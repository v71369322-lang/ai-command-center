"""Explicit list structure, not semantic AI or speech recognition acceptance."""
from datetime import datetime, timezone

import pytest

from command_center.mixed_inbox import enumeration, item_content, multiple_requests
from command_center.mixed_review import items_for

NOW = datetime(2026, 11, 28, 9, tzinfo=timezone.utc)
SCHEDULE = {'configured': True, 'timezone': 'Europe/Moscow'}


@pytest.mark.parametrize('value', [
    'Первое купить упаковку. Второе идея: новая коробка. Третье напомни завтра в 9:15 позвонить.',
    'первое купить упаковку и второе идея: новая коробка и третье напомни завтра в 9:15 позвонить',
    '  Первое: купить упаковку. Второе: идея: новая коробка. Третье: напомни завтра в 9:15 позвонить.',
    '1. Купить упаковку.\n2. Идея: новая коробка.\n3. Напомни завтра в 9:15 позвонить.',
    '  1) Купить упаковку.\n  2) Идея: новая коробка.\n  3) Напомни завтра в 9:15 позвонить.',
])
def test_list_is_literal_complete_and_needs_each_review_click(value):
    assert multiple_requests(value)
    items = items_for(value, NOW, SCHEDULE, NOW)
    assert len(items) == 3
    assert ''.join(value[x['start']:x['end']] for x in items) == value
    assert [x['document']['category'] for x in items] == ['task', 'idea', 'reminder']
    assert items[0]['document']['title'].strip('. ') == 'Купить упаковку' or items[0]['document']['title'].strip('. ') == 'купить упаковку'
    assert items[1]['document']['title'].strip('. ') == 'новая коробка'
    assert items[2]['document']['due_at'] == '2026-11-29T09:15:00+03:00'
    assert all(not x['document']['title'].lower().startswith(('первое', 'второе', 'третье', '1.', '2.')) for x in items)


@pytest.mark.parametrize('value', [
    'Первое декабря купить упаковку, второе декабря позвонить.',
    'Первое место занял Иван, второе место заняла Анна.',
    'Первое купить упаковку. Третье проверить склад.',
    'Первое купить упаковку. Второе проверить склад. Второе позвонить.',
    'Второе купить упаковку. Третье проверить склад.',
    '1. Купить упаковку.\n3. Проверить склад.',
    '1. Купить упаковку. 2. Проверить склад.',
    '1.12 купить упаковку.\n2.12 проверить склад.',
    '9:15 купить упаковку.\n10:15 проверить склад.',
    'Заметка: «первое купить упаковку второе проверить склад».',
    'Заметка: "1. Купить упаковку.\n2. Проверить склад."',
    '«Пример» Первое купить упаковку. Второе проверить склад.',
    'Это пример. Первое купить упаковку. Второе проверить склад.',
    'Первое купить упаковку.\n2. Проверить склад.',
    'Первое купить упаковку.',
])
def test_dates_rankings_quotes_invalid_or_incomplete_sequences_are_not_enumeration(value):
    assert not enumeration(value)
    assert item_content(value, 0, len(value)) == value


def test_no_ninth_point_truncation_and_all_eight_are_preserved():
    value = '\n'.join(f'{i}. Купить коробку {i}.' for i in range(1, 9))
    assert len(items_for(value, NOW, SCHEDULE, NOW)) == 8
    too_many = value + '\n9. Купить коробку 9.'
    assert not enumeration(too_many)
    assert items_for(too_many, NOW, SCHEDULE, NOW) == []


@pytest.mark.parametrize('tail', ['не отправить письмо.', 'создай встречу завтра.',
                                  'напомни в среду позвонить.', 'напомни завтра в 9 часов 75 минут позвонить.'])
def test_unsafe_item_keeps_literal_text_without_a_save_document(tail):
    value = 'Первое купить упаковку. Второе ' + tail
    items = items_for(value, NOW, SCHEDULE, NOW)
    assert len(items) == 2 and items[0]['document'] and items[1]['document'] is None
    assert ''.join(value[x['start']:x['end']] for x in items) == value


def test_quoted_ordinals_inside_item_do_not_split_it():
    value = 'Первое сохрани заметку: «второе купить пример». Второе купить упаковку.'
    assert len(items_for(value, NOW, SCHEDULE, NOW)) == 2


def test_original_receipt_time_and_existing_project_hint_are_reused():
    value = 'Первое проверить склад по автосервису. Второе напомни завтра в 9:15 позвонить.'
    later = datetime(2026, 11, 29, 4, tzinfo=timezone.utc)
    items = items_for(value, NOW, SCHEDULE, later)
    assert items[0]['project_id'] == 'lnauto'
    assert items[1]['document']['due_at'] == '2026-11-29T09:15:00+03:00'


@pytest.mark.parametrize('value', [
    'Первое купить «второе купить пример',
    'Первое купить "второе купить пример',
    'Первое купить коробку». Второе проверить склад.',
    'Первое купить упаковку. Идея: вложить листовку. Второе проверить склад.',
    'Первое задача: купить упаковку. Идея: вложить листовку. Второе проверить склад.',
])
def test_incomplete_quotes_or_extra_unlabelled_requests_do_not_gain_enumeration(value):
    assert not enumeration(value)


def test_nested_quoted_ordinals_are_data():
    value = 'Первое сохрани заметку: «пример «внутри» второе купить пример». Второе купить коробку.'
    items = items_for(value, NOW, SCHEDULE, NOW)
    assert len(items) == 2 and items[0]['document']['category'] == 'note'
    assert 'второе купить пример' in items[0]['document']['title']


@pytest.mark.parametrize('quote', ['«второе купить пример»', '“второе купить пример”',
                                  '"второе купить пример"', "'второе купить пример'"])
def test_quoted_instruction_is_never_the_second_list_item(quote):
    value = 'Первое сохрани заметку: ' + quote
    assert not enumeration(value)


@pytest.mark.parametrize('fourth', ['четвёртое', 'четвертое'])
def test_spoken_eight_item_bound_including_yo_variant(fourth):
    labels = ['первое', 'второе', 'третье', fourth, 'пятое', 'шестое', 'седьмое', 'восьмое']
    value = ' '.join(label + ' купить упаковку.' for label in labels)
    assert len(items_for(value, NOW, SCHEDULE, NOW)) == 8
    assert not enumeration(value + ' Девятое купить коробку.')
