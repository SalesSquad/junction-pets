"""R3 shared visual residual, explicit anchor batches and baseline-safe selection.

NumPy helpers import no Torch. Training consumes only caller-selected train
embeddings; product families exclude ambiguous variants from negatives.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterator

import numpy as np


def normalize_rows(x):
    x = np.asarray(x, dtype=np.float32)
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError("finite_embedding_matrix_required")
    norm = np.linalg.norm(x, axis=1, keepdims=True)
    if np.any(norm < 1e-12):
        raise ValueError("zero_embedding")
    return x / norm


def project_numpy(x, weights=None):
    x = np.asarray(x, dtype=np.float32)
    if weights is None:
        return normalize_rows(x)
    if set(weights) != {"a", "b"}:
        raise ValueError("unexpected_adapter_fields")
    a, b = (np.asarray(weights[k]) for k in ("a", "b"))
    if a.dtype != np.float32 or b.dtype != np.float32:
        raise ValueError("adapter_dtype_must_be_float32")
    if x.ndim != 2 or a.ndim != 2 or b.shape != (a.shape[1], x.shape[1]) or a.shape[0] != x.shape[1] or a.shape[1] < 1:
        raise ValueError("adapter_shape_mismatch")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("nonfinite_adapter")
    return normalize_rows(x + (x @ a) @ b)


project_features = project_numpy


def _validate_selection(selection):
    if selection.get("schema_version") != 1 or selection.get("kind") != "meta.visual_adapter.r3.selection" or selection.get("fresh_cal_test_evaluated") is not False:
        raise ValueError("unexpected_r3_selection_contract")
    if selection["confirmation_candidate"] != selection["primary"]:
        raise ValueError("confirmation_candidate_must_match_frozen_primary")


def load_selected(selection, runroot):
    """Evaluator API: verified selected primary weights, or explicit identity."""
    _validate_selection(selection)
    return _load_candidate(selection["confirmation_candidate"], runroot)


def load_ablation(selection, runroot):
    """Load the separately reported ablation without changing confirmation.

    The original selection envelope remains intact. In particular, copying the
    ablation into confirmation_candidate is rejected by both public loaders.
    """
    _validate_selection(selection)
    selected = selection["ablation"]
    if selected.get("recipe") != "cosine_preservation_ablation" or selected.get("preservation") != 0.05:
        raise ValueError("unexpected_ablation_recipe")
    return _load_candidate(selected, runroot)


def _load_candidate(selected, runroot):
    if selected["kind"] == "identity":
        if selected["epoch"] != 0 or selected["checkpoint"] is not None or selected["checkpoint_sha256"] is not None:
            raise ValueError("invalid_identity_selection")
        return None
    if selected["kind"] != "adapter" or selected["epoch"] < 1:
        raise ValueError("invalid_adapter_selection")
    relative = Path(selected["checkpoint"])
    root = Path(runroot).resolve()
    path = root / relative
    if relative.is_absolute() or ".." in relative.parts or path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("checkpoint_path_outside_run")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != selected["checkpoint_sha256"]:
        raise ValueError("selected_checkpoint_hash_mismatch")
    from safetensors.numpy import load_file
    weights = load_file(str(path))
    if set(weights) != {"a", "b"} or weights["a"].shape != (768,64) or weights["b"].shape != (64,768):
        raise ValueError("unexpected_selected_adapter_shape")
    # Checks dtype, finiteness and output validity with a nonzero probe.
    probe = np.zeros((1,768),dtype=np.float32)
    probe[0,0] = 1
    project_numpy(probe,weights)
    return weights


def mine_visual_hard_negatives(query, gallery, families, k=4):
    """Indices are local to explicitly passed TRAIN arrays, never global rows."""
    q, g = normalize_rows(query), normalize_rows(gallery)
    if q.shape != g.shape or len(families) != len(q) or len(set(families)) < 2 or k < 1:
        raise ValueError("two_train_families_and_aligned_views_required")
    f = np.asarray(families)
    # Symmetric visual similarity supports both directions of the primary loss.
    similarity = 0.5 * (q @ g.T + g @ q.T)
    similarity[f[:, None] == f[None, :]] = -np.inf
    order = np.argsort(-similarity, axis=1, kind="stable")
    result = np.full((len(q), min(k, len(q)-1)), -1, dtype=np.int64)
    for i in range(len(q)):
        valid = order[i][np.isfinite(similarity[i, order[i]])][:result.shape[1]]
        result[i, :len(valid)] = valid
    if np.any(np.all(result < 0, axis=1)):
        raise ValueError("anchor_without_other_family_negative")
    return result


@dataclass(frozen=True)
class AnchorBatch:
    anchors: np.ndarray
    candidates: np.ndarray
    positive_columns: np.ndarray
    exclude: np.ndarray


def make_batch(anchors, candidates, families):
    anchors = np.asarray(anchors, dtype=np.int64)
    candidates = np.asarray(candidates, dtype=np.int64)
    n = len(families)
    if anchors.ndim != 1 or candidates.ndim != 1 or not len(anchors) or len(set(anchors.tolist())) != len(anchors) or len(set(candidates.tolist())) != len(candidates):
        raise ValueError("unique_nonempty_anchor_and_candidate_lists_required")
    if np.any(anchors < 0) or np.any(candidates < 0) or np.any(anchors >= n) or np.any(candidates >= n):
        raise ValueError("train_local_index_out_of_range")
    lookup = {int(item): pos for pos, item in enumerate(candidates)}
    if any(int(a) not in lookup for a in anchors):
        raise ValueError("anchor_was_dropped")
    positives = np.asarray([lookup[int(a)] for a in anchors], dtype=np.int64)
    f = np.asarray(families)
    exclude = (f[anchors, None] == f[None, candidates]) & (anchors[:, None] != candidates[None, :])
    if np.any(exclude[np.arange(len(anchors)), positives]):
        raise ValueError("positive_pair_masked")
    if np.any(np.sum(~exclude, axis=1) < 2):
        raise ValueError("anchor_has_no_valid_negative")
    return AnchorBatch(anchors, candidates, positives, exclude)


def epoch_batches(families, hard_negatives, batch_size=128, seed=17, epoch=0) -> Iterator[AnchorBatch]:
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 2:
        raise ValueError("batch_size_at_least_two_required")
    if epoch < 0 or seed < 0:
        raise ValueError("nonnegative_seed_and_epoch_required")
    n = len(families)
    hard = np.asarray(hard_negatives)
    if hard.ndim != 2 or hard.shape[0] != n or hard.shape[1] < 1 or not np.issubdtype(hard.dtype, np.integer):
        raise ValueError("invalid_train_hard_negative_table")
    for i, row in enumerate(hard):
        valid = row[row >= 0]
        if not len(valid) or np.any(valid >= n) or any(families[int(j)] == families[i] for j in valid):
            raise ValueError("hard_negative_must_be_other_train_family")
    order = np.random.default_rng(np.random.SeedSequence([seed, epoch, 3])).permutation(n)
    anchors_per_batch = max(1, batch_size // 2)
    for offset in range(0, n, anchors_per_batch):
        anchors = order[offset:offset + anchors_per_batch]
        # Keep anchors first. One extra per anchor fits even for batch_size=2.
        candidates = [int(i) for i in anchors]
        seen = set(candidates)
        for i in anchors:
            valid = hard[i][hard[i] >= 0]
            negative = int(valid[epoch % len(valid)])
            if negative not in seen:
                candidates.append(negative)
                seen.add(negative)
        if len(candidates) > batch_size:
            raise RuntimeError("candidate_budget_invariant_broken")
        yield make_batch(anchors, candidates, families)


def metric_key(candidate):
    metrics = candidate["dev"]
    key = (float(metrics["recall_at_1"]), float(metrics["mrr"]))
    if not all(np.isfinite(v) and 0 <= v <= 1 for v in key):
        raise ValueError("invalid_dev_selection_metric")
    return key


def select_with_identity(baseline, candidates):
    if baseline.get("kind") != "identity" or baseline.get("epoch") != 0:
        raise ValueError("explicit_epoch_zero_baseline_required")
    best = baseline
    metric_key(best)
    for candidate in candidates:
        if metric_key(candidate) > metric_key(best):
            best = candidate
        elif metric_key(candidate) == metric_key(best) and candidate.get("kind") == "identity":
            best = candidate
    return best


def make_torch_adapter(dimension=768, rank=64, seed=17, device="cuda:0"):
    import torch
    from torch import nn
    from torch.nn import functional as F
    if dimension < 1 or not 1 <= rank <= dimension:
        raise ValueError("invalid_adapter_dimensions")
    generator = torch.Generator(device="cpu").manual_seed(seed)

    class SharedVisualResidual(nn.Module):
        def __init__(self):
            super().__init__()
            self.a = nn.Parameter(torch.randn(dimension, rank, generator=generator) * 0.01)
            self.b = nn.Parameter(torch.zeros(rank, dimension))

        def forward(self, x):
            return F.normalize(x + (x @ self.a) @ self.b, dim=-1)

    return SharedVisualResidual().to(device)


def symmetric_visual_loss(model, train_query, train_gallery, batch, temperature=0.07, preservation=0.0):
    """Only anchor rows are queries; added negatives never become extra anchors."""
    import torch
    from torch.nn import functional as F
    if temperature <= 0 or preservation not in (0.0, 0.05):
        raise ValueError("unexpected_predeclared_loss_parameters")
    device = train_query.device
    candidates = torch.as_tensor(batch.candidates, device=device)
    positions = torch.as_tensor(batch.positive_columns, device=device)
    excluded = torch.as_tensor(batch.exclude, device=device)
    q_all, g_all = model(train_query[candidates]), model(train_gallery[candidates])
    q, g = q_all[positions], g_all[positions]
    qg = ((q @ g_all.T) / temperature).masked_fill(excluded, -torch.inf)
    gq = ((g @ q_all.T) / temperature).masked_fill(excluded, -torch.inf)
    contrastive = 0.5 * (F.cross_entropy(qg, positions) + F.cross_entropy(gq, positions))
    cosine = torch.zeros((), device=device)
    if preservation:
        original_q = F.normalize(train_query[candidates][positions], dim=-1)
        original_g = F.normalize(train_gallery[candidates][positions], dim=-1)
        cosine = 0.5 * ((1 - (q * original_q).sum(-1)).mean() + (1 - (g * original_g).sum(-1)).mean())
    loss = contrastive + preservation * cosine
    if not torch.isfinite(loss):
        raise RuntimeError("nonfinite_visual_training_loss")
    return loss, {"contrastive": float(contrastive.detach().cpu()), "cosine_preservation": float(cosine.detach().cpu()), "loss_anchor_rows": len(batch.anchors), "candidate_rows": len(batch.candidates)}
