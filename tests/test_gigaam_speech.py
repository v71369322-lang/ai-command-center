from hashlib import sha256
from types import SimpleNamespace
import sys

import pytest

from command_center import gigaam_speech as speech
from command_center.speech_models import GIGAAM_MANIFEST, model_files, model_target
from command_center.store import Denied


def test_modified_snapshot_rejected_before_importing_optional_runtime(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'onnx_asr', None)
    changed = {**GIGAAM_MANIFEST, 'v3_e2e_ctc.int8.onnx': '0' * 64}
    with pytest.raises(Denied, match='exact_snapshot'):
        speech.GigaamSpeech(tmp_path, changed)
    with pytest.raises(ValueError, match='not_supported'):
        model_files(changed)


def test_missing_snapshot_rejected_before_inference_runtime(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'onnx_asr', None)
    with pytest.raises(Denied, match='binding_invalid'):
        speech.GigaamSpeech(tmp_path, GIGAAM_MANIFEST)


def test_local_cpu_loader_has_no_model_download_or_gpu_selection(tmp_path, monkeypatch):
    events = []

    def verify(directory, manifest, *, files):
        assert directory == tmp_path and manifest == GIGAAM_MANIFEST
        assert set(files) == set(GIGAAM_MANIFEST)
        events.append('verified')
        return 'a' * 64

    def load(name, directory, **options):
        assert events == ['verified', 'telemetry_disabled']
        assert name == 'gigaam-v3-e2e-ctc' and directory == str(tmp_path)
        assert options['quantization'] == 'int8' and options['providers'] == ['CPUExecutionProvider']
        assert options['sess_options'].intra_op_num_threads == options['sess_options'].inter_op_num_threads == 1
        assert options['preprocessor_config']['max_concurrent_workers'] == 1
        return object()

    monkeypatch.setattr(speech, 'verify_model', verify)
    monkeypatch.setitem(sys.modules, 'onnxruntime', SimpleNamespace(SessionOptions=SimpleNamespace,
        disable_telemetry_events=lambda: events.append('telemetry_disabled')))
    monkeypatch.setitem(sys.modules, 'onnx_asr', SimpleNamespace(load_model=load))
    assert speech.GigaamSpeech(tmp_path, GIGAAM_MANIFEST).model_fingerprint == 'a' * 64
    assert model_target(GIGAAM_MANIFEST) == '/models/gigaam-v3'


def decoder(monkeypatch, texts, seconds=1, segments=None):
    samples = [.1] * (seconds * 16000)
    monkeypatch.setattr(speech, 'decode_audio', lambda audio: samples)
    if segments is None:
        segments = [{'start': 0, 'end': len(samples)}]
    vad = SimpleNamespace(get_speech_timestamps=lambda data, options: segments,
                          VadOptions=lambda **options: options)
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(vad=vad))
    monkeypatch.setitem(sys.modules, 'faster_whisper.vad', vad)
    calls, values = [], iter(texts)

    def recognize(data, *, sample_rate):
        assert 0 < len(data) <= 15 * 16000 and sample_rate == 16000
        calls.append(len(data))
        return next(values)

    result = object.__new__(speech.GigaamSpeech)
    result.model = SimpleNamespace(recognize=recognize)
    return result, calls


def test_result_preserves_audio_binding_and_creates_no_action_authority(monkeypatch):
    result, _ = decoder(monkeypatch, ['  Не переноси встречу.  '])
    assert result.transcribe(b'public fixture') == {
        'audio_sha256': sha256(b'public fixture').hexdigest(), 'language': 'ru',
        'text': 'Не переноси встречу.', 'duration_seconds': 1.0}


def test_long_note_keeps_every_sample_and_repeated_words(monkeypatch):
    result, calls = decoder(monkeypatch, ['Нет,', 'нет,', 'не переноси.'], seconds=31)
    assert result.transcribe(b'fixture')['text'] == 'Нет, нет, не переноси.'
    assert sum(calls) == 31 * 16000 and len(calls) == 3


def test_empty_speech_window_cannot_silently_disappear(monkeypatch):
    result, _ = decoder(monkeypatch, ['', 'Остаток'], seconds=16)
    with pytest.raises(Denied, match='chunk_empty'):
        result.transcribe(b'fixture')


def test_silence_does_not_become_an_invented_request(monkeypatch):
    result, calls = decoder(monkeypatch, [], segments=[])
    with pytest.raises(Denied, match='no_speech'):
        result.transcribe(b'fixture')
    assert calls == []


def test_oversized_note_is_rejected_not_truncated(monkeypatch):
    result, _ = decoder(monkeypatch, ['я' * 1000, 'x'], seconds=16)
    with pytest.raises(Denied, match='too_large'):
        result.transcribe(b'fixture')


@pytest.mark.parametrize('value', [None, {}, 42])
def test_invalid_decoder_output_cannot_be_saved(monkeypatch, value):
    result, _ = decoder(monkeypatch, [value])
    with pytest.raises(Denied, match='transcript_invalid'):
        result.transcribe(b'fixture')
