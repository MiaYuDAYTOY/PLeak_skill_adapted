"""ROUGE overlap on caller-supplied tokens, without model/library dependencies."""

import re
from collections import Counter


ROUGE_FIELDS = ("rougeL_recall", "rougeL_precision", "rouge2_recall")
OVERLAP_FIELDS = ROUGE_FIELDS + tuple("body_" + name for name in ROUGE_FIELDS)


def strip_yaml_front_matter(text):
    """Remove a leading fenced metadata block; preserve ordinary Markdown rules.

    Input is normalized Markdown. Require an opening '---', a closing '---'
    or '...', and at least one top-level YAML-style mapping key. This is a
    conservative lexical check, not a YAML parser; never execute YAML tags.
    Unclosed blocks and documents without front matter are left intact.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    for end in range(1, len(lines)):
        if lines[end].strip() in ("---", "..."):
            header = "".join(lines[1:end])
            if re.search(r"^[A-Za-z_][\w-]*\s*:", header, re.MULTILINE):
                return "".join(lines[end + 1:]).strip()
            break
    return text


def longest_common_subsequence_length(reference, prediction):
    """Exact LCS length using a bit-parallel dynamic program.

    Each bit in state represents an increment in one DP row. Python's integer
    operations avoid allocating a quadratic table for long skill documents.
    """
    if len(reference) > len(prediction):
        reference, prediction = prediction, reference
    masks = {}
    for index, token in enumerate(reference):
        masks[token] = masks.get(token, 0) | (1 << index)
    state = 0
    for token in prediction:
        matches = state | masks.get(token, 0)
        state = matches & ~(matches - ((state << 1) | 1))
    return bin(state).count("1")


def rouge_overlap(reference, prediction):
    """Return whole-sequence ROUGE-L R/P and clipped bigram ROUGE-2 recall.

    Empty denominators (including a reference shorter than two tokens for
    ROUGE-2) score zero. No stemming, case folding or deduplication is applied.
    """
    lcs = longest_common_subsequence_length(reference, prediction)
    ref_bigrams = Counter(zip(reference, reference[1:]))
    pred_bigrams = Counter(zip(prediction, prediction[1:]))
    common_bigrams = sum((ref_bigrams & pred_bigrams).values())
    return {
        "rougeL_recall": lcs / len(reference) if reference else 0.0,
        "rougeL_precision": lcs / len(prediction) if prediction else 0.0,
        "rouge2_recall": common_bigrams / (len(reference) - 1)
        if len(reference) > 1 else 0.0,
    }
