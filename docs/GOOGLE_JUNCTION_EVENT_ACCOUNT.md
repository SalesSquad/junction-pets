# Google Junction 2026 — temporary event account and agent routing

**Status:** Google-issued participant account received; **no API key creation, sign-in, quota probe or live agent credential provisioning is verified**. This page is a nonsecret access runbook, not a usable credential or provider grant.

**Important separate identity:** the owner also has a **personal Google AI Studio** Gemini API key named `Junction-2026-Gemini-Agent-Mesh`; its tested use is routed through the MBP's Keychain and [SalesSquad/agents PR #120](https://github.com/SalesSquad/agents/pull/120) / `docs/gemini-junction.md`. That personal key **does not** verify a key, quota or login for the temporary `gcplab.me` event account below. Do not combine either provider's entitlements or distribute either credential.

## Organizer source and validity

- On **14 Nov 2026, 01:54 EET**, Erno Kurki (`elv@google.com`) sent the owner's Junction mailbox a personal message titled **Google Junction Accounts**. The message provides an assigned **temporary Google identity and password**, **not an API key**. Keep the actual credentials only in the owner-authorized private channel or approved host secret store.
- Organizer describes **generous event quotas** but gives **no verified infinite quota or usage rate**. The provider must confirm actual limits and service availability.
- The account is exclusively for developing and demonstrating the registered team's project **during official Junction hackathon hours**. Sharing credentials outside the registered team, publishing API keys, and unrelated commercial/non-event workloads are prohibited.
- Organizer says event-account prompts, code, outputs and submitted data are not used to train its models. Ordinary privacy and data-minimization rules still apply.
- **All account projects and data are permanently deleted when the event concludes on 15 Nov 2026.** Export reproducible source, configuration (without secrets), models/artifacts and project outputs to approved persistent storage before then. Exact provider deletion time is not verified.

## How authorized agents can use this account

1. Agent discovers this runbook through `START_HERE.md`, the per-company source index or the central `SalesSquad/agents` route. Discovery **does not grant login**.
2. Owner or another **registered-team** member signs in only through the official Google interface, validates service, region, terms and quotas, and (if supported) creates a separately scoped API key for the Junction project.
3. Provision that key **only to a verified registered-team executor**, using approved host-side secret injection with no secret values in ChatGPT/Spaces/GitHub, terminal arguments/history, PRs, logs, build artifacts or publicly shared demos. Avoid a shared root credential. Prefer one controlled Google-call gateway and explicit per-agent workload authorization instead of distributing the account password.
4. An agent uses its authorized executor/gateway for the specified hackathon task, checks provider scope and expiry, and records only nonsecret `account-access=verified|blocked|unknown`, actual API endpoint, purpose, time and usage receipt. No automatic privilege sharing via proposed agent-graph edges.
5. Keep an export/cleanup handoff ready for the end of the event; do not store irreplaceable work solely in the temporary account.

## Verified and unverified as of 14 Nov

| Item | State |
| --- | --- |
| Google participant identity/password email received | **Verified from original Gmail message** |
| Organizer's use restrictions and end-of-event deletion | **Verified from original message** |
| Google API key issued for the account | **Not verified; do not assume** |
| Google console sign-in, API service access or effective quota | **Not verified** |
| Credentials installed in a central production secret manager | **Not verified** |
| Codex Cloud, Claude, Chibi or Mac agents have working Google access | **Not verified separately per executor** |

**Credential source:** owner's private Gmail, message ID `1a1d757433865410` (`ervamaamikaelb@gmail.com`). This is a reference for the owner, **not** an invitation for an agent to copy secrets from the inbox. Do not reproduce the temporary username/password in catalog files.

**General agent entrypoint:** `SalesSquad/agents/cloud-services/google-junction/README.md`. The `cloud-services/secret-hub` source is **not** a verified production distribution service. A secret-store deployment and agent enrollment require explicit authorized host/provider setup. Do not infer access from this documentation.
