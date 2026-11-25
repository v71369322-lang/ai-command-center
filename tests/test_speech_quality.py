import pytest

from command_center.speech_quality import assess


def test_low_average_error_does_not_hide_dropped_negation():
    result = assess('Пожалуйста не переноси встречу с поставщиком завтра утром',
                    'Пожалуйста переноси встречу с поставщиком завтра утром', ['не'])
    assert result['word_error_rate'] < .2
    assert result['missing_critical_indexes'] == [0]
    assert result['requires_human_review'] is True


def test_changed_time_and_name_are_independently_flagged():
    result = assess('Анна завтра в 15:30', 'Антон завтра в 16:30', ['Анна', '15:30'])
    assert result['missing_critical_indexes'] == [0, 1]


def test_punctuation_is_not_word_accuracy_and_case_is_ignored():
    result = assess('Завтра, Пётр.', 'завтра петр', ['Пётр'])
    assert result['word_error_rate'] == 0
    assert result['punctuation_sequence_equal'] is False
    assert result['missing_critical_indexes'] == []


def test_critical_match_uses_whole_words():
    assert assess('не нужно', 'необходимо', ['не'])['missing_critical_indexes'] == [0]


def test_insertions_can_exceed_one_hundred_percent():
    assert assess('идея', 'новая полезная важная идея')['word_error_rate'] == 3


def test_perfect_lexical_match_is_never_action_permission():
    result = assess('Встреча завтра.', 'Встреча завтра.', ['завтра'])
    assert result['word_error_rate'] == 0
    assert result['requires_human_review'] is True


@pytest.mark.parametrize('reference,transcript,critical', [
    ('', 'слово', []), ('слово', 'слово', ['другое']),
    ('слово', 'слово', ['']), ('я' * 1001, '', []),
])
def test_invalid_or_unbounded_references_are_rejected(reference, transcript, critical):
    with pytest.raises(ValueError):
        assess(reference, transcript, critical)
