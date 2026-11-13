/**
 * UI-only adapter for the Fleet Control server projection. All JSON fetched
 * by a browser is untrusted. This module NEVER attests Cloud/CI/model readiness.
 * Source-bound records are advisory until an authenticated owner-private host
 * establishes an independent trust channel outside this browser payload.
 */
import {sourceCommit} from './status-model.mjs';

const KIND = 'junction-fleet-control/server-projection/v1';
const REPO = 'SalesSquad/junction-pets';
const SLUG = /^junction-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const ENV_ID = /^[A-Za-z0-9_.:-]{5,160}$/;
const SHA = /^[a-f0-9]{40}$/;
const STATES = {
  cloud: new Set(['ready', 'unprovisioned', 'unverified', 'blocked']),
  ci: new Set(['missing', 'stale', 'unverified', 'blocked', 'verified-pass', 'verified-fail']),
  evaluation: new Set(['missing', 'stale', 'unverified', 'blocked', 'verified-pass', 'verified-fail']),
  grant: new Set(['unverified', 'revoked', 'host-verified', 'blocked']),
};
const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);

function safeState(value, field) {
  const candidate = value?.state;
  return STATES[field].has(candidate) ? candidate : 'unverified';
}

function timestamp(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/.test(value)) return null;
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) return null;
  const normalized = value.replace(/(?:\.(\d{1,3}))?Z$/, (_, fraction) =>
    '.' + (fraction ?? '').padEnd(3, '0') + 'Z');
  return new Date(ms).toISOString() === normalized ? ms : null;
}

export function normalizeServerProjection(payload, registry, nowMs = Date.now()) {
  const expectedSha = sourceCommit(registry?.source);
  if (!expectedSha || !isObject(payload) || payload.schemaVersion !== 1 ||
      payload.kind !== KIND || !isObject(payload.source) ||
      payload.source.repository !== REPO || payload.source.commit !== expectedSha ||
      !Array.isArray(payload.pets) || payload.pets.length !== 34 ||
      !Array.isArray(registry?.pets) || registry.pets.length !== 34) {
    throw new Error('Backend projection missing, incomplete or source SHA mismatched');
  }
  const observedAt = timestamp(payload.generatedAt);
  if (observedAt === null || !Number.isFinite(nowMs) || observedAt > nowMs + 60_000) {
    throw new Error('Backend projection has invalid timestamp');
  }
  const stale = nowMs - observedAt > 600_000;
  const canonical = new Set(registry.pets.map(pet => pet.slug));
  const byPet = new Map();
  for (const item of payload.pets) {
    if (!isObject(item) || !SLUG.test(item.petSlug || '') ||
        !canonical.has(item.petSlug) || byPet.has(item.petSlug) ||
        item.runtimeExecutionAllowed !== false) {
      throw new Error('Backend projection has unsafe, duplicate or unknown pet');
    }
    const cloud = safeState(item.cloud, 'cloud');
    // Downgrade any apparently verified claim whose exact receipt binding
    // does not match the authenticated source claim of the static registry.
    const cloudBound = cloud === 'ready' &&
      item.cloud?.sourceCommit === expectedSha &&
      typeof item.cloud?.environmentId === 'string' &&
      ENV_ID.test(item.cloud.environmentId) &&
      timestamp(item.cloud.verifiedAt) !== null;
    const evidenceState = (field) => {
      const state = safeState(item[field], field);
      if (state.startsWith('verified-') && (stale || !SHA.test(item[field]?.sourceCommit || '') ||
          item[field].sourceCommit !== expectedSha)) return 'stale';
      return state;
    };
    byPet.set(item.petSlug, Object.freeze({
      cloud: cloud === 'ready' ? stale ? 'stale' : cloudBound ? 'ready' : 'unverified' : cloud,
      ci: evidenceState('ci'),
      evaluation: evidenceState('evaluation'),
      grant: stale && safeState(item.grant, 'grant') === 'host-verified'
        ? 'unverified' : safeState(item.grant, 'grant'),
      // Opaque ID is advisory. Never propagate raw reason/evidence URL/token
      // fields from user-editable or compromised JSON.
      environmentId: !stale && cloudBound ? item.cloud.environmentId : null,
    }));
  }
  if (byPet.size !== canonical.size) throw new Error('Backend projection omitted company lanes');
  return Object.freeze({
    advisoryOnly: true,
    sourceSha: expectedSha,
    generatedAt: payload.generatedAt,
    stale,
    byPet,
  });
}

export function advisoryCloudLabel(record) {
  if (!record) return 'No backend report';
  if (record.cloud === 'ready') return 'Backend reports ready · unverified in browser';
  if (record.cloud === 'stale') return 'Backend Cloud evidence stale · recheck provider';
  if (record.cloud === 'blocked') return 'Backend reports cloud blocked';
  if (record.cloud === 'unprovisioned') return 'Backend reports not provisioned';
  return 'Backend Cloud status unverified';
}

export function advisoryEvidenceLabel(state, category) {
  if (state === 'verified-pass') return category + ': backend reports pass · not browser-attested';
  if (state === 'verified-fail') return category + ': backend reports fail';
  if (state === 'stale') return category + ': source evidence stale';
  if (state === 'blocked') return category + ': backend check blocked';
  return category + ': no independently verified result';
}
