"""Owner-only connection blueprints. No probes, credentials or execution authority."""
from .project_inbox import IDS, owner
from .store import Denied

REPOSITORIES = {
    'command-center': 'v71369322-lang/ai-command-center',
    'vanilla-sugar': 'v71369322-lang/Vanilla-Sugar-CRM',
    'lnauto': 'v71369322-lang/LNAuto',
    'capital-lab': 'v71369322-lang/Capital-Lab',
}


def connection_plan(role, project_id):
    owner(role)
    if not isinstance(project_id, str) or project_id not in IDS:
        raise Denied('unknown_project')
    return {'schema': 1, 'project_id': project_id, 'scope': 'PLAN_ONLY',
            'expected_repository': REPOSITORIES[project_id], 'checked_at': None,
            'components': [{'id': key, 'state': 'NOT_CHECKED'} for key in
                           ('repository', 'verification_environment', 'deployment_channel')],
            'execution_connected': False, 'external_checks_performed': False, 'actions_enabled': []}
