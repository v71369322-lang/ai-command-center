"""Cloud-only, read-only source compatibility checks; never contact a VPS."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

APPROVED = '316dc1615dea224bcf4bd595d87048d19820bd21'
BASELINE = '4cc6ec46bf461d65958f013bb23ac2234b9a7fd3'
PREVIOUS_BUNDLE = '1e151b2953b6debb4bb05096fba20aa6c740665015f31479a50fd25c6ef80106'
OLD_SCHEMA = 'fde2dffdff0dacd1e1b46e97a747962c5b5a44f9cbd2076c969efd3f8d03378a'
NEW_SCHEMA = '4039930b4d9b11fe7bf0aad046bcb47b29397a25aa41a6b878145ed60056276a'
CHAIN = ['53565cc2ca232fb2cf6d6552a3ae04b462d92956', BASELINE,
         'a994de96c2f9656f1d766a849e63a6836e21ef65',
         '2f50fbb148eb116378fe69bcc3e3a9eb44fe0245', APPROVED]
REQUIRED = ['Dockerfile', 'Dockerfile.executor', 'compose.yaml', 'infra/vps/build_release.sh',
            *['src/command_center/' + name + '.py' for name in (
                'password_auth', 'telegram_bridge', 'telegram_service', 'telegram_release',
                'telegram_health', 'telegram_transition', 'telegram_requests')]]


def migration(reader, revision):
    hashes = {name: hashlib.sha256(reader(revision, 'src/command_center/' + name)).hexdigest()
              for name in ('models.py', 'admin.py')}
    # Exactly the deployment.migration_hash / deployment_profile.checksum format.
    return hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def compatibility(reader):
    old_lock, new_lock = reader(BASELINE, 'requirements.lock'), reader(APPROVED, 'requirements.lock')
    if old_lock != new_lock:
        raise ValueError('f32_existing_tools_dependency_mismatch')
    if migration(reader, BASELINE) != OLD_SCHEMA or migration(reader, APPROVED) != NEW_SCHEMA:
        raise ValueError('f32_unknown_schema_transition')
    return {'requirements_sha256': hashlib.sha256(new_lock).hexdigest(),
            'old_schema': OLD_SCHEMA, 'new_schema': NEW_SCHEMA,
            'required_files_sha256': {name: hashlib.sha256(reader(APPROVED, name)).hexdigest() for name in REQUIRED}}


def report(repository, channel):
    if channel.REVISION != APPROVED:
        raise ValueError('f32_unapproved_application')
    repository = Path(repository)
    try:
        for previous, following in zip(CHAIN, CHAIN[1:]):
            channel.git(repository, 'merge-base', '--is-ancestor', previous, following)
        result = compatibility(lambda revision, name: channel.git(repository, 'show', revision + ':' + name))
        with tempfile.TemporaryDirectory() as temp:
            packet = Path(temp) / 'source.json'
            channel.pack(repository, packet)
            raw = packet.read_bytes()
            objects = channel.validate(raw)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ValueError('f32_source_history_or_required_file_missing') from error
    return {'scope': 'CLOUD_SOURCE_ONLY', 'status': 'PASS', 'revision': APPROVED,
            'expected_baseline_revision': BASELINE, 'expected_previous_bundle': PREVIOUS_BUNDLE,
            'baseline_observed_on_vps': False, 'source_ancestry': CHAIN,
            'packet_bytes': len(raw), 'packet_sha256': hashlib.sha256(raw).hexdigest(),
            'git_objects': len(objects), **result, 'migration_required': True,
            'generic_update_allowed': False, 'telegram_default': 'disabled',
            'image_ids_verified': False, 'bundle_digest': None, 'vps_contacted': False,
            'host_rootless_verified': False, 'live_calls_enabled': False}


if __name__ == '__main__':
    import argparse
    import prepare_channel
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    print(json.dumps(report(args.source, prepare_channel), indent=2, sort_keys=True))
