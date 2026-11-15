// Host-side grounding: the host (not the model) reads an Aiven project inventory
// through the API with its own read-only credential and hands it to the model as
// framed, untrusted tool data. Facts such as names, states, plans, VPC placement,
// protection and topic settings then come from the API, not from model recall.
// `fetchJson(path)` is injected (it must add the host's credential).
export async function inventorySnapshot({ project, fetchJson }) {
  const { services } = await fetchJson(`project/${project}/service`);
  const out = services.map(s => ({
    name: s.service_name, type: s.service_type, state: s.state, plan: s.plan, cloud: s.cloud_name,
    in_project_vpc: !!s.project_vpc_id, termination_protection: !!s.termination_protection,
    node_count: s.node_count, disk_space_mb: s.disk_space_mb, plan_price_usd_per_hour: s.plan_price_usd ?? null,
    pg_version: s.service_type === 'pg' ? Number(s.user_config?.pg_version ?? 0) || null : undefined,
    databases: s.service_type === 'pg' ? (s.databases ?? []).map(d => typeof d === 'string' ? d : d.database_name) : undefined,
    tags: s.tags ?? {}
  }));
  const topics = [];
  for (const s of services.filter(x => x.service_type === 'kafka' && x.state === 'RUNNING')) {
    try { for (const t of (await fetchJson(`project/${project}/service/${s.service_name}/topic`)).topics ?? []) topics.push({ service: s.service_name, topic: t.topic_name, partitions: t.partitions, replication: t.replication }); } catch { topics.push({ service: s.service_name, error: 'topics unavailable' }); }
  }
  return { project, fetchedAt: new Date().toISOString(), source: 'Aiven API, host read-only credential', services: out, kafka_topics: topics };
}

export function inventoryAttachment(snapshot) {
  return { source: `aiven-api inventory snapshot of project ${snapshot.project} at ${snapshot.fetchedAt} (host, read-only)`, content: JSON.stringify(snapshot) };
}
