"""Explicit pinned operator evidence; no provider credentials or network access."""
import hashlib
import json
import os
import re

from .planning_admission import PlanningProfile
from .request_planning import _unique
from .store import Denied
from .telegram_transport import private_read


def load():
    path = os.environ.get('F1_PLANNING_PROFILE_FILE')
    pin = os.environ.get('F1_PLANNING_PROFILE_SHA256')
    if path is None and pin is None:
        return None
    try:
        if not path or not isinstance(pin, str) or not re.fullmatch('[a-f0-9]{64}', pin):
            raise ValueError()
        raw = private_read(path, 16384)
        if len(raw) > 16384 or hashlib.sha256(raw).hexdigest() != pin:
            raise ValueError()
        return PlanningProfile.model_validate(json.loads(raw, object_pairs_hook=_unique))
    except (OSError, ValueError, Denied, RecursionError):
        raise Denied('planning_profile_invalid_or_unavailable') from None
