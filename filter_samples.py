"""Select a fixed short-skill subset before the train/test split.

This module never changes source files and does not inspect generated triggers.
The startup budget reserves space for a future trigger, template and boundaries;
it is not a measurement of an actual, fully assembled inference prompt.
"""

import hashlib
import json
from pathlib import Path


GENERATION_EXTRA_TOKENS = 50  # Sampler.sample_sequence's unchanged default.
BOUNDARY_RESERVE_TOKENS = 8


def filter_skill_files(files, tokenizer, *, context_limit, trigger_token_reserve,
                       template, enabled=True):
    """Return eligible paths and an auditable manifest, without splitting yet."""
    if not enabled:
        paths = sorted(Path(path).resolve() for path in files)
        return paths, {
            "policy": "none",
            "enabled": False,
            "source_count": len(paths),
            "kept_count": len(paths),
            "excluded_count": 0,
            "kept_samples": [{"path": str(path)} for path in paths],
            "excluded_samples": [],
        }

    if context_limit <= GENERATION_EXTRA_TOKENS:
        raise ValueError("Context limit must exceed the generation extra tokens")
    if trigger_token_reserve <= 0:
        raise ValueError("Trigger token reserve must be positive")

    prompt_limit = (context_limit - GENERATION_EXTRA_TOKENS) // 2
    # Encode with the same special-token behavior as Sampler. The empty-trigger
    # template reserves its prefix and final newline separately; the additional
    # margin keeps borderline examples away from tokenization boundary changes.
    template_tokens = len(tokenizer.encode(
        template.format_trigger(""), add_special_tokens=False, truncation=False,
    ))
    reserved_tokens = (
        trigger_token_reserve + template_tokens + BOUNDARY_RESERVE_TOKENS
    )
    if reserved_tokens >= prompt_limit:
        raise ValueError("Trigger/template reserves leave no room for skill content")

    kept, excluded = [], []
    paths = sorted(Path(path).resolve() for path in files)
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate source paths in length-filter input")
    for source_index, path in enumerate(paths):
        content = path.read_text(encoding="utf-8")
        # Match Samples.__getitem__, including its trailing newline.
        text = content if content.endswith("\n") else content + "\n"
        content_tokens = len(tokenizer.encode(
            text, add_special_tokens=True, truncation=False,
        ))
        budgeted_prompt_tokens = content_tokens + reserved_tokens
        record = {
            "path": str(path),
            "source_index": source_index,
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "content_tokens_with_special_tokens": content_tokens,
            "budgeted_prompt_tokens": budgeted_prompt_tokens,
            "budgeted_max_length": 2 * budgeted_prompt_tokens + GENERATION_EXTRA_TOKENS,
        }
        if budgeted_prompt_tokens <= prompt_limit:
            kept.append(record)
        else:
            excluded.append({**record, "reason": "context_budget_exceeded"})

    manifest = {
        "policy": "pre_split_length_filter_v1",
        "enabled": True,
        "tokenizer": str(getattr(tokenizer, "name_or_path", type(tokenizer).__name__)),
        "context_limit": context_limit,
        "generation_extra_tokens": GENERATION_EXTRA_TOKENS,
        "prompt_token_limit": prompt_limit,
        "trigger_token_reserve": trigger_token_reserve,
        "template_token_reserve": template_tokens,
        "boundary_token_reserve": BOUNDARY_RESERVE_TOKENS,
        "content_token_limit_with_special_tokens": prompt_limit - reserved_tokens,
        "source_count": len(paths),
        "kept_count": len(kept),
        "excluded_count": len(excluded),
        "kept_samples": kept,
        "excluded_samples": excluded,
    }
    return [Path(sample["path"]) for sample in kept], manifest


def save_filter_manifest(path, manifest):
    """Write once so previous selections cannot be silently overwritten."""
    with Path(path).open("x", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
        file.write("\n")
