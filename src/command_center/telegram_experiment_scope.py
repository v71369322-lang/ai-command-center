"""Fixed UI namespaces only. Every scope still uses the same F1 authorization."""
from .coding.first_experiment import EXPERIMENT_ID, RECOVERY_ID
from .store import Denied


def experiment_id(bridge):
    value = getattr(bridge, 'experiment_id', EXPERIMENT_ID)
    if value not in {EXPERIMENT_ID, RECOVERY_ID}:
        raise Denied('unknown_experiment_scope')
    return value


def key(bridge, value):
    return value.replace('experiment', 'recovery', 1) if experiment_id(bridge) == RECOVERY_ID else value


def title(bridge):
    return 'Восстановительный AI-тест' if experiment_id(bridge) == RECOVERY_ID else 'Первый AI-эксперимент'


class RecoveryBridge:
    experiment_id = RECOVERY_ID

    def __init__(self, bridge):
        self.bridge = bridge

    def __getattr__(self, name):
        return getattr(self.bridge, name)

    @staticmethod
    def text(value):
        for old, new in (
            ('/authorize_experiment', '/authorize_recovery'), ('/prepare_experiment', '/prepare_recovery'),
            ('/cancel_experiment', '/cancel_recovery'), ('/unwatch_experiment', '/unwatch_recovery'),
            ('/watch_experiment', '/watch_recovery'), ('/experiment', '/recovery'),
            ('Первый AI-эксперимент', 'Восстановительный AI-тест'),
            ('первого AI-эксперимента', 'восстановительного AI-теста'),
            ('первого платного AI-теста', 'восстановительного платного AI-теста'),
        ):
            value = value.replace(old, new)
        return value

    def finish(self, session, iid, value, markup=None):
        return self.bridge.finish(session, iid, self.text(value), markup)

    def enqueue(self, session, event, value, markup=None):
        return self.bridge.enqueue(session, event, self.text(value), markup)
