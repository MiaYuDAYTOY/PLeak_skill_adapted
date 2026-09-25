"""Opt-in, single-process forward tracing for the legacy eager Llama path.

Observe existing results without recomputing attention or retaining tensors.
This temporarily wraps torch.matmul; only use in the standalone diagnostic CLI.
"""
from contextlib import contextmanager, ExitStack
import math
import re

import torch


def _check_range(tensor, label):
    if not tensor.is_floating_point() or tensor.numel() == 0:
        return
    # Reductions avoid allocating a boolean mask the size of the attention matrix.
    with torch.no_grad():
        low, high = torch.aminmax(tensor.detach())
        low, high = low.item(), high.item()
    print(f"[numerics] {label} shape={tuple(tensor.shape)} dtype={tensor.dtype} "
          f"min={low} max={high}", flush=True)
    if not math.isfinite(low) or not math.isfinite(high):
        raise FloatingPointError(f"First non-finite traced value: {label}; "
                                 f"dtype={tensor.dtype} min={low} max={high}")


def _check_output(output, label):
    if isinstance(output, torch.Tensor):
        _check_range(output, label)
    elif isinstance(output, (tuple, list)):
        for index, item in enumerate(output):
            _check_output(item, f"{label}[{index}]")


@contextmanager
def trace_forward_numerics(model):
    """Report the first observed non-finite module/matmul value, then stop."""
    state = {"attention": None, "matmul_index": 0}
    original_matmul = torch.matmul

    def traced_matmul(left, right, *args, **kwargs):
        label = None
        if state['attention'] is not None and left.ndim == 4 and right.ndim == 4:
            state['matmul_index'] += 1
            operation = ('QK before scaling' if state['matmul_index'] == 1
                         else f"attention matmul {state['matmul_index']}")
            label = f"{state['attention']} {operation}"
            _check_range(left, f"{label} left input")
            _check_range(right, f"{label} right input")
        result = original_matmul(left, right, *args, **kwargs)
        if label is not None:
            _check_range(result, f"{label} output")
        return result

    watched = {'embed_tokens', 'input_layernorm', 'post_attention_layernorm',
               'q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj',
               'down_proj', 'self_attn', 'mlp', 'norm', 'lm_head'}
    with ExitStack() as cleanup:
        for name, module in model.named_modules():
            if name.rsplit('.', 1)[-1] not in watched and not re.search(r'(^|\.)layers\.\d+$', name):
                continue
            if name.rsplit('.', 1)[-1] == 'self_attn':
                def before_attention(module, inputs, name=name):
                    state['attention'] = name
                    state['matmul_index'] = 0
                handle = module.register_forward_pre_hook(before_attention)
                cleanup.callback(handle.remove)
            if name.rsplit('.', 1)[-1] == 'down_proj':
                def before_down_proj(module, inputs, name=name):
                    # In Llama this is SiLU(gate_proj(x)) * up_proj(x).
                    # Catch overflow here before a quantized linear turns Inf into NaN.
                    _check_output(inputs, f"{name} input (gated product)")
                handle = module.register_forward_pre_hook(before_down_proj)
                cleanup.callback(handle.remove)

            def after_module(module, inputs, output, name=name):
                _check_output(output, f"{name} output")
                if name == state['attention']:
                    state['attention'] = None
            handle = module.register_forward_hook(after_module)
            cleanup.callback(handle.remove)
        torch.matmul = traced_matmul
        cleanup.callback(setattr, torch, 'matmul', original_matmul)
        yield
