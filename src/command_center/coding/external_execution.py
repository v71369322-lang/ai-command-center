"""Networkless edit/test step. Receives sources, never credentials or gateway handles."""
from .agent import check
from .spec import safe_source
from .workspace import Workspace


def apply_proposals(job, root):
    proposals, task = job['proposals'], job['coding']
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= task['max_iterations']:
        raise ValueError('iteration_scope')
    workspace = Workspace(root, job['operation_id'], job['fence'], task['base_sha'])
    history = []
    try:
        for number, proposal in enumerate(proposals, 1):
            if set(proposal) != {'calculator.py'}:
                raise ValueError('edit_scope')
            safe_source(proposal['calculator.py'])
            workspace.apply(proposal)
            commit = workspace.commit()
            history.append({'attempt': number, 'commit': commit, 'checks': check(workspace.root, 3)})
        return {'status': 'ready_for_verification' if history[-1]['checks']['passed'] else 'attempt_failed',
                'history': history, 'git': workspace.export(),
                # This is replay accounting only, NOT provider-billed usage.
                'usage': {'synthetic': True, 'units': len(proposals), 'tokens': 0}}
    finally:
        workspace.repo.close()
