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


def test_second_lost_negation_is_not_hidden_by_another_identical_one():
    result = assess('Не переноси встречу. Не переноси задачу.',
                    'Не переноси встречу. Переноси задачу.', ['не переноси'])
    assert result['missing_critical_indexes'] == [0]
    assert result['critical_phrase_counts'] == [{'reference': 2, 'transcript': 1}]
    assert result['critical_occurrence_mismatch_indexes'] == [0]


def test_inserted_critical_phrase_is_reported_without_claiming_it_was_dropped():
    result = assess('Не переноси встречу.', 'Не переноси встречу. Не переноси задачу.', ['не переноси'])
    assert result['missing_critical_indexes'] == []
    assert result['critical_phrase_counts'] == [{'reference': 1, 'transcript': 2}]
    assert result['critical_occurrence_mismatch_indexes'] == [0]


def test_overlapping_phrase_occurrences_are_counted_consistently():
    result = assess('не не не', 'не не', ['не не'])
    assert result['critical_phrase_counts'] == [{'reference': 2, 'transcript': 1}]
    assert result['missing_critical_indexes'] == [0]


def test_same_punctuation_sequence_at_wrong_word_boundary_is_not_a_match():
    result = assess('Нет, переноси встречу.', 'Нет переноси, встречу.')
    assert result['punctuation_sequence_equal'] is True
    assert result['punctuation_boundaries_equal'] is False
    assert result['requires_human_review'] is True


@pytest.mark.parametrize('value', ['Не переноси встречу.', 'Пётр: завтра в 15:30.', 'Задача; идея!'])
def test_identical_punctuation_word_boundaries_match(value):
    assert assess(value, value)['punctuation_boundaries_equal'] is True


@pytest.mark.parametrize('reference,transcript,critical', [
    ('', 'слово', []), ('слово', 'слово', ['другое']),
    ('слово', 'слово', ['']), ('я' * 1001, '', []),
])
def test_invalid_or_unbounded_references_are_rejected(reference, transcript, critical):
    with pytest.raises(ValueError):
        assess(reference, transcript, critical)
