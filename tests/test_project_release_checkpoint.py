import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('project_release_checkpoint', ROOT / 'scripts/project_release_checkpoint.py')
checkpoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkpoint)


def test_project_release_checkpoint_is_offline_and_fail_closed():
    result = checkpoint.inspect(ROOT)
    assert result['base_revision'] == checkpoint.BASE and result['target_revision'] == checkpoint.TARGET
    assert result['status'] == 'OFFLINE_RELEASE_CHECKPOINT'
    assert result['external_calls'] == result['paid_calls'] == 0
    assert result['deployment_started'] is result['live_binding_modified'] is False
    assert result['blockers'] == ['live_bundle_reconciliation_required', 'exact_operator_profile_not_prepared',
                                  'rootless_images_not_built_for_target', 'vps_postcheck_not_run']
