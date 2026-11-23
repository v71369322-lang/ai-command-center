"""Credential-free, bounded Russian speech decoding from a pinned local model.

The caller supplies bytes, not a URL. Runtime model downloads are forbidden.
This module is intended for a separate resource-limited, networkless worker.
"""

from hashlib import sha256
from io import BytesIO
import math
from pathlib import Path
import re

from .store import Denied, digest
from .telegram_voice_requests import MAX_BYTES, MAX_SECONDS

MODEL_FILES = ('config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt')
MAX_SAMPLES = MAX_SECONDS * 16000


def verify_model(directory, manifest):
    """Check an exact local snapshot before importing the inference runtime."""
    path = Path(directory)
    if (not path.is_absolute() or path.is_symlink() or not path.is_dir()
            or not isinstance(manifest, dict) or set(manifest) != set(MODEL_FILES)):
        raise Denied('speech_model_binding_invalid')
    for name in MODEL_FILES:
        expected = manifest[name]
        file = path / name
        if (not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected)
                or file.is_symlink() or not file.is_file()):
            raise Denied('speech_model_binding_invalid')
        value = sha256()
        with file.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                value.update(chunk)
        if value.hexdigest() != expected:
            raise Denied('speech_model_binding_changed')
    # Reject optional/unreviewed files (including a tokenizer fallback/config).
    if set(item.name for item in path.iterdir()) != set(MODEL_FILES):
        raise Denied('speech_model_snapshot_not_exact')
    return digest(manifest)


def decode_audio(audio):
    """Decode in memory, bounding decoded samples as well as compressed bytes."""
    if not isinstance(audio, bytes) or not 1 <= len(audio) <= MAX_BYTES:
        raise Denied('speech_audio_size_invalid')
    import av
    import numpy as np

    chunks, count = [], 0
    try:
        with av.open(BytesIO(audio), mode='r') as container:
            if len(container.streams.audio) != 1:
                raise Denied('speech_audio_stream_invalid')
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            for frame in container.decode(audio=0):
                for converted in resampler.resample(frame):
                    count += converted.samples
                    if count > MAX_SAMPLES:
                        raise Denied('speech_audio_duration_invalid')
                    chunks.append(converted.to_ndarray().reshape(-1))
            for converted in resampler.resample(None):
                count += converted.samples
                if count > MAX_SAMPLES:
                    raise Denied('speech_audio_duration_invalid')
                chunks.append(converted.to_ndarray().reshape(-1))
    except Denied:
        raise
    except Exception:
        raise Denied('speech_audio_decode_failed') from None
    if not 1 <= count <= MAX_SAMPLES:
        raise Denied('speech_audio_duration_invalid')
    return np.concatenate(chunks).astype(np.float32) / 32768.0


class OfflineSpeech:
    def __init__(self, model_directory, manifest):
        self.model_fingerprint = verify_model(model_directory, manifest)
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from faster_whisper import WhisperModel

        self.model = WhisperModel(str(model_directory), device='cpu', compute_type='int8',
                                  cpu_threads=1, num_workers=1, local_files_only=True)

    def transcribe(self, audio):
        samples = decode_audio(audio)
        duration = len(samples) / 16000
        segments, _ = self.model.transcribe(samples, language='ru', task='transcribe',
            beam_size=1, best_of=1, temperature=0, condition_on_previous_text=False,
            vad_filter=True, vad_parameters={'min_silence_duration_ms': 500})
        parts, size = [], 0
        for segment in segments:
            if (not math.isfinite(segment.start) or not math.isfinite(segment.end)
                    or not 0 <= segment.start <= segment.end <= duration + 1):
                raise Denied('speech_segment_invalid')
            value = segment.text.strip()
            size += len(value.encode()) + bool(parts)
            if size > 2000 or len(parts) >= 200:
                raise Denied('speech_transcript_too_large')
            if value:
                parts.append(value)
        result = ' '.join(parts)
        if not result:
            raise Denied('speech_no_speech_detected')
        return {'audio_sha256': sha256(audio).hexdigest(), 'language': 'ru',
                'text': result, 'duration_seconds': duration}
