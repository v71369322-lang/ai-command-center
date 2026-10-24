"""OIDC/JWT adapter with server-side revocable sessions. No home-made MFA protocol."""
from datetime import timedelta
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import time

from fastapi import HTTPException
import jwt
from sqlalchemy import select

from .models import OwnerSession


def checksum(value):
    return hashlib.sha256(value.encode()).hexdigest()


class OwnerAuth:
    cookie = '__Host-f1-session'

    def __init__(self, store):
        self.store, self.settings = store, store.settings

    def trusted(self):
        s = self.settings
        return bool(s.auth_mode == 'oidc' and s.oidc_issuer.startswith('https://') and s.oidc_audience
                    and s.oidc_owner and s.oidc_jwks_file and Path(s.oidc_jwks_file).is_file()
                    and s.web_origin.startswith('https://'))

    def exchange(self, assertion):
        if not self.trusted():
            raise HTTPException(503, 'identity_provider_not_configured')
        try:
            header = jwt.get_unverified_header(assertion)
            keys = json.loads(Path(self.settings.oidc_jwks_file).read_text())['keys']
            selected = next(k for k in keys if k.get('kid') == header.get('kid') and k.get('kty') == 'RSA')
            key = jwt.PyJWK.from_dict(selected).key
            claims = jwt.decode(assertion, key, algorithms=['RS256'],
                                issuer=self.settings.oidc_issuer, audience=self.settings.oidc_audience,
                                options={'require': ['exp', 'iat', 'nbf', 'sub', 'jti', 'auth_time', 'amr']})
            if (claims['sub'] != self.settings.oidc_owner or not isinstance(claims['amr'], list)
                    or 'mfa' not in claims['amr'] or type(claims['auth_time']) is not int
                    or not 0 <= time.time() - claims['auth_time'] <= 300
                    or not isinstance(claims['jti'], str) or len(claims['jti']) > 200):
                raise ValueError('owner_mfa_required')
        except Exception:
            raise HTTPException(401, 'invalid_owner_assertion') from None
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        assertion_hash = checksum(self.settings.oidc_issuer + ':' + claims['jti'])
        with self.store.transaction() as session:
            self.store.check_audit(session)
            previous = session.execute(select(OwnerSession).where(OwnerSession.assertion_hash == assertion_hash)).first()
            if previous:
                raise HTTPException(401, 'assertion_already_exchanged')
            remaining = min(900, int(claims['exp'] - time.time()))
            if remaining < 1:
                raise HTTPException(401, 'expired_owner_assertion')
            session.add(OwnerSession(token_hash=checksum(token), csrf_hash=checksum(csrf),
                                     assertion_hash=assertion_hash, subject=claims['sub'],
                                     expires_at=self.store.now(session) + timedelta(seconds=remaining), revoked=False))
            self.store.audit(session, 'owner_session_created', 'owner')
        return token, csrf, remaining

    def authenticate(self, request):
        token = request.cookies.get(self.cookie, '')
        if not self.trusted() or not token or len(token) > 256 or request.url.scheme != 'https':
            raise HTTPException(401, 'owner_session_required')
        with self.store.transaction() as session:
            row = session.get(OwnerSession, checksum(token))
            if not row or row.revoked or row.expires_at <= self.store.now(session):
                raise HTTPException(401, 'owner_session_invalid')
            if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                origin = request.headers.get('origin')
                supplied = request.headers.get('x-csrf-token', '')
                if ((origin and origin != self.settings.web_origin) or len(supplied) > 256
                        or not hmac.compare_digest(checksum(supplied), row.csrf_hash)):
                    raise HTTPException(403, 'csrf_rejected')
        return 'owner'

    def revoke(self, token=None, all_sessions=False):
        with self.store.transaction() as session:
            rows = session.execute(select(OwnerSession)).scalars() if all_sessions else [session.get(OwnerSession, checksum(token or ''))]
            for row in rows:
                if row:
                    row.revoked = True
            self.store.audit(session, 'owner_sessions_revoked', 'owner', all_sessions=all_sessions)

    def csrf(self, token):
        value = secrets.token_urlsafe(32)
        with self.store.transaction() as session:
            row = session.get(OwnerSession, checksum(token))
            if not row or row.revoked or row.expires_at <= self.store.now(session):
                raise HTTPException(401, 'owner_session_invalid')
            row.csrf_hash = checksum(value)
            self.store.audit(session, 'owner_csrf_rotated', 'owner')
        return value
