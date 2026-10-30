import json
from uuid import uuid4

import pytest

from command_center.coding.contract import CodingRequest
from command_center.coding.external_execution import apply_proposals
from command_center.coding.http_contract import decode_response, request_document
from command_center.coding.spec import BASE_SHA, CORRECT, FIRST, INITIAL, OBJECTIVE, REPOSITORY, TEST_SOURCE
from command_center.coding.verification import inspect_result, replay


MODEL = 'fixture-model'
LOOP = ('def sum_positive(values):\n    total = 0\n    for value in values:\n'
        '        if value > 0:\n            total += value\n    return total\n')


def document():
    return request_document({'repository': REPOSITORY, 'objective': OBJECTIVE, 'base_sha': BASE_SHA,
                             'source': INITIAL, 'acceptance': TEST_SOURCE, 'checks': None, 'attempt': 1},
                            MODEL, 2048)


def response(source):
    return {'id': 'resp_public_fixture', 'model': MODEL, 'status': 'completed',
            'usage': {'input_tokens': 100, 'output_tokens': 32, 'total_tokens': 132},
            'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': json.dumps({'source': source})}]}]}


def test_provider_schema_excludes_unexecutable_forms_before_generation():
    body = document()
    schema = body['text']['format']
    assert schema['strict'] is True
    assert schema['schema']['properties']['source']['enum'] == [FIRST, CORRECT]
    assert LOOP not in schema['schema']['properties']['source']['enum']
    assert INITIAL not in schema['schema']['properties']['source']['enum']
    assert schema['schema']['additionalProperties'] is False
    assert schema['schema']['required'] == ['source']
    assert body['store'] is False and body['service_tier'] == 'default'


@pytest.mark.parametrize('source', [FIRST, CORRECT])
def test_every_schema_choice_reaches_existing_independent_checks(tmp_path, source):
    choices = document()['text']['format']['schema']['properties']['source']['enum']
    assert source in choices
    changes, _ = decode_response(response(source), MODEL)
    task_id = str(uuid4())
    coding = CodingRequest(provider='openai').model_dump()
    result = apply_proposals({'operation_id': task_id, 'fence': 1, 'coding': coding,
                              'proposals': [changes]}, tmp_path / 'repository')
    report, _, _ = inspect_result(result, task_id, 1, coding, allow_incomplete=True)
    assert report['passed'] is (source == CORRECT)
    if source == CORRECT:
        assert replay(result, task_id, 1, coding, tmp_path / 'verification') == report


@pytest.mark.parametrize('source', [LOOP, INITIAL, 'import os\n' + CORRECT,
                                   CORRECT.replace('value', 'number')])
def test_nonconforming_provider_response_still_cannot_bypass_allowlist(source):
    with pytest.raises(ValueError, match='synthetic_language_scope_violation'):
        decode_response(response(source), MODEL)


def test_request_schema_is_private_to_each_request():
    first = document()
    first['text']['format']['schema']['properties']['source']['enum'].append(LOOP)
    first['text']['format']['schema']['additionalProperties'] = True
    second = document()['text']['format']['schema']
    assert second['properties']['source']['enum'] == [FIRST, CORRECT]
    assert second['additionalProperties'] is False
