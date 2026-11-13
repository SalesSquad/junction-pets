# Verda service map for Junction agents

Work ID: junction.verda.service-audit-20261113
Observed: 2026-11-13, approximately 20:20 UTC.
Repository baseline: 9b8c8edbe6bde9f61ffd12185673ccb7884778b2.
Scope: developer guidance and read-only discovery; no GPU deployment or inference run was performed by this audit.
Companion read path: [compute routing](NVIDIA_VERDA_COMPUTE_ROUTING.md), then this service map. Provider secrets and private execution receipts stay outside content packs and generated plugins.

## Goal

Mikael reports that on-site Verda staff invited extensive use during Junction and rewards ambitious applications. Treat this as owner-provided event guidance. The engineering objective is measured solution quality and scaling, with each job bound to source, input digest, model, result and resource usage. Runtime entitlements and stock still come from the authenticated account.

## Services and proposed workloads

These are proposed integrations, not implemented capabilities.

| Service | Useful Junction workload | Control and qualification |
| --- | --- | --- |
| GPU VMs, on-demand and spot | Nemotron self-hosting experiments; visual extraction, segmentation, 3D reconstruction; repeatable performance comparisons | CLI vm, availability, images, cost; checkpoint interruptible work and verify architecture/driver/model memory requirements |
| Serverless GPU containers | Shared specialist endpoints for NVIDIA/other agents, OCR, embeddings and rendering | CLI container supports always-on endpoints, replica limits, pause/resume and scaling; zero minimum replicas where appropriate |
| Serverless batch jobs | Video transcription, frame extraction plus GPU vision, scene processing, parallel benchmark runs | API/SDK or infrastructure configuration; each job gets one replica and a deadline, exits when done; no batch subcommand was exposed in CLI 1.10.0 |
| Managed Inference | Independent coding/reasoning or evidence-review workers through an OpenAI-compatible API | Separate inference credentials/model enablement; currently documented Kimi K3.1 Pro and DeepSeek V4.1 Flash 1017; hosted Nemotron not verified |
| Instant Clusters | Multi-GPU serving and real scaling experiments with Kubernetes, Kueue, Slinky/Slurm and NVIDIA Dynamo | Published H200/B200/B300 configurations, 16–128 GPUs, InfiniBand; account capacity, contract duration and job placement require verification |
| S3-compatible object storage (Beta) | Versioned input manifests, authorized videos/images, model artifacts and benchmark outputs | CLI object-storage; separate S3 credentials; objects private; current keys span all project buckets |
| NVMe block storage and shared filesystem | Model cache, fast temporary datasets and shared weights across workers | Block disks for local VM state, SFS/RWX for shared model weights; checkpoint to durable artifacts |
| OCI container registry | Pinned worker images reused by VM/container/cluster execution | CLI registry, immutable image digests and retention policies; separate registry credentials |
| Private networking and confidential computing | Internal specialist services; later confidential inference where justified | Location/hardware-specific, validate attestation before privacy claims; this audit tested neither |
| Automation and diagnostics | Reproducible job dispatch, teardown, cost/utilization records and agent access | Existing CLI agent-mode JSON, API/SDK, Terraform/OpenTofu, dstack/SkyPilot, MCP, audit logs and metrics; no new permanent daemon needed |
| CPU VMs, Jupyter and dedicated/bare-metal options | Interactive GPU-adjacent work; custom large deployments | Existing Codex Cloud remains default CPU engineering route; bare metal/custom clusters are contract-based, not automatically available |

## Authenticated catalog versus actual stock

The authenticated CLI returned **57 GPU instance configurations** at 2026-11-13T20:20:56Z. Model labels included GB300, B300, B200, H200, H100, A100 80GB/40GB, V100, RTX PRO 6000, L40S, RTX 6000 Ada, RTX A6000, plus confidential-computing variants. Single-VM configurations reach eight GPUs for several families. This is a catalog, not a reservation.

The separate availability request returned:
- FIN-01: A100 80GB configurations with one or two GPUs; V100 configurations with one or four GPUs, plus CPU types.
- FIN-02: one A100 40GB configuration.
- FIN-03: CPU configurations only in this VM availability response.

