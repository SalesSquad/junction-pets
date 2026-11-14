#!/usr/bin/env python3
"""Focused protocol tests. FACTORY_CHECKOUT must name the pinned external repo."""
import importlib.util
import os
import sys
from types import ModuleType
from unittest import mock
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('lens_evaluate', Path(__file__).with_name('evaluate.py'))
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def fixture():
    text = 'SYNTHETIC fixture: uncertain step observation; no personal data.'
    request = {'schema': 'factory.decision-assist-request/v1', 'task_id': 'lens-parser-fixture',
               'source_sha256': harness.sha256(text.encode()), 'input': text,
               'questions': [{'name': 'route', 'instructions': 'Choose a bounded advisory route.',
                              'choices': [{'value': 'first', 'description': 'Temporary episode.'},
                                          {'value': 'second', 'description': 'Insufficient evidence.'}]}]}
    return {'schema': 'lens.learning-evaluation-suite/v1', 'evidenceMode': 'SYNTHETIC',
            'source': {'baseCommit': '9e1915827fabff9836dac217ab69727e514acc49',
                       'files': {'synthetic-fixture': request['source_sha256']}},
            'cases': [{'id': 'parser-case', 'request': request,
                       'expected': {'route': ['second']}, 'domain': {'hiddenMarker': 'DOMAIN-NOT-SENT'}}]}


class ProviderProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.environ.get('FACTORY_CHECKOUT')
        if not root:
            raise RuntimeError('FACTORY_CHECKOUT required: these tests use the real pinned parser')
        cls.adapter, cls.pin = harness.load_adapter(root)

    def test_offline_actual_parsers_do_not_read_keys_or_expected(self):
        original = self.adapter.load_key
        def denied(_):
            raise AssertionError('offline credential read')
        self.adapter.load_key = denied
        try:
            report = harness.evaluate_suite(fixture(), self.adapter, self.pin)
        finally:
            self.adapter.load_key = original
        self.assertEqual(report['providerAttempts'], 0)
        self.assertEqual(report['simulatedTransports'], 2)
        self.assertEqual(report['errors'], 0)
        for row in report['results']:
            self.assertEqual(row['receipt']['answers'][0]['choice'], 'first')
            self.assertFalse(row['labelComparison'][0]['allowed'])
            self.assertIsNone(row['receipt']['usage'])
            self.assertEqual(row['responseOrigin'], 'SIMULATED_TRANSPORT')
            wire = self.adapter.wire_request(row['provider'], fixture()['cases'][0]['request'])
            self.assertNotIn(b'DOMAIN-NOT-SENT', harness.canonical(wire))
            self.assertNotIn(b'expected', harness.canonical(wire))

    def test_whole_suite_admission_and_source_binding(self):
        bad = fixture()
        bad['cases'][0]['request']['source_sha256'] = '0' * 64
        with self.assertRaises(harness.HarnessError):
            harness.evaluate_suite(bad, self.adapter, self.pin)
        bad = fixture()
        bad['cases'] *= 9
        with self.assertRaises(harness.HarnessError):
            harness.evaluate_suite(bad, self.adapter, self.pin)

    def test_actual_parser_preserves_refusal_and_rejects_malformed(self):
        request = fixture()['cases'][0]['request']
        refused = {'model': 'gpt-6-luna', 'answers': [{'name': 'route', 'type': 'refusal', 'refusal': 'untrusted text'}],
                   'usage': {'input_tokens': 1, 'output_tokens': 0}}
        normalized = self.adapter.normalize_response('openai', request, refused)
        self.assertEqual(normalized['status'], 'refused')
        self.assertNotIn('refusal', normalized['answers'][0])
        for provider in ('jev', 'openai'):
            wire = self.adapter.wire_request(provider, request)
            response = harness.strict_json(harness.simulated_response(provider, wire))
            response['model'] = 'wrong-model'
            with self.assertRaises(Exception):
                self.adapter.normalize_response(provider, request, response)

    def test_https_deferred_import_reaches_dns_boundary_without_network(self):
        import importlib
        import threading
        import time
        from types import SimpleNamespace
        deadline = importlib.import_module('factory_os.deadline')
        gateway = importlib.import_module('factory_os.model_gateway')
        original = deadline.bounded_bytes
        reached = []
        def synthetic_dns(target, args, **kwargs):
            reached.append(args)
            return b'[]'
        deadline.bounded_bytes = synthetic_dns
        try:
            lease = SimpleNamespace(deadline=time.time() + 1, revoked=threading.Event())
            stream = gateway.ModelGateway._https(self.adapter._AdvisoryHttps(),
                        'api.typesafe.ai', '/v1/systemone', {}, b'{}', lease)
            with self.assertRaisesRegex(Exception, 'gateway_dns_unavailable'):
                next(stream)
        finally:
            deadline.bounded_bytes = original
        self.assertEqual(reached, [('api.typesafe.ai',)])

    def test_unknown_delivery_is_not_retried(self):
        request = fixture()['cases'][0]['request']
        calls = []
        def uncertain(provider, payload, key):
            calls.append(provider)
            raise KeyboardInterrupt('synthetic process interruption')
        with tempfile.TemporaryDirectory() as state:
            with self.assertRaises(KeyboardInterrupt):
                self.adapter.evaluate('jev', request, state_dir=state, live=True,
                                      transport=uncertain, key_reader=lambda _: 'SYNTHETIC-NO-CREDENTIAL')
            result = self.adapter.evaluate('jev', request, state_dir=state, live=True,
                                          transport=uncertain, key_reader=lambda _: 'SYNTHETIC-NO-CREDENTIAL')
        self.assertEqual(result['status'], 'indeterminate')
        self.assertTrue(result['replayed'])
        self.assertEqual(calls, ['jev'])


