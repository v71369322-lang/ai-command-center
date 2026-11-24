"""Restriction-only transition policy; never an additional execution authority."""
import os


def assistant_only():
    value = os.environ.get('F1_ASSISTANT_ONLY', '0')
    if value not in {'0', '1'}:
        raise RuntimeError('assistant_mode_invalid')
    return value == '1'


def require_developer():
    if assistant_only():
        from .store import Denied
        raise Denied('developer_functionality_disabled')


PERSONAL_INTENTS = frozenset({
    'capture', 'voice_request', 'voice_confirm', 'voice',
    'help', 'projects', 'project', 'requests', 'request', 'assign',
    'archive_request', 'restore_request', 'attention', 'reminders',
    'attention_schedule', 'attention_schedule_change',
    'calendar_list', 'calendar_create', 'calendar_decide', 'calendar_voice',
    'stop', 'resume_request', 'resume_confirm', 'assistant_disabled', 'unknown_command',
})


def http_allowed(method, path):
    if not path.startswith('/api/'):
        return True
    read = {'/api/health', '/api/state', '/api/auth/mode', '/api/auth/csrf', '/api/telegram/status',
            '/api/telegram/requests', '/api/project-inbox', '/api/attention', '/api/attention/schedule'}
    write = {'/api/auth/login', '/api/auth/exchange', '/api/auth/logout', '/api/auth/revoke-all',
             '/api/control/stop', '/api/control/resume', '/api/project-inbox/assign',
             '/api/attention/schedule'}
    return (method == 'GET' and (path in read or (
        path.startswith('/api/projects/') and len(path.split('/')) == 4))) or (method == 'POST' and path in write)
