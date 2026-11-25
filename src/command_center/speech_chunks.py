"""Bound speech inference without discarding or overlapping input samples."""


def chunk_ranges(sample_count, speech, *, maximum=15 * 16000, lookback=5 * 16000):
    if (type(sample_count) is not int or not 0 < sample_count <= 120 * 16000
            or type(maximum) is not int or not 16000 <= maximum <= 15 * 16000
            or type(lookback) is not int or not 0 <= lookback < maximum
            or not isinstance(speech, list) or len(speech) > 1000):
        raise ValueError('speech_chunk_bounds_invalid')
    gaps, previous = [], 0
    for segment in speech:
        if (not isinstance(segment, dict) or set(segment) != {'start', 'end'}
                or type(segment['start']) is not int or type(segment['end']) is not int
                or not previous <= segment['start'] < segment['end'] <= sample_count):
            raise ValueError('speech_chunk_vad_invalid')
        if previous < segment['start']:
            gaps.append((previous, segment['start']))
        previous = segment['end']
    if previous < sample_count:
        gaps.append((previous, sample_count))
    result, start = [], 0
    while start < sample_count:
        end = min(start + maximum, sample_count)
        hard_boundary = end < sample_count
        if hard_boundary:
            # Use the latest sufficiently long pause near the inference limit.
            candidates = [(max(a, end - lookback), min(b, end)) for a, b in gaps]
            candidates = [(a, b) for a, b in candidates if b - a >= 1600]
            if candidates:
                a, b = candidates[-1]
                end = (a + b) // 2
                hard_boundary = False
        result.append({'start': start, 'end': end, 'hard_boundary': hard_boundary})
        start = end
    return result
