"""Small, opt-in CUDA diagnostics and mandatory non-finite guards."""
import os

import torch


def diagnostics_enabled():
    return os.environ.get("PLEAK_DEBUG", "0") == "1"


def print_cuda_memory(tag, *, enabled=None):
    if enabled is None:
        enabled = diagnostics_enabled()
    if not enabled:
        return
    if not torch.cuda.is_available():
        print(f"[memory] {tag}: CUDA unavailable", flush=True)
        return
    for device in range(torch.cuda.device_count()):
        print(
            f"[memory] {tag} cuda:{device}",
            f"allocated={torch.cuda.memory_allocated(device) / 1024**3:.4f} GiB",
            f"reserved={torch.cuda.memory_reserved(device) / 1024**3:.4f} GiB",
            f"peak={torch.cuda.max_memory_allocated(device) / 1024**3:.4f} GiB",
            flush=True,
        )


def require_finite(value, name, context):
    if not torch.isfinite(value).all().item():
        raise FloatingPointError(f"{context}: non-finite {name}; stopping before trigger update")
