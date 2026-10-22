"""Token IDs usable as plain-text triggers, independent of model family."""

import re


def allowed_trigger_token_ids(tokenizer, embedding_rows=None):
    """Exclude undefined, special, empty and non-ASCII-text candidate tokens.

    A model's padded embedding vocabulary can be larger than its tokenizer.
    Use actual vocabulary IDs, not range(config.vocab_size). The text filter
    retains the existing letters/digits/whitespace trigger search policy.
    """
    special_ids = set(tokenizer.all_special_ids)
    token_ids = sorted({
        int(token_id) for token_id in tokenizer.get_vocab().values()
        if token_id >= 0 and token_id not in special_ids
        and (embedding_rows is None or token_id < embedding_rows)
    })
    texts = tokenizer.batch_decode(
        [[token_id] for token_id in token_ids],
        skip_special_tokens=False, clean_up_tokenization_spaces=False,
    )
    allowed = [token_id for token_id, text in zip(token_ids, texts)
               if text and re.fullmatch(r"[a-zA-Z0-9\s]+", text)]
    if not allowed:
        raise ValueError("Tokenizer has no usable plain-text trigger tokens")
    return allowed
