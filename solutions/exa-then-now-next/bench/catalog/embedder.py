"""Shared helpers for the on-device semantic catalog: paths, prompts and the two embedding runtimes.

EmbeddingGemma (google/embeddinggemma-300m) expects a task prompt in front of every text. The prompts below
are the ones in the model's config_sentence_transformers.json; without them Finnish and English drift apart.

  MLX   mlx-community/embeddinggemma-300m-bf16, Metal GPU. Used to build the index and to serve queries.
  ONNX  onnx-community/embeddinggemma-300m-ONNX (q8). The transformers.js export, i.e. what a browser would run
        to embed the query against the same index. CPU only here.

Nothing in this module calls the network: both models are loaded from bench/catalog/out/models/.
"""
import ctypes
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "bench", "catalog", "out")
DATA = os.environ.get(
    "CFR_DATA",
    "/Users/mikaelervamaa/Library/Mobile Documents/com~apple~CloudDocs/Events/Junction-2026/Datasets/cfr-annual-focused",
)
MODEL_ID = "mlx-community/embeddinggemma-300m-bf16"
MODEL_DIR = os.path.join(OUT, "models", "mlx-community--embeddinggemma-300m-bf16")
ONNX_MODEL_ID = "onnx-community/embeddinggemma-300m-ONNX"
ONNX_DIR = os.path.join(OUT, "models", "onnx-community--embeddinggemma-300m-ONNX")
ONNX_FILE = "onnx/model_quantized.onnx"

QUERY_PREFIX = "task: search result | query: "
DOC_PREFIX = "title: none | text: "
DOC_PREFIX_TITLED = "title: {title} | text: "
DIM = 768


def footprint_gb():
    """(current, lifetime peak) phys_footprint of this process in GB. Counts Metal memory, unlike RSS."""
    try:
        buf = (ctypes.c_uint64 * 64)()
        if ctypes.CDLL("/usr/lib/libproc.dylib").proc_pid_rusage(os.getpid(), 4, ctypes.byref(buf)) != 0:
            return None, None
        return round(buf[2 + 7] / 1e9, 3), round(buf[2 + 28] / 1e9, 3)
    except Exception:
        return None, None


def out_path(name, tag=""):
    """out/<stem>.<tag>.<ext>; the default recipe has no tag."""
    stem, ext = os.path.splitext(name)
    return os.path.join(OUT, f"{stem}.{tag}{ext}" if tag else name)


class MlxEmbedder:
    """EmbeddingGemma on MLX. Returns L2-normalised float32 vectors, one row per input text."""

    runtime = "mlx"
    model_id = MODEL_ID

    def __init__(self, model_dir=MODEL_DIR, cache_mb=256):
        import mlx.core as mx

        mx.set_memory_limit(3 << 30)  # a training job shares this Mac: stay under 3 GB
        mx.set_cache_limit(cache_mb << 20)
        from mlx_embeddings import load

        self.mx = mx
        self.model, tokenizer = load(model_dir)
        self.tok = getattr(tokenizer, "_tokenizer", tokenizer)

    def embed(self, texts, max_tokens=512, batch=16):
        mx = self.mx
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))  # similar lengths together: less padding
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        truncated = 0
        for s in range(0, len(order), batch):
            idx = order[s : s + batch]
            enc = self.tok([texts[i] for i in idx], padding=True, truncation=True, max_length=max_tokens, return_tensors="np")
            truncated += int((enc["attention_mask"].sum(1) >= max_tokens).sum())
            o = self.model(mx.array(enc["input_ids"]), mx.array(enc["attention_mask"]))
            out[idx] = np.array(o.text_embeds.astype(mx.float32))
        self.last_truncated = truncated
        return out

    def peak(self):
        return {"mlx_peak_gb": round(self.mx.get_peak_memory() / 1e9, 3)}


class OnnxEmbedder:
    """EmbeddingGemma q8 on onnxruntime (CPU): the same file transformers.js loads in a browser."""

    runtime = "onnx"
    model_id = ONNX_MODEL_ID

    def __init__(self, model_dir=ONNX_DIR, onnx_file=ONNX_FILE, threads=4):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(os.path.join(model_dir, onnx_file), so, providers=["CPUExecutionProvider"])
        self.tk = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
        self.pad_id = self.tk.token_to_id("<pad>") or 0
        self.in_names = [i.name for i in self.sess.get_inputs()]
        self.out_names = [o.name for o in self.sess.get_outputs()]

    def embed(self, texts, max_tokens=512, batch=8):
        self.tk.enable_truncation(max_length=max_tokens)
        self.tk.enable_padding(pad_id=self.pad_id, pad_token="<pad>")
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        truncated = 0
        for s in range(0, len(order), batch):
            idx = order[s : s + batch]
            encs = self.tk.encode_batch([texts[i] for i in idx])
            feed = {"input_ids": np.array([e.ids for e in encs], dtype=np.int64), "attention_mask": np.array([e.attention_mask for e in encs], dtype=np.int64)}
            truncated += int((feed["attention_mask"].sum(1) >= max_tokens).sum())
            res = dict(zip(self.out_names, self.sess.run(None, {k: v for k, v in feed.items() if k in self.in_names})))
            e = res["sentence_embedding"]
            out[idx] = (e / np.linalg.norm(e, axis=1, keepdims=True)).astype(np.float32)
        self.last_truncated = truncated
        return out

    def peak(self):
        return {}


def load_embedder(runtime="mlx"):
    return MlxEmbedder() if runtime == "mlx" else OnnxEmbedder()
