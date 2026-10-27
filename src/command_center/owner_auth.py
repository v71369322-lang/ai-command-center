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
from sqlalchemy import select, func, cast, DateTime

from .models import OwnerSession, Audit
from . import password_auth


def checksum(value):
    return hashlib.sha256(value.encode()).hexdigest()


class OwnerAuth:
    @property
    def cookie(self):
        return '__Host-f1-session' if self.secure_cookie else 'f1-loopback-session'

    @property
    def secure_cookie(self):
        return not (self.settings.auth_mode == 'password' and self.settings.password_loopback_http
                    and self.settings.web_origin.startswith('http://'))

    def __init__(self, store):
        self.store, self.settings = store, store.settings

    def trusted(self):
        s = self.settings
        if s.auth_mode == 'password':
            try:
                password_auth.load(s.owner_password_file)
                return password_auth.origin_valid(s.web_origin, s.password_loopback_http)
            except Exception:
                return False
        return bool(s.auth_mode == 'oidc' and s.oidc_issuer.startswith('https://') and s.oidc_audience
                    and s.oidc_owner and s.oidc_jwks_file and Path(s.oidc_jwks_file).is_file()
                    and s.web_origin.startswith('https://'))

    def trust_document(self):
        try:
            path = Path(self.settings.oidc_jwks_file)
            if path.stat().st_size > 65536:
                raise ValueError('oversized_trust_bundle')
            return json.loads(path.read_text())
        except Exception:
            raise HTTPException(503, 'identity_trust_unavailable') from None

    def binding(self, keys=None):
        if self.settings.auth_mode == 'password':
            return checksum(json.dumps({'mode': 'password', 'origin': self.settings.web_origin,
                'loopback_http': self.settings.password_loopback_http,
                'revision': self.settings.source_revision,
                'verifier': password_auth.load(self.settings.owner_password_file) if keys is None else keys}, sort_keys=True))
        return checksum(json.dumps({'issuer': self.settings.oidc_issuer,
                                        'audience': self.settings.oidc_audience,
                                        'owner': self.settings.oidc_owner,
                                        'origin': self.settings.web_origin,
                                        'keys': self.trust_document() if keys is None else keys}, sort_keys=True))

    def exchange(self, assertion):
        if self.settings.auth_mode != 'oidc' or not self.trusted():
            raise HTTPException(503, 'identity_provider_not_configured')
        trust_document = self.trust_document()
        trust_binding = self.binding(trust_document)
        try:
            header = jwt.get_unverified_header(assertion)
            keys = trust_document['keys']
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
                                     assertion_hash=assertion_hash, subject=trust_binding,
                                     expires_at=self.store.now(session) + timedelta(seconds=remaining), revoked=False))
            self.store.audit(session, 'owner_session_created', 'owner')
        return token, csrf, remaining

    def transport_allowed(self, request):
        if self.settings.auth_mode == 'password':
            return (self.trusted() and str(request.base_url).rstrip('/') == self.settings.web_origin
                    and (request.url.scheme == 'https' or not self.secure_cookie))
        return request.url.scheme == 'https'

    def password_login(self, request, username, password):
        if self.settings.auth_mode != 'password' or not self.trusted():
            raise HTTPException(503, 'password_login_not_configured')
        if not self.transport_allowed(request) or request.headers.get('origin') != self.settings.web_origin:
            raise HTTPException(403, 'login_transport_or_origin_rejected')
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        valid = False
        limited = False
        # Same global admission/audit lock serializes attempts across API instances.
        with self.store.transaction() as session:
            self.store.check_audit(session)
            now = self.store.now(session)
            attempts = session.scalar(select(func.count()).select_from(Audit).where(
                Audit.event['kind'].as_string() == 'owner_password_attempt',
                cast(Audit.event['time'].as_string(), DateTime(timezone=True)) >= now - timedelta(minutes=15)))
            limited = attempts >= 5
            if not limited:
                value = password_auth.load(self.settings.owner_password_file)
                valid = password_auth.verify(value, username, password)
                self.store.audit(session, 'owner_password_attempt', 'owner' if valid else 'unauthenticated',
                                 accepted=valid)
                if valid:
                    session.add(OwnerSession(token_hash=checksum(token), csrf_hash=checksum(csrf),
                        assertion_hash=checksum('password-session:' + token), subject=self.binding(value),
                        expires_at=now + timedelta(minutes=15), revoked=False))
                    self.store.audit(session, 'owner_session_created', 'owner', method='password', mfa=False)
        # Raise only after the transaction commits, retaining denied attempts.
        if limited:
            raise HTTPException(429, 'owner_login_rate_limited')
        if not valid:
            raise HTTPException(401, 'invalid_owner_credentials')
        return token, csrf, 900

    def authenticate(self, request):
        token = request.cookies.get(self.cookie, '')
        if not self.trusted() or not token or len(token) > 256 or not self.transport_allowed(request):
            raise HTTPException(401, 'owner_session_required')
        with self.store.transaction() as session:
            row = session.get(OwnerSession, checksum(token))
            if not row or row.revoked or row.expires_at <= self.store.now(session) or row.subject != self.binding():
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
