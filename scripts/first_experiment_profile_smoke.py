"""Networkless cloud-container binding proof; public fake credentials, never VPS/live."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

from command_center.coding.first_experiment import CAP, FirstExperiment, MODEL
from command_center.coding.integration_config import IntegrationConfig, Tariff
from command_center.deployment import migration_hash
from command_center.deployment_integrations import mounts, prepare_binding
from command_center.deployment_profile import atomic_json, render
from command_center.local_docker import environment, run as docker


def main():
    source = Path.cwd()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain']) or os.getuid() < 1000:
        raise ValueError('clean_unprivileged_cloud_source_required')
    env = dict(environment(), F1_SOURCE_REVISION=revision, F1_DOCKER_GID='0')
    base = json.loads(subprocess.check_output(['docker', '--host=unix:///var/run/docker.sock', 'compose',
        '--profile', 'worker', '-f', 'compose.yaml', 'config', '--format', 'json'], env=env))
    tags = {'api': 'acc-f1-app:local', 'worker': 'acc-f1-worker:local', 'broker': 'acc-f1-broker:local',
            'executor': 'acc-f1-executor:local', 'coding': 'acc-f2-executor:local'}
    images = {}
    for key, tag in tags.items():
        result = docker('image', 'inspect', tag)
        result.check_returncode()
        image = json.loads(result.stdout)[0]
        if image['Config']['Labels'].get('org.opencontainers.image.revision') != revision:
            raise ValueError('first_experiment_probe_image_revision_mismatch')
        images[key] = image['Id']
    with tempfile.TemporaryDirectory(prefix='acc-f2-profile-public-fixture-') as temporary:
        private = Path(temporary)
        config = IntegrationConfig(mode='live', live_authorized=False,
            synthetic_repository='fixture/acc-f2-synthetic-container', budget_evidence='PUBLIC_FIXTURE_ONLY',
            daily_nano_rub=CAP, monthly_nano_rub=CAP, first_experiment=FirstExperiment(repository_id=725000001),
            tariff=Tariff(model=MODEL, input_nano_rub=67500, output_nano_rub=405000,
                          context_tokens=400000, max_output_tokens=2048, confirmed=True, evidence='PUBLIC_FIXTURE_ONLY'),
            credential_files={'openai': '/run/f2/openai.key', 'github-installation-token': '/run/f2/github.token'})
        config_file = private / 'config.json'
        atomic_json(config_file, {**config.model_dump(), 'credential_files': config.credential_files})
        paths = {'config_file': config_file}
        for name in ('openai_key_file', 'github_token_file'):
            path = private / name
            path.write_text('PUBLIC_SYNTHETIC_FIXTURE_' + name)
            path.chmod(0o600)
            paths[name] = path
        manifest = dict(schema=1, revision=revision, images=images, migration_hash=migration_hash(source),
            database_image=base['services']['db']['image'], redis_image=base['services']['redis']['image'],
            control_uid=os.getuid(), execution_uid=os.getuid() + 1, source_root=str(source), data_root=str(private / 'state'))
        manifest['first_experiment'] = prepare_binding(manifest, **paths)
        profile = render(base, manifest)
        names = []

        def probe(role, code):
            name = 'acc-f2-profile-' + uuid4().hex
            names.append(name)
            args = ['run', '--rm', '--name', name, '--network', 'none', '--read-only', '--cap-drop=ALL',
                    '--security-opt=no-new-privileges', '--user', f'{os.getuid()}:{os.getgid()}',
                    '--memory=256m', '--cpus=.5', '--pids-limit=64', '--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m']
            for key, value in profile['services'][role]['environment'].items():
                if key.startswith('F2_INTEGRATION'):
                    args += ['--env', key + '=' + value]
            for mount in mounts(manifest, role):
                args += ['--mount', f'type=bind,src={mount["source"]},dst={mount["target"]},readonly']
            image = images['broker' if role == 'runtime-broker' else role]
            result = docker(*args, image, 'python', '-B', '-c', code, timeout=45)
            if result.returncode:
                raise ValueError('first_experiment_container_probe_failed:' + role)

        try:
            common = ('import os,errno;from command_center.coding.integration_config import IntegrationConfig,FileCredentials;'
                      'c=IntegrationConfig.load();assert c.mode=="live" and not c.connected();'
                      'assert not c.first_experiment.report()["ready_for_final_confirmation"];')
            probe('api', common + '\nfor ref in (c.openai_secret_ref,c.github_secret_ref):\n'
                  ' try: FileCredentials(c).get(ref)\n'
                  ' except FileNotFoundError: pass\n'
                  ' else: raise ValueError("credential_visible_to_api")\n')
            broker = common + ('assert FileCredentials(c).get(c.openai_secret_ref)=="PUBLIC_SYNTHETIC_FIXTURE_openai_key_file";'
                               'assert FileCredentials(c).get(c.github_secret_ref)=="PUBLIC_SYNTHETIC_FIXTURE_github_token_file";')
            broker += '\nfor path in c.credential_files.values():\n'
            broker += (' try: fd=os.open(path,os.O_WRONLY)\n'
                       ' except OSError as error: assert error.errno in (errno.EROFS,errno.EACCES,errno.EPERM)\n'
                       ' else: os.close(fd);raise ValueError("credential_mount_writable")\n')
            probe('runtime-broker', broker)
            probe('worker', 'import os;from pathlib import Path;'
                  'from command_center.coding.integration_config import IntegrationConfig;'
                  'assert IntegrationConfig.load().mode=="disabled";'
                  'assert not any(k.startswith("F2_INTEGRATION") for k in os.environ);'
                  'assert not Path("/run/f2").exists()')
            # The profile_hash excludes credential references. A byte pin must still
            # reject redirecting the OpenAI alias to an unrelated mounted secret.
            altered = json.loads(config_file.read_text())
            altered['credential_files']['openai'] = '/run/secrets/db_runtime_password'
            atomic_json(config_file, altered)
            probe('runtime-broker', 'from command_center.coding.integration_config import IntegrationConfig\n'
                  'try: IntegrationConfig.load()\n'
                  'except ValueError as error: assert str(error)=="integration_config_pin_changed"\n'
                  'else: raise ValueError("changed_reference_accepted")\n')
        finally:
            for name in names:
                docker('rm', '-f', name)  # Exact fresh probe names only, including a timed-out CLI.
    report = dict(revision=revision, mode='CLOUD_ROOTFUL_NETWORKLESS_PUBLIC_FIXTURES',
        api_config_only=True, broker_only_credentials=True, credential_mounts_readonly=True,
        worker_unconfigured=True, changed_reference_rejected=True, exact_image_revision=True,
        real_credentials_used=False, external_api_calls=0, vps_contacted=False, rootless_host_verified=False)
    atomic_json(source / '.runtime/first-experiment-profile-smoke.json', report)
    print('First-experiment profile: API config only, broker readonly credentials, worker isolated, byte pin: PASS')


if __name__ == '__main__':
    main()
