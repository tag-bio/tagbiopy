"""Unit tests for the '/t' protocol-run flow (mocked wire; no network)."""
import json
from unittest import mock

import pytest

from tagbiopy.run_protocol import TRequest, ProtocolRunError, ProtocolRunTimeout


def make_treq():
    return TRequest(fc_name='fc-test', host='https://demo.tag.bio', api_key='a@b.co:0000')


def fake_post(bodies):
    """requests.post replacement yielding canned JSON bodies in order."""
    it = iter(bodies)

    def _post(url, **kwargs):
        resp = mock.Mock()
        body = next(it)
        resp.json.return_value = body
        resp.content = json.dumps(body).encode()
        resp.status_code = 200
        resp.headers = {}
        _post.calls.append(json.loads(kwargs['data']))
        return resp
    _post.calls = []
    return _post


FINAL = {'method': 'variable_summary', 'results': [{'ok': True}], 'protocol_instance': {'name': 'x'}}
PROGRESS = {'token': 'T1', 'total': 10, 'count': 3, 'message': 'working', 'results_next': False}
READY = {'token': 'T1', 'total': 10, 'count': 10, 'message': 'done', 'results_next': True}


def test_immediate_final_result():
    t = make_treq()
    with mock.patch('tagbiopy.request.requests.post', fake_post([FINAL])):
        out = t.run({'name': 'x', 'arguments': {}})
    assert out == FINAL


def test_poll_then_results():
    t = make_treq()
    post = fake_post([PROGRESS, READY, FINAL])
    with mock.patch('tagbiopy.request.requests.post', post):
        out = t.run({'name': 'x', 'arguments': {}}, poll_interval=0)
    assert out == FINAL
    # wire shapes: submit, status poll, results fetch
    assert post.calls[0]['protocol_instance'] == {'name': 'x', 'arguments': {}}
    assert post.calls[1] == {'token': 'T1', 'use_cache': True}
    assert post.calls[2]['results_next_received'] is True
    assert post.calls[2]['token'] == 'T1'


def test_error_string_raises():
    t = make_treq()
    with mock.patch('tagbiopy.request.requests.post', fake_post(['boom: bad args'])):
        with pytest.raises(ProtocolRunError, match='boom'):
            t.run({'name': 'x', 'arguments': {}})


def test_timeout_carries_token():
    t = make_treq()
    post = fake_post([PROGRESS, PROGRESS, PROGRESS])
    with mock.patch('tagbiopy.request.requests.post', post):
        with pytest.raises(ProtocolRunTimeout) as e:
            t.run({'name': 'x', 'arguments': {}}, poll_interval=0, timeout=0)
    assert e.value.token == 'T1'


def test_kill_payload():
    t = make_treq()
    post = fake_post([{}])
    with mock.patch('tagbiopy.request.requests.post', post):
        t.kill('T9')
    assert post.calls[0] == {'token': 'T9', 'kill': True}


def test_fc_run_protocol_validates_names():
    from tagbiopy.fc import FC
    fc = FC(fc_name='fc-test', host='https://demo.tag.bio', api_key='a@b.co:0000')
    definition = {'argument_sets': [{'arguments': [
        {'argument_definition': {'name': 'drug_name'}}]}]}
    with mock.patch.object(type(fc), 'get_protocol', return_value=definition):
        with mock.patch('tagbiopy.run_protocol.TRequest.run', return_value=FINAL) as run:
            out = fc.run_protocol('p1', {'drug_name': ['EYLEA']})
            assert out == FINAL
            assert run.call_args.args[0] == {'name': 'p1', 'arguments': {'drug_name': ['EYLEA']}}
        with pytest.raises(ValueError, match='unknown argument'):
            fc.run_protocol('p1', {'nope': 1})
