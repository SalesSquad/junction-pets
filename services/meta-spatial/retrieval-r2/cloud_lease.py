#!/usr/bin/env python3
"""Finite trusted-host GPU lease; credentials remain in the installed CLI.

Reuses one detached OS volume. Never deletes data, creates SSH keys, retries an
ambiguous create, or operates an instance that does not match this lease.
Run inside the existing durable receipt runner, not as a service/daemon.
"""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--state-dir', required=True, type=Path)
    p.add_argument('--cli', required=True)
    p.add_argument('--hostname', required=True)
    p.add_argument('--instance-type', required=True)
    p.add_argument('--location', required=True)
    p.add_argument('--volume', required=True)
    p.add_argument('--ssh-key', required=True)
    p.add_argument('--max-hours', type=float, default=4)
    p.add_argument('--budget-usd', type=float, default=50)
    a = p.parse_args()
    if not 0 < a.max_hours <= 4 or not 0 < a.budget_usd <= 50:
        p.error('maximum four hours and USD50')
    a.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (a.state_dir / 'lease.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state_path = a.state_dir / 'lease.json'
    if state_path.exists():
        raise RuntimeError('existing_lease_requires_status_reconciliation_not_create_retry')
    state = {'work_id': 'META-LENS-TRAIN-20261114-R2', 'created_utc': utc(),
             'hostname': a.hostname, 'phase': 'preflight', 'events': [],
             'budget_usd': a.budget_usd, 'max_gpu_hours': a.max_hours,
             'max_task_machines': 4, 'admitted_task_machines': 1,
             'existing_os_volume': a.volume, 'new_persistent_storage': False}

    def call(*args):
        r = subprocess.run([a.cli, '--agent', *args, '-o', 'json'],
                           text=True, capture_output=True, timeout=50)
        state['events'].append({'at_utc': utc(), 'operation': ' '.join(args[:2]),
                                'exit_code': r.returncode})
        save(state_path, state)
        if r.returncode:
            raise RuntimeError('provider_operation_failed:' + ' '.join(args[:2]))
        # Shutdown may return a human acknowledgement even in agent mode.
        if args[:2] == ('vm', 'shutdown'):
            return None
        return json.loads(r.stdout)

    inventory = call('vm', 'list')
    if not isinstance(inventory, list):
        raise RuntimeError('unexpected_inventory_schema')
    if any(v.get('hostname') == a.hostname for v in inventory):
        raise RuntimeError('hostname_already_exists')
    volume = call('volume', 'describe', a.volume)
    if volume.get('status') != 'detached' or volume.get('instance_id') or volume.get('instances') or not volume.get('is_os_volume') or volume.get('location') != a.location:
        raise RuntimeError('volume_not_detached_compatible_os')
    available = call('vm', 'availability', '--type', a.instance_type)
    if not any(v.get('instance_type') == a.instance_type and v.get('location') == a.location for v in available):
        raise RuntimeError('requested_gpu_not_available')
    cost = call('cost', 'estimate', '--type', a.instance_type, '--os-volume', str(volume['size']))
    rate = float(cost['total']['hourly'])
    state.update({'hourly_compute_usd': float(cost['instance']['hourly']),
                  'attributed_existing_storage_hourly_usd': float(cost['os_volume']['hourly']),
                  'reserved_upper_estimate_usd': rate * (a.max_hours + 1),
                  'pricing_qualification': 'provider_quote_not_invoice'})
    balance = call('cost', 'balance')
    state['balance_observed_usd'] = float(balance['amount'])
    if balance.get('currency', '').lower() != 'usd' or state['reserved_upper_estimate_usd'] > min(a.budget_usd, state['balance_observed_usd']):
        raise RuntimeError('budget_preflight_refused')
    start = time.time()
    state.update({'phase': 'create_requested', 'start_epoch': start,
                  'shutdown_deadline_epoch': start + a.max_hours * 3600})
    save(state_path, state)
    # This is the sole create. A timeout is reconciled by exact hostname below.
    try:
        created = call('vm', 'create', '--kind', 'gpu', '--instance-type', a.instance_type,
                       '--location', a.location, '--os', a.volume, '--hostname', a.hostname,
                       '--ssh-key', a.ssh_key, '--contract', 'pay_as_go', '--pricing', 'FIXED_PRICE',
                       '--wait=false')
        state['instance_id'] = created.get('id') or created.get('instance_id')
    except Exception as exc:
        state['create_outcome'] = type(exc).__name__ + ':unknown_reconcile_only'
    save(state_path, state)
    shutting_down = False
    stop_attempts = 0
    while time.time() - start < (a.max_hours + 1) * 3600:
        try:
            if not state.get('instance_id'):
                matches = [v for v in call('vm', 'list') if v.get('hostname') == a.hostname]
                if len(matches) == 1:
                    state['instance_id'] = matches[0]['id']
                elif len(matches) > 1:
                    raise RuntimeError('ambiguous_hostname_multiple_instances')
            if state.get('instance_id'):
                vm = call('vm', 'describe', state['instance_id'])
                if vm.get('hostname') != a.hostname or vm.get('os_volume_id') != a.volume:
                    raise RuntimeError('lease_identity_mismatch')
                state['provider_status'] = vm.get('status')
                state['ip'] = vm.get('ip')
                state['last_observed_utc'] = utc()
                state['elapsed_attributed_estimate_usd'] = rate * (time.time() - start) / 3600
                if vm.get('status') == 'running':
                    state['phase'] = 'running' if not shutting_down else 'stopping'
                    if not state.get('running_observed_utc'):
                        state['running_observed_utc'] = utc()
                        print(json.dumps({k: state[k] for k in ('phase', 'instance_id', 'ip', 'hostname', 'shutdown_deadline_epoch')}), flush=True)
                if shutting_down and vm.get('status') in ('offline', 'discontinued', 'deleted'):
                    state.update({'phase': 'stopped', 'stopped_observed_utc': utc(),
                                  'stop_observed_epoch': time.time(), 'retained_existing_volume': True})
                    save(state_path, state)
                    print(json.dumps({'phase': 'stopped', 'instance_id': state['instance_id'],
                                      'attributed_estimate_usd': state['elapsed_attributed_estimate_usd']}), flush=True)
                    return
                requested = (a.state_dir / 'stop-requested').exists()
                expired = time.time() >= state['shutdown_deadline_epoch']
                if (requested or expired or shutting_down) and vm.get('status') == 'running':
                    shutting_down = True
                    state['phase'] = 'stopping'
                    state['stop_reason'] = 'task_completed' if requested else 'four_hour_deadline'
                    if stop_attempts < 10:
                        stop_attempts += 1
                        call('vm', 'shutdown', state['instance_id'], '--yes', '--wait=false')
        except Exception as exc:
            state['last_error'] = type(exc).__name__ + ':' + str(exc)[:160]
        save(state_path, state)
        time.sleep(20 if shutting_down else 30)
    state['phase'] = 'unresolved_requires_operator'
    save(state_path, state)
    raise RuntimeError('could_not_verify_shutdown')


if __name__ == '__main__':
    main()
