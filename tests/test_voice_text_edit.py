import pytest

from command_center.voice_text_edit import replace_once


@pytest.mark.parametrize('instruction', [
    'Замени «Аня» на «Анна»',
    'замени "Аня" на "Анна".',
    'ЗАМЕНИ “Аня” на “Анна”',
    '  Замени «Аня» на "Анна"  ',
])
def test_literal_fragment_preserves_every_surrounding_character(instruction):
    assert replace_once(instruction, 'Не переноси: Аня, 09:15. Ещё задача.') == 'Не переноси: Анна, 09:15. Ещё задача.'


@pytest.mark.parametrize('original', ['Анна', 'Аня и Аня', 'АняАня'])
def test_missing_or_repeated_fragment_is_refused(original):
    with pytest.raises(ValueError, match='not_unique'):
        replace_once('Замени «Аня» на «Анна»', original)


def test_overlapping_occurrences_are_ambiguous():
    with pytest.raises(ValueError, match='not_unique'):
        replace_once('Замени «аа» на «б»', 'ааа')


@pytest.mark.parametrize('instruction', [
    'Замени Аня на Анна', 'Замени «» на «Анна»', 'Замени «Аня» на « »',
    'Замени «Аня» на «Анна» и сохрани', 'Замени «Аня» на «Анна»; удали встречу',
    'Замени «Аня» на «Анна»\nЗамени «9» на «10»',
])
def test_malformed_or_multiple_instruction_is_refused(instruction):
    with pytest.raises(ValueError, match='format'):
        replace_once(instruction, 'Аня')


def test_plain_full_text_and_control_strings_remain_data():
    for value in ['Полный исправленный текст.', '/stop', 'Слово замени здесь — часть текста.']:
        assert replace_once(value, 'Исходный текст') is None


def test_replacement_is_literal_not_regex_or_execution():
    assert replace_once('Замени «a.b» на «/stop»', 'Не a.b, а axb.') == 'Не /stop, а axb.'
