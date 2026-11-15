import test from 'node:test';
import assert from 'node:assert/strict';
import { inventorySnapshot, inventoryAttachment } from '../services/aiven-platform/grounding.mjs';

test('inventory snapshot keeps the facts tasks need and labels its source', async () => {
  const api = { 'project/p/service': { services: [
    { service_name: 'pg-a', service_type: 'pg', state: 'RUNNING', plan: 'startup-4', cloud_name: 'c1', project_vpc_id: 'v', termination_protection: true, node_count: 1, disk_space_mb: 80, plan_price_usd: '0.1', user_config: { pg_version: '16' }, databases: [{ database_name: 'app' }], tags: { env: 'x' } },
    { service_name: 'k', service_type: 'kafka', state: 'RUNNING', plan: 'free-0', cloud_name: 'c2', project_vpc_id: null, termination_protection: false } ] },
    'project/p/service/k/topic': { topics: [{ topic_name: 't', partitions: 2, replication: 2 }] } };
  const snap = await inventorySnapshot({ project: 'p', fetchJson: async p => api[p] });
  assert.deepEqual(snap.services[0], { name: 'pg-a', type: 'pg', state: 'RUNNING', plan: 'startup-4', cloud: 'c1', in_project_vpc: true, termination_protection: true, node_count: 1, disk_space_mb: 80, plan_price_usd_per_hour: '0.1', pg_version: 16, databases: ['app'], tags: { env: 'x' } });
  assert.deepEqual(snap.kafka_topics, [{ service: 'k', topic: 't', partitions: 2, replication: 2 }]);
  assert.match(inventoryAttachment(snap).source, /inventory snapshot of project p .* \(host, read-only\)/);
});
