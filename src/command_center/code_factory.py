"""Compose code proposals with the installed broker HTTP host, never an executor key."""
from .code_generation import CodeGateway, configured, fresh
from .live_planning_gateway import PlanningCredentials
from .planning_profile import load
from .store import Denied, digest


class CodeFactory:
    def __init__(self, store):
        self.store = store

    def preflight(self):
        with self.store.transaction() as session:
            self.store.check_audit(session)
            profile, _ = configured(self.store, session)
            fresh(self.store, session, profile)
            if profile.mode != 'live':
                raise Denied('code_live_profile_not_connected')
            return profile

    def __call__(self, guard):
        profile = self.preflight()
        installed = load()
        if installed is None or digest(installed.model_dump()) != profile.installation_profile_digest:
            raise Denied('code_installed_profile_missing')
        return CodeGateway(self.store, profile, credentials=PlanningCredentials(installed),
                           runtime_guard=lambda: guard(profile.runtime.model_dump()))
