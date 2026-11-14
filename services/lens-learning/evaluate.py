#!/usr/bin/env python3
"""Evaluate synthetic Lens cases through an external, pinned Factory adapter.

Offline responses exercise serialization/parser plumbing, never model accuracy.
Expected labels and domain observations never enter provider payloads.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
MAX_SUITE_BYTES = 262144
MAX_CASES = 8


class HarnessError(ValueError):
    pass


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise HarnessError('duplicate_json_key')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(HarnessError('nonfinite_json')))


def load_adapter(root):
    root = Path(root).resolve()
    source = strict_json((HERE / 'provider-sources.json').read_bytes())
    pin = source['factory']
    head, changed = None, ''
    if (root / '.git').exists():
        try:
            head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL, text=True).strip()
            changed = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--', *pin['moduleHashes']], stderr=subprocess.DEVNULL, text=True)
        except (OSError, subprocess.CalledProcessError):
            raise HarnessError('factory_checkout_unavailable') from None
        if len(head) != 40 or any(c not in '0123456789abcdef' for c in head):
            raise HarnessError('invalid_executor_commit')
    # An external source snapshot is admitted by exact transitive module bytes,
    # never by an invented Git revision. Any Git checkout must also be clean.
    if changed:
        raise HarnessError('factory_adapter_package_dirty')
    origins, declared_paths = {}, set()
    for relative, expected in pin['moduleHashes'].items():
        declared = Path(relative)
        if declared.is_absolute() or '..' in declared.parts:
            raise HarnessError('invalid_factory_manifest_path')
        resolved = (root / declared).resolve()
        if not resolved.is_relative_to(root):
            raise HarnessError('factory_manifest_path_escape')
        if sha256(resolved.read_bytes()) != expected:
            raise HarnessError('factory_module_hash_mismatch')
        name = relative.split('/', 1)[1].removesuffix('.py').replace('/', '.')
        name = name.removesuffix('.__init__')
        if name in origins:
            raise HarnessError('duplicate_factory_module')
        origins[name] = resolved
        declared_paths.add(resolved)
    # These two pinned wrappers replace sys.modules with the declared canonical
    # kernel module. Both wrapper and target source bytes were checked above.
    aliases = {'factory_os.common': 'factory_kernel.common',
               'factory_os.secure_fs': 'factory_kernel.secure_fs'}
    runtime_origins = dict(origins)
    for alias, target in aliases.items():
        if alias in origins:
            if target not in origins:
                raise HarnessError('unmanifested_factory_alias_target')
            runtime_origins[alias] = origins[target]
    if 'factory_os.decision_assist' not in origins or origins['factory_os.decision_assist'] != (root / pin['adapterPath']).resolve():
        raise HarnessError('unmanifested_factory_adapter')
    if any(name.split('.')[0] in {'factory_os', 'factory_kernel'} for name in sys.modules):
        raise HarnessError('factory_package_already_imported')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root / 'tools'))
    # Eager admission includes deferred HTTPS imports before credentials or a
    # paid attempt. An outside-root module cannot satisfy a manifested name.
    for name, expected_origin in runtime_origins.items():
        module = importlib.import_module(name)
        filename = getattr(module, '__file__', None)
        if not filename or Path(filename).resolve() != expected_origin:
            raise HarnessError('factory_import_mismatch')
    adapter = sys.modules['factory_os.decision_assist']
    for name, module in list(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        if name.split('.')[0] in {'factory_os', 'factory_kernel'}:
            expected_origin = runtime_origins.get(name)
            if expected_origin is None:
                raise HarnessError('unmanifested_factory_import')
            if not filename or Path(filename).resolve() != expected_origin:
                raise HarnessError('factory_import_mismatch')
        if filename and Path(filename).resolve().is_relative_to(root):
            if Path(filename).resolve() not in declared_paths:
                raise HarnessError('unmanifested_factory_import')
    return adapter, {**pin, 'executorCommit': head, 'sourceQualification': 'all_imported_project_modules_match_pinned_bytes'}


def validate_suite(suite, adapter):
    if not isinstance(suite, dict) or set(suite) != {'schema', 'evidenceMode', 'source', 'cases'} or suite['schema'] != 'lens.learning-evaluation-suite/v1' or suite['evidenceMode'] != 'SYNTHETIC':
        raise HarnessError('invalid_suite')
    source = suite['source']
    if not isinstance(source, dict) or set(source) != {'baseCommit', 'files'} or not isinstance(source['baseCommit'], str) or len(source['baseCommit']) != 40 or any(c not in '0123456789abcdef' for c in source['baseCommit']):
        raise HarnessError('invalid_suite_source')
    if not isinstance(source['files'], (list, dict)) or not source['files']:
        raise HarnessError('missing_suite_source_files')
    cases = suite['cases']
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise HarnessError('case_budget')
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {'id', 'request', 'expected', 'domain'} or not isinstance(case['id'], str) or not case['id'] or len(case['id']) > 64 or case['id'] in ids:
            raise HarnessError('invalid_case')
        ids.add(case['id'])
        request = case['request']
        adapter.validate_request(request, profile='standard')
        if request['source_sha256'] != sha256(request['input'].encode('utf-8')):
            raise HarnessError('case_source_hash_mismatch')
        if len(request['questions']) > 3:
            raise HarnessError('case_question_budget')
        expected = case['expected']
        if not isinstance(expected, dict) or set(expected) != {q['name'] for q in request['questions']}:
            raise HarnessError('expected_question_mismatch')
        for question in request['questions']:
            values = expected[question['name']]
            options = {x['value'] for x in question['choices']}
            if not isinstance(values, list) or not values or any(not isinstance(x, str) or x not in options for x in values) or len(set(values)) != len(values):
                raise HarnessError('invalid_expected_choice')
    return suite


def simulated_response(provider, payload):
    """Protocol fixture: always choose the first declared option, without labels."""
    answers = {} if provider == 'jev' else []
    questions = payload['questions'].items() if provider == 'jev' else ((q['name'], q) for q in payload['questions'])
    for name, question in questions:
        options = list(question['criteria']) if provider == 'jev' else [x['value'] for x in question['choices']]
        probabilities = {value: float(index == 0) for index, value in enumerate(options)}
        answer = {'type': 'choice', 'choice': options[0], 'probabilities': probabilities, 'confidence': 1.0}
        if provider == 'jev':
            answers[name] = answer
        else:
            answer.update(name=name, probabilities=[{'value': value, 'probability': probability} for value, probability in probabilities.items()])
            answers.append(answer)
    return canonical({'model': payload['model'], 'answers': answers, 'usage': {'input_tokens': 0, 'output_tokens': 0}})


def evaluate_suite(suite, adapter, pin, *, live=None, state_dir=None):
    validate_suite(suite, adapter)  # Admit the entire suite before any call or key read.
    if live not in (None, 'jev', 'openai', 'both'):
        raise HarnessError('invalid_provider')
    if live and state_dir is None:
        raise HarnessError('live_state_dir_required')
    providers = ('jev', 'openai') if live in (None, 'both') else (live,)
    counts = {'providerAttempts': 0, 'simulatedTransports': 0, 'cachedReplays': 0}
    rows = []
    began = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='lens-provider-simulation-') as temporary:
        for provider in providers:
            for case in suite['cases']:
                request = case['request']
                wire = adapter.wire_request(provider, request, profile='standard')
                observed = {}
                def transport(name, payload, key):
                    # The transport receives the canonical request only. No closure
                    # reads case.expected or case.domain to synthesize a response.
                    if live:
                        counts['providerAttempts'] += 1
                        raw = adapter._AdvisoryHttps('standard').send(name, payload, key)
                    else:
                        counts['simulatedTransports'] += 1
                        raw = simulated_response(name, payload)
                    observed['responseSha256'] = sha256(raw)
                    return raw
                started = time.monotonic()
                try:
                    receipt = adapter.evaluate(provider, request,
                        state_dir=state_dir if live else temporary,
                        live=True, transport=transport,
                        key_reader=None if live else lambda _: 'SYNTHETIC-NO-CREDENTIAL',
                        profile='standard', attempt_ceiling=MAX_CASES)
                except Exception as exc:
                    receipt = {'status': 'blocked', 'authority': 'advisory_only',
                               'errorType': type(exc).__name__, 'answers': [], 'usage': None}
                counts['cachedReplays'] += int(receipt.get('replayed', False))
                answers = receipt.get('answers', [])
                comparisons = [{'name': answer['name'], 'allowed': answer.get('choice') in case['expected'][answer['name']]}
                               for answer in answers if answer.get('type') == 'choice']
                row = {'caseId': case['id'], 'provider': provider,
                       'responseOrigin': ('LIVE_PROVIDER' if receipt.get('response_sha256') else 'NO_PROVIDER_RESPONSE') if live else 'SIMULATED_TRANSPORT',
                       'measurement': 'model_evaluation' if live else 'serialization_and_parser_only',
                       'inputSha256': request['source_sha256'], 'wireSha256': sha256(canonical(wire)),
                       'durationSeconds': round(time.monotonic() - started, 6),
                       'labelComparison': comparisons, 'receipt': receipt}
                if not live:
                    # Factory estimates from fixture usage; it is not an observed
                    # provider cost/token measurement. Preserve that distinction.
                    row['simulatedUsage'] = row['receipt'].get('usage')
                    row['receipt'] = {**receipt, 'usage': None, 'estimated_cost_usd': None}
                rows.append(row)
                # The shared transport deliberately hides HTTP/auth details.
                # Any unavailable result stops this provider to avoid repeating
                # an authentication/outage failure across the remaining cases.
                if live and receipt.get('status') in {'blocked', 'provider_unavailable', 'indeterminate', 'budget_exhausted'}:
                    break
    usage = {'input_tokens': 0, 'output_tokens': 0} if live else None
    for row in rows:
        observed_usage = row['receipt'].get('usage')
        if live and observed_usage and not row['receipt'].get('replayed'):
            for key in usage:
                usage[key] += observed_usage[key]
    return {'schema': 'lens.learning-evaluation-report/v1', 'evidenceMode': 'SYNTHETIC',
            'responseOrigin': 'LIVE_EVALUATION' if live else 'SIMULATED_TRANSPORT',
            'authority': 'advisory_only', 'factorySource': pin,
            'suiteSha256': sha256(canonical(suite)), 'source': suite['source'],
            'durationSeconds': round(time.monotonic() - began, 6), **counts,
            'observedUsage': usage, 'estimatedCostUsd': None,
            'plannedCaseCalls': len(suite['cases']) * len(providers),
            'notAttemptedCaseCalls': len(suite['cases']) * len(providers) - len(rows),
            'errors': sum(row['receipt'].get('status') != 'ok' for row in rows), 'results': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite', type=Path)
    parser.add_argument('--factory-checkout', required=True, type=Path)
    parser.add_argument('--live', choices=['jev', 'openai', 'both'])
    parser.add_argument('--state-dir', type=Path, help='Existing task-owned budget directory; required for live calls')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        raw = args.suite.read_bytes()
        if len(raw) > MAX_SUITE_BYTES:
            raise HarnessError('suite_byte_cap')
        suite = strict_json(raw)
        adapter, pin = load_adapter(args.factory_checkout)
        report = evaluate_suite(suite, adapter, pin, live=args.live, state_dir=args.state_dir)
    except Exception as exc:
        # Exception messages can contain provider or credential data. Only local
        # closed error codes are emitted; all external failures keep their type.
        report = {'schema': 'lens.learning-evaluation-report/v1', 'status': 'blocked',
                  'reason': str(exc) if type(exc) is HarnessError else 'evaluation_boundary_failure',
                  'errorType': type(exc).__name__, 'providerAttempts': None}
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end='')
    return 2 if report.get('status') == 'blocked' or report.get('errors') else 0


if __name__ == '__main__':
    raise SystemExit(main())
