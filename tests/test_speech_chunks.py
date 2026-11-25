import pytest

from command_center.speech_chunks import chunk_ranges


def test_silence_boundary_keeps_all_samples_once_including_pauses():
    ranges = chunk_ranges(40 * 16000, [
        {'start': 0, 'end': 12 * 16000}, {'start': 13 * 16000, 'end': 26 * 16000},
        {'start': 27 * 16000, 'end': 40 * 16000}])
    assert ranges[0]['end'] == int(12.5 * 16000)
    assert ranges[0]['hard_boundary'] is False
    assert ranges[0]['start'] == 0 and ranges[-1]['end'] == 40 * 16000
    assert all(a['end'] == b['start'] for a, b in zip(ranges, ranges[1:]))
    assert all(0 < x['end'] - x['start'] <= 15 * 16000 for x in ranges)
    assert sum(x['end'] - x['start'] for x in ranges) == 40 * 16000


def test_no_pause_uses_bounded_hard_boundary_without_deduplicating_words():
    ranges = chunk_ranges(120 * 16000, [{'start': 0, 'end': 120 * 16000}])
    assert len(ranges) == 8
    assert all(x['hard_boundary'] for x in ranges[:-1])
    assert ranges[-1]['hard_boundary'] is False
    assert sum(x['end'] - x['start'] for x in ranges) == 120 * 16000


def test_short_clip_is_not_resegmented():
    assert chunk_ranges(16000, [{'start': 0, 'end': 16000}]) == [
        {'start': 0, 'end': 16000, 'hard_boundary': False}]


@pytest.mark.parametrize('count,speech', [
    (0, []), (120 * 16000 + 1, []), (True, []),
    (10000, [{'start': 1, 'end': 10001}]),
    (10000, [{'start': 100, 'end': 99}]),
    (10000, [{'start': 0, 'end': 900}, {'start': 800, 'end': 1000}]),
    (10000, [{'start': 0, 'end': 100, 'command': 'discard'}]),
])
def test_invalid_vad_cannot_drop_or_replace_audio(count, speech):
    with pytest.raises(ValueError):
        chunk_ranges(count, speech)
