"""ROUGE overlap on caller-supplied tokens, without model/library dependencies."""

import re
from collections import Counter


ROUGE_FIELDS = ("rougeL_recall", "rougeL_precision", "rouge2_recall")
OVERLAP_FIELDS = ROUGE_FIELDS + tuple("body_" + name for name in ROUGE_FIELDS)


def strip_yaml_front_matter(text):
    """Remove a leading fenced metadata block; preserve ordinary Markdown rules.

    Input is normalized Markdown. Recognize a conservative subset of YAML:
    top-level mapping keys, comments and indented value continuations. Require
    an opening '---', a closing '---' or '...', and at least one mapping key.
    Reject unindented prose instead of searching later body text for a key.
    This is a lexical check, not a YAML parser; never execute YAML tags.
    Unclosed, unsupported or ambiguous blocks are left intact.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    has_key = False
    for end, line in enumerate(lines[1:], start=1):
        stripped = line.strip()
        if stripped in ("---", "..."):
            if has_key:
                return "".join(lines[end + 1:]).strip()
            return text
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^[A-Za-z_][\w-]*\s*:(?:\s|$)", line):
            has_key = True
        elif not has_key or not line[0].isspace():
            return text
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
