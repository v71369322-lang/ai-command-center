"""Read-only acceptance runner baked into the image, never taken from agent claims."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from command_center.coding.spec import safe_source  # noqa: E402


def run(root):
    source = Path(root) / 'calculator.py'
    safe_source(source.read_text())
    spec = importlib.util.spec_from_file_location('f2_calculator_under_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = [([], 0), ([1, 2, 3], 6), ([-4, 2, -1, 5, 0], 7), ([0, -8], 0)]
    suite = unittest.TestSuite()
    for values, expected in cases:
        def case(values=values, expected=expected):
            if module.sum_positive(values) != expected:
                raise AssertionError('synthetic acceptance mismatch')
        suite.addTest(unittest.FunctionTestCase(case))
    result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    return {'tests_run': result.testsRun, 'failures': len(result.failures),
            'errors': len(result.errors), 'passed': result.wasSuccessful()}


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), sort_keys=True))
