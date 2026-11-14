"""Offline-only strict fixture contracts. No HTTP client or credential access."""
import json
import math
from pathlib import Path
from experiment import CHOICES, decision

CRITERIA = {
    'CONTINUE': 'Fresh confident observations, no mapped obstacle nearby; continue bounded simulation.',
    'REPLAN': 'Fresh object observation has lateral displacement; adjust object-centered target.',
    'REOBSERVE': 'Tracking is stale or occluded; hold and await fresh observations.',
    'REQUEST_HUMAN': 'Mapped obstacle blocks local push; request help within remaining budget and hold.',
    'HALT': 'Deadman released, workspace invalid, or intervention budget exhausted; halt proposals.'
}
OBS_KEYS = {'object', 'age', 'quality', 'deadman', 'inside', 'obstacle_distance'}


def observed(o):
    if type(o) is not dict or set(o) != OBS_KEYS:
        raise ValueError('Observed allowlist required; hidden state forbidden')
    if type(o['deadman']) is not bool or type(o['inside']) is not bool:
        raise ValueError('Boolean safety signals required')
    nums = o['object'] if type(o['object']) is list and len(o['object']) == 2 else []
    if len(nums) != 2 or any(type(v) not in (int, float) or not math.isfinite(v)
                             for v in nums + [o['age'], o['quality'], o['obstacle_distance']]):
        raise ValueError('Finite observations required')
    if o['age'] < 0 or not 0 <= o['quality'] <= 1 or o['obstacle_distance'] < 0:
        raise ValueError('Invalid observed range')
    return o


def validate_request(provider, body):
    if provider == 'openai':
        if set(body) != {'model', 'input', 'questions'} or body['model'] != 'gpt-6-luna':
            raise ValueError('OpenAI contract')
        observed(json.loads(body['input']))
        q = body['questions']
        if type(q) is not list or len(q) != 1 or set(q[0]) != {'type','name','instructions','choices'}:
            raise ValueError('One named choice question required')
        if q[0] != dict(type='choice', name='next_step', instructions='Select the next simulation-only step from observed evidence.',
                         choices=[dict(value=k, description=v) for k,v in CRITERIA.items()]):
            raise ValueError('Question contract')
    elif provider == 'openrouter':
        if set(body) != {'model','state','questions'} or body['model'] != 'typesafe/jev-1.13':
            raise ValueError('Jev contract')
        observed(body['state'])
        if body['questions'] != {'next_step': dict(type='choice', instructions='Select the next simulation-only step from observed evidence.', criteria=CRITERIA)}:
            raise ValueError('Question contract')
    else:
        raise ValueError('Unknown provider')


def validate_answer(answer):
    # Local normalized response contract, not a universal provider response parser.
    if set(answer) != {'type','name','choice','confidence','probabilities'}:
        raise ValueError('Unexpected normalized answer fields')
    if answer['type'] != 'choice' or answer['name'] != 'next_step' or answer['choice'] not in CHOICES:
        raise ValueError('Unknown answer/choice')
    probs = answer['probabilities']
    if type(probs) is not dict or set(probs) != set(CHOICES):
        raise ValueError('Exact choice probabilities required')
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0 <= v <= 1
           for v in list(probs.values())+[answer['confidence']]) or abs(sum(probs.values())-1) > 1e-6:
        raise ValueError('Invalid probability distribution')
    if probs[answer['choice']] != max(probs.values()):
        raise ValueError('Choice disagrees with distribution')
    return answer


def guarded_choice(obs, budget, answer):
    observed(obs)
    # Hard rules have priority over even confidence=1 model claims.
    hard = decision(obs, budget)
    if hard in ('HALT','REOBSERVE','REQUEST_HUMAN'):
        return hard
    try:
        a = validate_answer(answer)
    except (ValueError, TypeError, KeyError):
        return 'REOBSERVE'
    if a['confidence'] < 0.8:
        return 'REOBSERVE'
    candidate = a['choice']
    if candidate == 'REQUEST_HUMAN' and budget <= 0:
        return 'HALT'
    # Observation-driven replanning is a mandatory lower bound on caution:
    # a confident external model may abstain, but never downgrade it to CONTINUE.
    if hard == 'REPLAN' and candidate == 'CONTINUE':
        return 'REPLAN'
    return candidate


if __name__ == '__main__':
    f = json.loads((Path(__file__).parent/'decision-fixtures.json').read_text())
    for item in f['fixtures']:
        validate_request(item['provider'], item['request']['body'])
        validate_answer(item['normalized_offline_response'])
    print('PASS: 2 REDACTED requests + normalized OFFLINE_STUB answers; no calls sent')


def normalize_response(provider, response):
    """Strict fixture subset of wire responses; rejects missing/refused/unknown answers."""
    if provider == 'openai':
        if set(response) != {'answers'} or type(response['answers']) is not list or len(response['answers']) != 1:
            raise ValueError('Expected one OpenAI answer excerpt')
        a = dict(response['answers'][0])
        if type(a.get('probabilities')) is not list:
            raise ValueError('Expected OpenAI probability array')
        entries = a['probabilities']
        if len(entries) != len(CHOICES) or any(set(e) != {'value','probability'} for e in entries):
            raise ValueError('Probability entry contract')
        a['probabilities'] = {e['value']: e['probability'] for e in entries}
    elif provider == 'openrouter':
        if set(response) != {'answers'} or set(response['answers']) != {'next_step'}:
            raise ValueError('Expected one OpenRouter answer excerpt')
        a = dict(response['answers']['next_step'])
        if 'name' in a:
            raise ValueError('Unexpected wire name')
        a['name'] = 'next_step'
    else:
        raise ValueError('Unknown provider')
    return validate_answer(a)
