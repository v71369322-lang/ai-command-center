"""Offline review bindings; these tests never approve F1 tasks or call providers."""
from copy import deepcopy

import httpx
import pytest
from pydantic import ValidationError

from command_center.planning_admission import PlanningProfile, prepare_review, validate_review
from command_center.request_planning import PlanningContext
from command_center.store import Denied, digest

TASK = '11111111-1111-4111-8111-111111111111'


@pytest.fixture
def profile():
    return PlanningProfile.model_validate({
        'tariff': {'model': 'operator-test-model', 'input_nano_rub': 1, 'output_nano_rub': 2,
                   'context_tokens': 8192, 'max_output_tokens': 32,
                   'confirmed': True, 'evidence': 'SYNTHETIC tariff fixture'},
        'evidence': {'account': 'SYNTHETIC account', 'model': 'SYNTHETIC model',
                     'funding': 'SYNTHETIC funding', 'data_sharing': 'SYNTHETIC consent',
                     'observed_at': 100, 'expires_at': 1000},
        'available_nano_rub': 10000, 'daily_nano_rub': 10000, 'monthly_nano_rub': 10000})


@pytest.fixture
def snapshot():
    return PlanningContext(schema_version=1, request_id='a' * 64 + ':123',
        request_fingerprint='b' * 64, text='Подготовить план очереди', project_id='command-center',
        assignment_version=1, intake_revision='c' * 40, source_revision='d' * 40,
        control_epoch=26, halted=False, recovery=False)


def quote(profile, snapshot):
    return prepare_review('owner', profile, snapshot, task_id=TASK, task_version=1, now=200)


def validate(profile, snapshot, value, **changes):
    args = dict(task_id=TASK, task_version=1, now=201, expected_quote_digest=digest(value.model_dump()))
    args.update(changes)
    return validate_review('owner', profile, snapshot, value, **args)


def test_review_has_exact_bounds_and_no_io(profile, snapshot, monkeypatch):
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('provider client forbidden'))
    value = quote(profile, snapshot)
    assert value.maximum_nano_rub == 8256
    assert value.model == profile.tariff.model
    assert value.expires_at == 320
    assert value.context_digest == snapshot.binding
    assert value.max_calls == 1 and value.execution_authorized is False
    assert validate(profile, snapshot, value) == value


@pytest.mark.parametrize('field,value', [
    ('text', 'Другой запрос'), ('project_id', 'lnauto'), ('assignment_version', 2),
    ('source_revision', 'e' * 40), ('control_epoch', 27), ('halted', True), ('recovery', True),
    ('request_fingerprint', 'f' * 64), ('request_id', 'a' * 64 + ':124')])
def test_context_changes_invalidate_review(profile, snapshot, field, value):
    review = quote(profile, snapshot)
    changed = snapshot.model_copy(update={field: value})
    with pytest.raises(Denied):
        validate(profile, changed, review)


@pytest.mark.parametrize('changes', [
    {'now': 320}, {'now': 199}, {'now': True}, {'task_version': 2},
    {'task_id': '22222222-2222-4222-8222-222222222222'}, {'expected_quote_digest': 'f' * 64}])
def test_stale_or_other_task_review_rejected(profile, snapshot, changes):
    with pytest.raises(Denied):
        validate(profile, snapshot, quote(profile, snapshot), **changes)


def test_nested_tariff_mutation_and_profile_replacement_rejected(profile, snapshot):
    review = quote(profile, snapshot)
    profile.tariff.model = 'replacement-model'
    with pytest.raises(Denied):
        validate(profile, snapshot, review)
    profile.tariff.input_nano_rub = -1
    with pytest.raises(Denied):
        quote(profile, snapshot)


@pytest.mark.parametrize('path,value', [
    (('tariff', 'confirmed'), False), (('tariff', 'evidence'), '  '),
    (('available_nano_rub',), 1), (('daily_nano_rub',), 1), (('monthly_nano_rub',), 1),
    (('evidence', 'funding'), '  '), (('evidence', 'data_sharing'), ''),
    (('evidence', 'expires_at'), 100), (('evidence', 'expires_at'), 90000),
    (('project_id',), 'lnauto'), (('credential_files',), {'openai': '/tmp/secret'})])
def test_operator_evidence_fail_closed(profile, path, value):
    data = deepcopy(profile.model_dump())
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        PlanningProfile.model_validate(data)


@pytest.mark.parametrize('now,seconds', [(99, 120), (1000, 1), (900, 120), (200, 121),
                                       (200, 0), (True, 120), (200, True)])
def test_review_windows(profile, snapshot, now, seconds):
    with pytest.raises(Denied):
        prepare_review('owner', profile, snapshot, task_id=TASK, task_version=1, now=now, seconds=seconds)


@pytest.mark.parametrize('actor', ['executor', 'viewer', 'gateway'])
def test_owner_required(profile, snapshot, actor):
    with pytest.raises(Denied):
        prepare_review(actor, profile, snapshot, task_id=TASK, task_version=1, now=200)
    review = quote(profile, snapshot)
    with pytest.raises(Denied):
        validate_review(actor, profile, snapshot, review, task_id=TASK, task_version=1, now=201,
                        expected_quote_digest=digest(review.model_dump()))


def test_forged_review_rejected_even_with_matching_digest(profile, snapshot):
    review = quote(profile, snapshot).model_copy(update={'maximum_nano_rub': 1})
    with pytest.raises(Denied):
        validate(profile, snapshot, review)


@pytest.mark.parametrize('task_id,version', [('not-a-uuid', 1), (TASK.upper(), 0),
    ('11111111-1111-5111-8111-111111111111', 1), (TASK, True)])
def test_invalid_task_binding(profile, snapshot, task_id, version):
    with pytest.raises(Denied):
        prepare_review('owner', profile, snapshot, task_id=task_id, task_version=version, now=200)


def test_changed_funding_evidence_invalidates_quote(profile, snapshot):
    review = quote(profile, snapshot)
    data = profile.model_dump()
    data['evidence']['funding'] = 'replacement funding evidence'
    with pytest.raises(Denied):
        validate(PlanningProfile.model_validate(data), snapshot, review)


def test_forged_window_and_execution_fields_rejected(profile, snapshot):
    for changes in ({'expires_at': 999}, {'issued_at': 99}, {'execution_authorized': True},
                    {'max_calls': 2}, {'source_revision': 'invalid'}):
        review = quote(profile, snapshot).model_copy(update=changes)
        with pytest.raises(Denied):
            validate(profile, snapshot, review)
