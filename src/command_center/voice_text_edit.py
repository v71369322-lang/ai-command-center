"""Literal owner-requested correction; no inferred spelling or action execution."""
import re

_QUOTED = r'(?:«([^«»\r\n]+)»|"([^"\r\n]+)"|“([^“”\r\n]+)”)'
_PATTERN = re.compile(r'замени\s+' + _QUOTED + r'\s+на\s+' + _QUOTED + r'\.?', re.I)


def replace_once(instruction, original):
    """None means a full-text reply; reserved replacement syntax must be exact."""
    if not re.match(r'замени\b', instruction.strip(), re.I):
        return None
    match = _PATTERN.fullmatch(instruction.strip())
    if not match:
        raise ValueError('voice_fragment_format')
    old = next(value for value in match.groups()[:3] if value is not None)
    new = next(value for value in match.groups()[3:] if value is not None)
    if not old.strip() or not new.strip():
        raise ValueError('voice_fragment_format')
    start = original.find(old)
    if start < 0 or original.rfind(old) != start:
        raise ValueError('voice_fragment_not_unique')
    return original[:start] + new + original[start + len(old):]
