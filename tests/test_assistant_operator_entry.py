import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize('assistant', [False, True])
def test_predecessor_maintenance_has_one_entry_wrapper(monkeypatch, assistant):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / 'infra/vps'))
    spec = importlib.util.spec_from_file_location('entry_operator', root / 'infra/vps/activate_assistant_candidate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured = []

    def base_tool(self, code):
        if self.m.get('assistant_only'):
            code = module.entry_retry_code() + code
        captured.append(code)
    monkeypatch.setattr(module.Deployment, 'tool', base_tool)
    controller = object.__new__(module.PreviousUpdate)
    controller.m = {'assistant_only': True} if assistant else {}
    controller.tool('OPERATOR_BODY')
    assert captured[0].count('_maintenance_original=Store.transaction') == 1
    assert captured[0].endswith('OPERATOR_BODY')
