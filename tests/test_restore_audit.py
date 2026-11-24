import json
import re

import pytest

from command_center.deployment import verify_restored_audit
from command_center.deployment_profile import checksum


def chain(size):
    rows, previous = [], '0' * 64
    for sequence in range(1, size + 1):
        event = {'kind': 'public_restore_fixture', 'sequence': sequence}
        value = checksum({'previous': previous, 'event': event})
        rows.append({'sequence': sequence, 'event': event, 'previous': previous, 'digest': value})
        previous = value
    return rows


@pytest.mark.parametrize('attack', [None, 'middle', 'checkpoint', 'missing', 'reorder'])
def test_restore_verifies_entire_chain_in_bounded_pages(attack):
    rows = chain(1025)
    checkpoint = {'sequence': 700, 'digest': rows[699]['digest']}
    if attack == 'middle':
        rows[600]['event']['changed'] = True
    elif attack == 'checkpoint':
        checkpoint['digest'] = '0' * 64
    elif attack == 'missing':
        rows.pop(600)
    calls = []
    def query(statement):
        calls.append(statement)
        assert 'ORDER BY sequence LIMIT 256' in statement
        after = int(re.search(r'WHERE sequence>(\d+)', statement)[1])
        page = [r for r in rows if r['sequence'] > after][:256]
        if attack == 'reorder' and page:
            page.reverse()
        return json.dumps(page)
    if attack is None:
        assert verify_restored_audit(query, checkpoint) == rows[-1]['digest']
        assert len(calls) == 6
    else:
        with pytest.raises(ValueError, match='restored_'):
            verify_restored_audit(query, checkpoint)
