from hashlib import sha256
from types import SimpleNamespace

import pytest

from command_center.offline_speech import MODEL_FILES, OfflineSpeech, verify_model
from command_center.store import Denied


def model(tmp_path):
    manifest = {}
    for name in MODEL_FILES:
        (tmp_path / name).write_bytes(name.encode())
        manifest[name] = sha256(name.encode()).hexdigest()
    return manifest


def test_model_snapshot_is_exact_and_tampering_fails_before_runtime_import(tmp_path):
    manifest = model(tmp_path)
    assert len(verify_model(tmp_path, manifest)) == 64
    (tmp_path / 'model.bin').write_bytes(b'changed')
    with pytest.raises(Denied, match='binding_changed'):
        verify_model(tmp_path, manifest)


def test_unreviewed_model_files_are_not_loaded(tmp_path):
    manifest = model(tmp_path)
    (tmp_path / 'unexpected.py').write_text('')
    with pytest.raises(Denied, match='snapshot_not_exact'):
        verify_model(tmp_path, manifest)


def test_runtime_is_local_cpu_only_and_disables_decoder_telemetry(tmp_path, monkeypatch):
    import sys
    events = []

    def whisper(directory, **options):
        assert events == ['telemetry_disabled']
        assert directory == str(tmp_path)
        assert options == {'device': 'cpu', 'compute_type': 'int8', 'cpu_threads': 1,
                           'num_workers': 1, 'local_files_only': True}
        return object()

    monkeypatch.setitem(sys.modules, 'onnxruntime', SimpleNamespace(
        disable_telemetry_events=lambda: events.append('telemetry_disabled')))
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=whisper))
    assert OfflineSpeech(tmp_path, model(tmp_path)).model is not None


def decoder(monkeypatch, segments):
    import command_center.offline_speech as speech
    monkeypatch.setattr(speech, 'decode_audio', lambda _: [0] * 16000)
    result = object.__new__(OfflineSpeech)

    class Model:
        def transcribe(self, samples, **kwargs):
            assert kwargs['language'] == 'ru' and kwargs['vad_filter'] is True
            assert kwargs['condition_on_previous_text'] is False
            return iter(segments), None

    result.model = Model()
    return result


def test_transcript_hash_binds_exact_audio_and_returns_no_authority(monkeypatch):
    speech = decoder(monkeypatch, [SimpleNamespace(start=0, end=1, text=' Позвонить завтра ')])
    result = speech.transcribe(b'public-fixture')
    assert result == {'audio_sha256': sha256(b'public-fixture').hexdigest(), 'language': 'ru',
                      'text': 'Позвонить завтра', 'duration_seconds': 1.0}


@pytest.mark.parametrize('segments,code', [
    ([], 'no_speech'),
    ([SimpleNamespace(start=0, end=float('nan'), text='noise')], 'segment_invalid'),
    ([SimpleNamespace(start=0, end=1, text='я' * 1001)], 'too_large'),
])
def test_bad_inference_does_not_become_a_task(monkeypatch, segments, code):
    with pytest.raises(Denied, match=code):
        decoder(monkeypatch, segments).transcribe(b'fixture')


@pytest.mark.parametrize('code,paused', [('control_blocked', True), ('voice_profile_revoked', False),
                                      ('audit_integrity_failure', False)])
def test_only_normal_stop_becomes_an_idle_worker_pause(code, paused):
    from command_center.voice_worker import process_or_pause

    class Worker:
        def process_one(self):
            raise Denied(code)

    if paused:
        assert process_or_pause(Worker()) == {'state': 'PAUSED'}
    else:
        with pytest.raises(Denied, match=code):
            process_or_pause(Worker())
