from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('same_report', [False, True])
def test_private_review_refuses_overwrite_before_loading_audio_or_model(tmp_path, same_report):
    review = tmp_path / 'private-review.json'
    review.write_text('private fixture transcript', encoding='utf-8')
    output = review if same_report else tmp_path / 'report.json'
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'speech_quality.py'
    result = subprocess.run([sys.executable, str(script), '--model', str(tmp_path / 'missing-model'),
        '--manifest', str(tmp_path / 'missing-manifest.json'), '--cases', str(tmp_path / 'missing-cases.json'),
        '--beam', '1', '--output', str(output), '--review-output', str(review)],
        capture_output=True, text=True, check=False, timeout=20)
    assert result.returncode == 2
    assert 'private review output must be a new, separate file' in result.stderr
    assert 'private fixture transcript' not in result.stdout + result.stderr
    assert review.read_text(encoding='utf-8') == 'private fixture transcript'
    if not same_report:
        assert not output.exists()
