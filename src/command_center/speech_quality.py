"""Local evaluation helpers, never an action-authority or ASR confidence score."""

import re
import unicodedata


def words(value):
    if not isinstance(value, str) or len(value.encode('utf-8')) > 2000:
        raise ValueError('speech_evaluation_text_invalid')
    return re.findall(r'\w+', unicodedata.normalize('NFC', value).casefold().replace('ё', 'е'))


def assess(reference, transcript, critical_phrases=()):
    """Lexical comparison only: dates written as digits/words need human review.

    Critical phrases are operator-labelled reference spans, not inferred entities.
    A low WER must never hide a dropped negation or a changed date.
    No return value grants permission to create a task/calendar event.
    """
    expected, actual = words(reference), words(transcript)
    if not expected or not isinstance(critical_phrases, (list, tuple)) or len(critical_phrases) > 32:
        raise ValueError('speech_evaluation_reference_invalid')

    def occurrences(tokens, phrase):
        return sum(tokens[start:start + len(phrase)] == phrase
                   for start in range(len(tokens) - len(phrase) + 1))

    missing, counts = [], []
    for index, phrase in enumerate(critical_phrases):
        tokens = words(phrase)
        expected_count = occurrences(expected, tokens) if tokens else 0
        if not expected_count:
            raise ValueError('speech_evaluation_critical_reference_invalid')
        actual_count = occurrences(actual, tokens)
        counts.append({'reference': expected_count, 'transcript': actual_count})
        if actual_count < expected_count:
            missing.append(index)

    previous = list(range(len(actual) + 1))
    for index, token in enumerate(expected, 1):
        current = [index]
        for offset, candidate in enumerate(actual, 1):
            current.append(min(current[-1] + 1, previous[offset] + 1,
                               previous[offset - 1] + (token != candidate)))
        previous = current
    def punctuation_boundaries(value):
        boundary, result = 0, []
        for token in re.findall(r'\w+|[^\w\s]', unicodedata.normalize('NFC', value)):
            if re.fullmatch(r'\w+', token):
                boundary += 1
            else:
                result.append((boundary, token))
        return result

    return {'word_edits': previous[-1], 'reference_words': len(expected),
            'word_error_rate': previous[-1] / len(expected),
            'missing_critical_indexes': missing,
            'critical_phrase_counts': counts,
            'critical_occurrence_mismatch_indexes': [i for i, c in enumerate(counts)
                                                     if c['reference'] != c['transcript']],
            'punctuation_sequence_equal': re.findall(r'[^\w\s]', reference) == re.findall(r'[^\w\s]', transcript),
            'punctuation_boundaries_equal': punctuation_boundaries(reference) == punctuation_boundaries(transcript),
            'requires_human_review': True}
