import type { Council, Receipt } from "./council.ts";
import { redactDeep } from "./redact.ts";
import type { Capability } from "./types.ts";

/**
 * The single choke point for data leaving the device. Every call is minimised, checked by
 * the council and receipted before the request is made. Revoking a grant therefore blocks
 * the very next call, and the receipt log shows the denial.
 */

export class EgressBlocked extends Error {
  readonly capability: Capability;
  readonly receipt: Receipt;
  constructor(capability: Capability, receipt: Receipt) {
    super(`${capability} blocked by the permission council (receipt #${receipt.seq})`);
    this.capability = capability;
    this.receipt = receipt;
  }
}

export class ServiceUnavailable extends Error {}

export interface EgressResult<T> {
  data: T;
  receipt: Receipt;
  removed: Record<string, number>;
}

export type Egress = <T>(capability: Capability, path: string, payload: object, subject: string) => Promise<EgressResult<T>>;

export function createEgress(council: Council, fetchImpl: typeof fetch = (...a) => fetch(...a)): Egress {
  return async <T>(capability: Capability, path: string, payload: object, subject: string) => {
    const { value, removed } = redactDeep(payload);
    const { allowed, receipt } = await council.checkEgress(capability, subject, value);
    if (!allowed) throw new EgressBlocked(capability, receipt);
    const res = await fetchImpl(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(value),
    });
    if (res.status === 503) throw new ServiceUnavailable(`${path}: service not configured on the relay`);
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status} ${(await res.text()).slice(0, 200)}`);
    return { data: (await res.json()) as T, receipt, removed };
  };
}

export interface RelayHealth {
  exa: boolean;
  exaMode?: "api" | "mcp-keyless";
  typesafe: boolean;
  model?: string;
  /** A hosted writer (NVIDIA Nemotron behind the relay) can draft from the question and the public sources. */
  writer?: boolean;
}

export async function relayHealth(fetchImpl: typeof fetch = (...a) => fetch(...a)): Promise<RelayHealth> {
  try {
    const res = await fetchImpl("/api/health");
    if (!res.ok) return { exa: false, typesafe: false };
    return (await res.json()) as RelayHealth;
  } catch {
    return { exa: false, typesafe: false };
  }
}