class SourceOriginGuard(unittest.TestCase):
    def test_shadow_extra_and_escaped_project_modules_are_rejected(self):
        for mode in ('shadow-deferred-module', 'extra-outside-module', 'symlink-escape'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                root, outside = folder / 'factory', folder / 'outside.py'
                outside.write_text('# synthetic origin fixture\n')
                relatives = ('tools/factory_os/__init__.py',
                             'tools/factory_os/decision_assist.py',
                             'tools/factory_os/deadline.py')
                for relative in relatives:
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(outside.read_bytes())
                if mode == 'symlink-escape':
                    (root / relatives[-1]).unlink()
                    (root / relatives[-1]).symlink_to(outside)
                hashes = {relative: harness.sha256((root / relative).read_bytes())
                          for relative in relatives}
                manifest = {'factory': {'commit': '1' * 40,
                            'adapterPath': relatives[1], 'moduleHashes': hashes}}
                (folder / 'provider-sources.json').write_bytes(harness.canonical(manifest))
                expected = {relative.split('/', 1)[1].removesuffix('.py')
                            .replace('/', '.').removesuffix('.__init__'): root / relative
                            for relative in relatives}
                def imported(name):
                    module = ModuleType(name)
                    path = expected[name]
                    if mode == 'shadow-deferred-module' and name == 'factory_os.deadline':
                        path = outside
                    module.__file__ = str(path)
                    sys.modules[name] = module
                    if mode == 'extra-outside-module':
                        extra = ModuleType('factory_kernel.surprise')
                        extra.__file__ = str(outside)
                        sys.modules[extra.__name__] = extra
                    return module
                with mock.patch.dict(sys.modules, sys.modules.copy(), clear=True), \
                        mock.patch.object(harness, 'HERE', folder), \
                        mock.patch.object(harness.importlib, 'import_module', side_effect=imported), \
                        mock.patch.object(sys, 'path', sys.path.copy()):
                    for name in list(sys.modules):
                        if name.split('.')[0] in {'factory_os', 'factory_kernel'}:
                            del sys.modules[name]
                    with self.assertRaises(harness.HarnessError):
                        harness.load_adapter(root)


if __name__ == '__main__':
    unittest.main()
