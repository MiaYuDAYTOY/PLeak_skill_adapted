"""Decode generated tokens without rewriting the model's text."""

GENERATION_DECODE_POLICY = "preserve_whitespace_skip_special_v1"


def decode_generation(tokenizer, token_ids, *, skip_special_tokens=True):
    """Keep whitespace, Markdown, repeated text and trigger echoes intact.

    The evaluation view skips tokenizer-designated special tokens. The raw
    audit view passes skip_special_tokens=False and retains them as well.
    """
    return tokenizer.decode(
        token_ids,
        skip_special_tokens=skip_special_tokens,
        clean_up_tokenization_spaces=False,
    )