Do not interpret the VM response as serverless/cluster stock. Larger Blackwell/Hopper catalog entries were not shown as available VMs at this checkpoint. Recheck before dispatch.

The container list was empty. The local CLI reported S3 credentials missing and registry credentials not configured. That describes this executor's setup, not proof that the account has no buckets or registry assets.

## First useful implementation sequence

1. Keep source/build/test loops in existing Codex Cloud. Build a source-pinned GPU worker image that accepts an input manifest and emits a typed result plus receipt.
2. Start with video/image understanding: approved challenge media to transcription/frame batches, NVIDIA Nemotron reasoning, deterministic validation, then visual verification. NVIDIA API remains a separate route; do not replace the adapter's fixed provider URL with an unverified Verda endpoint.
3. Reuse the same image/manifest for asynchronous GPU jobs and an autoscaled specialist endpoint. Expose capability discovery to other agents through the existing host permission/consent boundary.
4. Add shared model cache, private object artifacts and pinned registry images. Record time-to-result, task success, GPU utilization, throughput and cost per useful output.
5. Demonstrate scale with a fixed evaluation set and increasing concurrency. Only expand to a cluster when measured memory, throughput or multi-node requirements justify it. Preserve existing unrelated GPU-training pauses.

Never poll an ordinary batch deployment URL to check health: **GET as well as POST/PUT/PATCH/DELETE can launch a job**. Use only the documented status/result polling routes for job observation. Set job deadlines and concurrency explicitly. Keep workload data and credentials out of public packages and submission materials.

## Verified project experiments and agent access

The later [source-bound project experiment record](https://github.com/SalesSquad/agents/pull/106) supersedes the initial executor-readiness snapshot above. Managed Kimi text/vision/typed-tool formation, an actual CPU serverless batch result, S3 roundtrip and one source-pinned Taika Motion Wan draft video have now passed. Reality Twin's synthetic Philip-column CUDA experiment met its physical/oracle checks; at 65,536 identical columns it measured 28.4–31.6× speedup including transfers against the same two-thread eager Torch CPU baseline. This is not native Metal/product qualification. Savi's new avatar render run is authorized; its existing MLX trainer still requires Apple Silicon.

Use the installed `verda-agent` on the authorized executor through supported remote access. It serializes duplicate immutable job IDs, reconciles uncertain creates and shares a persistent GPU reservation ledger across sessions. Agent labels are not authentication; this does not automatically give every Codex Cloud environment credentials or transport. Keep provider Cloud, S3 and Inference credentials in the executor's protected store, never in GPU workers or source packages.

For batch execution use the actual deployment metadata's authoritative endpoint, bounded concurrency/deadline and explicit inference ID. Observe only documented status/result routes; record the terminal result rather than deployment201 alone. Hardware availability changes independently in VM and serverless pools. Stop idle VMs after finite tests and preserve their outputs before removing storage.

## Primary sources

- [Services](https://docs.verda.com/resources/services-overview/)
- [CLI](https://docs.verda.com/cli/)
- [Containers](https://docs.verda.com/containers/overview/)
- [Batch jobs](https://docs.verda.com/containers/batch-jobs/)
- [Managed models](https://docs.verda.com/inference/models/)
- [Instant Clusters](https://docs.verda.com/clusters/instant-clusters/)
- [Dynamo on Verda](https://docs.verda.com/clusters/instant-clusters/tutorials/dynamo-inference/)
- [Object storage](https://docs.verda.com/storage/object-storage/)
- [Storage](https://docs.verda.com/storage/)
- [Official Junction event and Best use of Verda](https://verda.com/blog/junction-2026)

The authenticated Junction Platform brief, captured in the [Verda challenge card](https://chatgpt.com/space/page_40ee62c902108191bb7b43c71ded5f9d), is the current challenge authority: document the process and post a link to its summary in Verda's Discord channel. It lists USD10,000 in cloud credits plus hoodies for first place and USD2,500 each for second and third, superseding the older EUR amounts on Verda's blog. The brief explicitly excludes crypto mining. The original catalog snapshot did not qualify execution; the later experiments section records the narrower verified results. No award eligibility outcome is claimed.
