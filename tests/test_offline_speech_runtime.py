"""Real audio decoding; run explicitly in the speech dependency environment."""
from io import BytesIO
import wave

import pytest

from command_center.offline_speech import decode_audio
from command_center.store import Denied

pytest.importorskip('av', reason='optional speech runtime; separate speech CI job')


def wav(seconds, rate=8000):
    output = BytesIO()
    with wave.open(output, 'wb') as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(b'\x00\x00' * (seconds * rate))
    return output.getvalue()


def test_real_decoder_resamples_bounded_audio_to_mono_16khz():
    result = decode_audio(wav(2))
    assert len(result) == 32000 and result.dtype.name == 'float32'
    assert not result.any()


def test_compressed_size_is_not_a_substitute_for_actual_duration_limit():
    with pytest.raises(Denied, match='duration_invalid'):
        decode_audio(wav(121))


def test_invalid_audio_and_empty_payload_fail_closed():
    for audio in (b'not an audio file', b''):
        with pytest.raises(Denied):
            decode_audio(audio)
