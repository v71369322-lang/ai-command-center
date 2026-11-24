"""Bounded lock-entry retry for trusted operator jobs, never transaction replay."""
from contextlib import contextmanager
import inspect
import sys
import time

from .voice_worker import admission_busy


@contextmanager
def bounded_entry(store, original, attempts=5, delay=1):
    if type(attempts) is not int or not 1 <= attempts <= 5 or not 0 <= delay <= 1:
        raise ValueError('maintenance_retry_bounds_invalid')
    for attempt in range(attempts):
        manager = original(store)
        try:
            session = manager.__enter__()
        except Exception as error:
            if not admission_busy(error, store) or attempt + 1 == attempts:
                raise
            time.sleep(delay)
        else:
            break
    try:
        yield session
    except BaseException:
        if not manager.__exit__(*sys.exc_info()):
            raise
    else:
        manager.__exit__(None, None, None)


def entry_retry_code():
    # Embedded into one disposable maintenance process. The predecessor image
    # already has admission_busy, but cannot import this new operator module.
    return ('from contextlib import contextmanager\nimport sys,time\n'
            'from command_center.voice_worker import admission_busy\n'
            + inspect.getsource(bounded_entry)
            + '\nfrom command_center.store import Store\n'
            '_maintenance_original=Store.transaction\n'
            'Store.transaction=lambda self: bounded_entry(self,_maintenance_original)\n')
