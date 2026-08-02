VALID_LOSS_MODES = {
    "baseline",
    "full",
    "prefix_cap",
    "anchor_frontier",
    "self_conditioned_frontier",
}

FULL_LOSS_MODES = {"baseline", "full"}
FRONTIER_LOSS_MODES = {
    "anchor_frontier",
    "self_conditioned_frontier",
}


def validate_loss_mode(loss_mode):
    if not isinstance(loss_mode, str) or loss_mode not in VALID_LOSS_MODES:
        allowed = ", ".join(sorted(VALID_LOSS_MODES))
        raise ValueError(
            f"Invalid loss_mode {loss_mode!r}. Expected one of: {allowed}"
        )


def _validate_int(name, value, minimum):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        comparison = ">= 0" if minimum == 0 else "> 0"
        raise ValueError(f"{name} must be an integer {comparison}; got {value!r}")


def validate_loss_parameters(
    loss_mode,
    max_loss_tokens,
    anchor_len,
    frontier_window,
    max_frontier_tokens,
    frontier_lambda=1.0,
):
    validate_loss_mode(loss_mode)
    _validate_int("max_loss_tokens", max_loss_tokens, 1)
    _validate_int("anchor_len", anchor_len, 0)
    _validate_int("frontier_window", frontier_window, 0)

    if max_frontier_tokens is not None:
        _validate_int("max_frontier_tokens", max_frontier_tokens, 1)

    if (
        isinstance(frontier_lambda, bool)
        or not isinstance(frontier_lambda, (int, float))
        or frontier_lambda <= 0
    ):
        raise ValueError(
            "frontier_lambda must be a positive number; "
            f"got {frontier_lambda!r}"
        )

    if (
        loss_mode in FRONTIER_LOSS_MODES
        and anchor_len == 0
        and frontier_window == 0
    ):
        raise ValueError(
            "anchor_frontier requires anchor_len or frontier_window to be positive"
        )

    if loss_mode == "self_conditioned_frontier" and anchor_len == 0:
        raise ValueError(
            "self_conditioned_frontier requires anchor_len to be positive"
        )

    if loss_mode == "self_conditioned_frontier" and frontier_window == 0:
        raise ValueError(
            "self_conditioned_frontier requires frontier_window to be positive"
        )


def get_effective_max_len(
    loss_mode,
    target_len,
    max_loss_tokens=300,
    max_frontier_tokens=None,
):
    validate_loss_mode(loss_mode)
    _validate_int("target_len", target_len, 0)

    if loss_mode == "prefix_cap":
        _validate_int("max_loss_tokens", max_loss_tokens, 1)
        return min(target_len, max_loss_tokens)

    if loss_mode in FRONTIER_LOSS_MODES and max_frontier_tokens is not None:
        _validate_int("max_frontier_tokens", max_frontier_tokens, 1)
        return min(target_len, max_frontier_tokens)

    return target_len


def iter_stage_ends(init_step, step, effective_max_len):
    _validate_int("init_step", init_step, 1)
    _validate_int("step", step, 1)
    _validate_int("effective_max_len", effective_max_len, 0)

    idx_loss = 0
    while effective_max_len > 0:
        stage_end = min(
            init_step + idx_loss * step,
            effective_max_len,
        )
        yield stage_end

        if stage_end >= effective_max_len:
            break

        idx_loss += 1


def iter_stage_ranges(init_step, step, effective_max_len):
    """Yield adjacent ``[start, end)`` stage chunks without gaps or overlap."""
    stage_start = 0
    for stage_end in iter_stage_ends(init_step, step, effective_max_len):
        yield stage_start, stage_end
        stage_start = stage_end


def get_loss_regions(
    loss_mode,
    stage_end,
    anchor_len=64,
    frontier_window=64,
):
    validate_loss_mode(loss_mode)
    _validate_int("stage_end", stage_end, 1)

    if loss_mode not in FRONTIER_LOSS_MODES:
        return ((0, stage_end),)

    _validate_int("anchor_len", anchor_len, 0)
    _validate_int("frontier_window", frontier_window, 0)
    if anchor_len == 0 and frontier_window == 0:
        raise ValueError(
            "anchor_frontier requires anchor_len or frontier_window to be positive"
        )

    anchor_end = min(anchor_len, stage_end)
    frontier_start = max(
        anchor_end,
        stage_end - frontier_window,
    )
    return (
        (0, anchor_end),
        (frontier_start, stage_end),
    )


def get_separate_loss_regions(
    loss_mode,
    stage_end,
    anchor_len=128,
    frontier_window=128,
):
    """Return independently normalized anchor and frontier regions.

    Unlike :func:`get_loss_regions`, overlap is intentionally preserved.  The
    caller computes each region's mean loss separately, so an overlapping
    frontier receives its explicit extra weight instead of being collapsed
    into a union mask.
    """
    validate_loss_mode(loss_mode)
    _validate_int("stage_end", stage_end, 1)
    _validate_int("anchor_len", anchor_len, 0)
    _validate_int("frontier_window", frontier_window, 0)

    anchor_end = min(anchor_len, stage_end)
    frontier_start = max(0, stage_end - frontier_window)
    return (0, anchor_end), (frontier_start, stage_end)


def build_target_labels(
    loss_mode,
    target_ids,
    stage_end,
    anchor_len=64,
    frontier_window=64,
):
    _validate_int("stage_end", stage_end, 1)
    if stage_end > len(target_ids):
        raise ValueError(
            f"stage_end ({stage_end}) exceeds target length ({len(target_ids)})"
        )

    regions = get_loss_regions(
        loss_mode=loss_mode,
        stage_end=stage_end,
        anchor_len=anchor_len,
        frontier_window=frontier_window,
    )
    target_prefix = list(target_ids[:stage_end])

    if loss_mode not in FRONTIER_LOSS_MODES:
        return target_prefix

    target_labels = [-100] * stage_end
    for start, end in regions:
        target_labels[start:end] = target_prefix[start:end]

    if not any(label != -100 for label in target_labels):
        raise ValueError("loss mask must contain at least one active target token")

    return target_labels
