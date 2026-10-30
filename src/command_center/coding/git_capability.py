"""Bounded Git smart-HTTP discovery, never a push or a grant of task authority."""
import hashlib
import re

from ..store import Denied

SERVICE = 'git-receive-pack'
CONTENT_TYPE = 'application/x-git-receive-pack-advertisement'


def discovery_path(repository):
    return '/' + repository + '.git/info/refs?service=' + SERVICE


def advertisement(raw, content_type, repository):
    """Validate the complete pkt-line stream; persist only a bounded projection."""
    try:
        if not isinstance(raw, (bytes, bytearray)) or not 12 <= len(raw) <= 65536:
            raise ValueError()
        if content_type.split(';')[0].strip() != CONTENT_TYPE:
            raise ValueError()
        offset = 0

        def packet():
            nonlocal offset
            header = raw[offset:offset + 4]
            if not re.fullmatch(b'[0-9a-f]{4}', header):
                raise ValueError()
            size = int(header, 16)
            if size == 0:
                offset += 4
                return None
            if size < 5 or offset + size > len(raw):
                raise ValueError()
            value = bytes(raw[offset + 4:offset + size])
            offset += size
            return value

        if packet() not in {b'# service=git-receive-pack', b'# service=git-receive-pack\n'} or packet() is not None:
            raise ValueError()
        refs = {}
        while True:
            value = packet()
            if value is None:
                break
            if not refs:
                value, capabilities = value.split(b'\0')
                capabilities = capabilities.removesuffix(b'\n')
                if not capabilities or any(byte < 32 or byte > 126 for byte in capabilities):
                    raise ValueError()
            row = re.fullmatch(b'([0-9a-f]{40}) ([^\x00-\x20\x7f]+)\n?', value)
            if not row or row[2] in refs or len(refs) >= 256:
                raise ValueError()
            refs[row[2]] = row[1].decode('ascii')
        if offset != len(raw) or b'refs/heads/main' not in refs:
            raise ValueError()
        return {'schema': 1, 'repository': repository, 'service': SERVICE,
                'main_sha': refs[b'refs/heads/main'], 'refs_count': len(refs),
                'advertisement_sha256': hashlib.sha256(raw).hexdigest()}
    except (ValueError, TypeError, AttributeError):
        raise Denied('github_git_advertisement_invalid') from None


def valid_discovery(value, repository, baseline):
    return (isinstance(value, dict) and set(value) == {
        'schema', 'repository', 'service', 'main_sha', 'refs_count', 'advertisement_sha256'}
        and type(value['schema']) is int and value['schema'] == 1
        and value['repository'] == repository and value['service'] == SERVICE
        and value['main_sha'] == baseline and type(value['refs_count']) is int
        and 1 <= value['refs_count'] <= 256 and isinstance(value['advertisement_sha256'], str)
        and re.fullmatch('[a-f0-9]{64}', value['advertisement_sha256']) is not None)
