"""Pinned CPU-only Russian ASR, with bounded, nonoverlapping inference windows."""

from hashlib import sha256

from .offline_speech import decode_audio, verify_model
from .speech_chunks import chunk_ranges
from .speech_models import GIGAAM_MANIFEST
from .store import Denied


class GigaamSpeech:
    def __init__(self, directory, manifest):
        if manifest != GIGAAM_MANIFEST:
            raise Denied('gigaam_exact_snapshot_required')
        self.model_fingerprint = verify_model(directory, manifest, files=tuple(GIGAAM_MANIFEST))
        import onnxruntime as ort
        ort.disable_telemetry_events()
        import onnx_asr
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.model = onnx_asr.load_model('gigaam-v3-e2e-ctc', str(directory), quantization='int8',
            sess_options=options, providers=['CPUExecutionProvider'],
            preprocessor_config={'max_concurrent_workers': 1, 'providers': ['CPUExecutionProvider'],
                                 'sess_options': options})

    def transcribe(self, audio):
        from faster_whisper.vad import get_speech_timestamps, VadOptions
        samples = decode_audio(audio)
        speech = get_speech_timestamps(samples, VadOptions(min_silence_duration_ms=100, speech_pad_ms=0))
        if not speech:
            raise Denied('speech_no_speech_detected')
        parts, size = [], 0
        for window in chunk_ranges(len(samples), speech):
            if not any(s['start'] < window['end'] and window['start'] < s['end'] for s in speech):
                continue
            value = self.model.recognize(samples[window['start']:window['end']], sample_rate=16000)
            if not isinstance(value, str):
                raise Denied('speech_transcript_invalid')
            value = value.strip()
            if not value:
                raise Denied('speech_chunk_empty')
            size += len(value.encode()) + bool(parts)
            if size > 2000:
                # Preserve the existing contract. Never silently truncate a long note.
                raise Denied('speech_transcript_too_large')
            parts.append(value)
        if not parts:
            raise Denied('speech_no_speech_detected')
        return {'audio_sha256': sha256(audio).hexdigest(), 'language': 'ru',
                'text': ' '.join(parts), 'duration_seconds': len(samples) / 16000}
