#!/usr/bin/env python3
"""Offline mocks only, never evidence of publisher or SDK availability."""
import types
import textwrap
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT/'.github/workflows/ohos-mac-arm-publisher-probe.yml'
workflow_text = WORKFLOW.read_text()
# Execute only the one reviewed inline source in an isolated module; __main__
# never runs. Tests below inject fake responses, never make network requests.
start = "          python3 - <<'PYPROBE'\n"
end = "          PYPROBE\n"
assert workflow_text.count(start) == workflow_text.count(end) == 1
source = textwrap.dedent(workflow_text.split(start, 1)[1].split(end, 1)[0])
p = types.ModuleType('offline_probe_test')
exec(compile(source, str(WORKFLOW), 'exec'), p.__dict__)


class Response:
    def __init__(self, url, body=b'', headers=None, status=200):
        self.url, self.body, self.status = url, body, status
        self.headers = headers or {}
        self.reads = []
    def geturl(self): return self.url
    def read(self, amount):
        self.reads.append(amount)
        return self.body[:amount]
    def __enter__(self): return self
    def __exit__(self, *args): pass


class Opener:
    def __init__(self, responses): self.responses, self.calls = list(responses), []
    def open(self, request, timeout):
        self.calls.append((request.full_url, request.get_method(), timeout))
        return self.responses.pop(0)


class Tests(unittest.TestCase):
    def pair(self):
        return [Response(p.BASE+'.sha256', p.SHA), Response(p.BASE, headers={'Content-Length':p.SIZE, 'Content-Type':'application/octet-stream'})]
    def reject(self, responses, reason):
        with self.assertRaisesRegex(p.Rejected, '^'+reason+'$'):
            p.probe(Opener(responses))
    def test_success_is_only_bounded_get_and_unread_head(self):
        r = self.pair(); o = Opener(r); p.probe(o)
        self.assertEqual(o.calls, [(p.BASE+'.sha256','GET',15),(p.BASE,'HEAD',15)])
        self.assertEqual(r[0].reads,[66]); self.assertEqual(r[1].reads,[])
    def test_html_nonhex_extra_and_noncanonical_checksum(self):
        for body in (b'<html>Site Unavailable</html>', b'g'*64+b'\n',p.SHA+b'x',p.SHA.upper(),p.SHA[:-1],p.SHA[:-1]+b'\r\n'):
            with self.subTest(body=body):
                r=self.pair();r[0].body=body;self.reject(r,'checksum-noncanonical')
    def test_checksum_mismatch(self):
        r=self.pair();r[0].body=b'0'*64+b'\n';self.reject(r,'checksum-mismatch')
    def test_redirect_handler_and_changed_final_url(self):
        with self.assertRaisesRegex(p.Rejected,'redirect'):
            p.NoRedirect().redirect_request(None,None,302,None,None,'https://other.invalid/')
        for i in (0,1):
            r=self.pair();r[i].url='https://other.invalid/';self.reject(r,'redirect')
    def test_head_missing_wrong_or_unbounded_size(self):
        for value in (None,'195','1288449770','1288449768','01288449769'):
            r=self.pair()
            if value is None: del r[1].headers['Content-Length']
            else: r[1].headers['Content-Length']=value
            self.reject(r,'head-size')
    def test_head_html_or_missing_type(self):
        for value in ('text/html; charset=utf-8','', 'text/plain'):
            r=self.pair();r[1].headers['Content-Type']=value;self.reject(r,'head-type')
    def test_encoding_and_non_200(self):
        for i in (0,1):
            r=self.pair();r[i].headers['Content-Encoding']='gzip';self.reject(r,'content-encoding')
            r=self.pair();r[i].status=206;self.reject(r,'http-status')
    def test_workflow_has_single_inline_source_and_exact_trigger(self):
        workflow=WORKFLOW.read_text()
        self.assertFalse((ROOT/'scripts/probe-ohos-mac-arm-publisher.py').exists())
        self.assertNotIn('uses:',workflow)
        self.assertNotIn('secrets.',workflow)
        self.assertIn('permissions: {}',workflow)
        self.assertNotIn('workflow_dispatch:',workflow)
        self.assertIn('on:\n  push:\n    branches: [checkpoint/madlink-ohos-api20-mac-arm-publisher-probe]\n    paths: [.github/workflows/ohos-mac-arm-publisher-probe.yml]\npermissions: {}\n',workflow)
        self.assertNotIn('  pull_request:',workflow)
        self.assertIn('runs-on: macos-15',workflow)
        self.assertIn('$(/usr/bin/uname -m)\" != arm64',workflow)
        self.assertIn('$(/usr/bin/uname -s)\" != Darwin',workflow)
        self.assertLess(workflow.index('/usr/bin/uname -m'),workflow.index(start))
        self.assertEqual(p.BASE,'https://repo.huaweicloud.com/openharmony/os/6.0-Release/L2-SDK-MAC-M1-PUBLIC.tar.gz')
        self.assertEqual(p.SIZE,'1288449769')
        self.assertEqual(p.SHA,b'd4b0c942cbc8dfc7f28f49c0f33648f332d43c3a51399f2463655c2ef1f2c659\n')

if __name__ == '__main__': unittest.main()
