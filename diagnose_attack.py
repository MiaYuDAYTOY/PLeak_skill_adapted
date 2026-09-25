"""Diagnose one fixed input/trigger configuration without optimizing triggers."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import random
from contextlib import nullcontext


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--token-length', type=int, required=True)
    parser.add_argument('--prefix-length', type=int, default=8)
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--mode', choices=['tokens', 'eval', 'train-no-grad', 'grad', 'checkpoint'],
                        default='tokens')
    parser.add_argument('--samples-json', type=Path)
    parser.add_argument('--trigger-ids', type=Path)
    parser.add_argument('--sample-index', type=int, help='Probe only this index in the selected samples')
    parser.add_argument('--trace-numerics', action='store_true',
                        help='Trace module and eager attention matmul ranges; no-grad modes only')
    parser.add_argument('--dtype', choices=['float16', 'bfloat16'], default=None,
                        help='Explicitly set both model and 4-bit compute dtype; default keeps current loading')
    args = parser.parse_args()
    if args.token_length <= 0 or args.prefix_length <= 0:
        parser.error('token-length and prefix-length must be positive')
    if args.trace_numerics and args.mode not in ('eval', 'train-no-grad'):
        parser.error('--trace-numerics requires --mode eval or --mode train-no-grad')
    return args


class SelectedSamples:
    def __init__(self, paths):
        self.dataset = [{'content': p.read_text(encoding='utf-8')} for p in paths]
        self.sample_metadata = [{'path': str(p.resolve())} for p in paths]

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, index):
        content = self.dataset[index]['content']
        return content if content.endswith('\n') else content + '\n'


def main():
    args = parse_args()
    os.environ['PLEAK_DEBUG'] = '1'
    import numpy as np
    import torch
    from Attack import HotFlip
    from ModelFactory import ModelFactory
    from util.attack_diagnostics import print_cuda_memory
    from util.template import TextTemplate

    root = Path(__file__).resolve().parent
    names = ['030_documentation-and-adrs', '053_minimax-xlsx', '060_pdf-creator']
    paths = [root / 'data/skill_expansion_20260922/samples/documents' / name / 'SKILL.md'
             for name in names]
    if args.samples_json:
        selection = json.loads(args.samples_json.read_text(encoding='utf-8'))
        if (selection['token_length'] != args.token_length or
                selection['prefix_length'] != args.prefix_length):
            raise ValueError('token/prefix lengths must match samples.json')
        if selection['shadow_model'] != 'llama':
            raise ValueError('This diagnostic currently targets shadow_model=llama')
        paths = [Path(m['path']) for m in selection['train_samples']]
        if args.seed is None:
            args.seed = selection['attack_seed']
    if args.seed is None:
        args.seed = 1
    if args.sample_index is not None:
        if not 0 <= args.sample_index < len(paths):
            raise ValueError('sample-index is outside the selected samples')
        print('Selected original sample index:', args.sample_index, flush=True)
        paths = [paths[args.sample_index]]
    samples = SelectedSamples(paths)
    for package in ['torch', 'transformers', 'bitsandbytes', 'accelerate', 'tokenizers']:
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = 'not installed'
        print(package, version, flush=True)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    if args.mode == 'tokens':
        # Use the real tokenizer and make_target without allocating model weights.
        factory = ModelFactory()
        attack = HotFlip.__new__(HotFlip)
        attack.device = torch.device('cpu')
        attack.target_model = 'llama'
        attack.template = TextTemplate(prefix_1='', prefix_2='')
        attack.tokenizer = factory.get_tokenizer('llama')
        attack.vocab_size = factory.get_vocab_size('llama')
        attack.user_prefix = ''
        attack.prefix_length = args.prefix_length
        attack.trigger_tokens = attack.init_triggers(args.token_length)
    else:
        attack = HotFlip(trigger_token_length=args.token_length, shadow_model='llama',
                         template=TextTemplate(prefix_1='', prefix_2=''),
                         prefix_length=args.prefix_length,
                         compute_dtype=None if args.dtype is None else getattr(torch, args.dtype))
    if args.trigger_ids:
        ids = json.loads(args.trigger_ids.read_text(encoding='utf-8'))
        if (not isinstance(ids, list) or len(ids) != args.token_length or
                any(type(t) is not int or not 0 <= t < attack.vocab_size for t in ids)):
            raise ValueError('trigger-ids must be a list of token-length valid integer IDs')
        attack.trigger_tokens = np.asarray(ids, dtype=int)
        attack._decode_trigger_tokens(attack.trigger_tokens)
    print('mode=', args.mode, 'seed=', args.seed, 'trigger_ids=', attack.trigger_tokens.tolist(), flush=True)
    print('tokenizer=', type(attack.tokenizer).__name__, attack.tokenizer.name_or_path, flush=True)
    # Report all lengths before a potentially failing model forward.
    for index, text in enumerate(samples):
        print(attack._sample_context(samples, index),
              'raw_chars=', len(samples.dataset[index]['content']), flush=True)
        result = attack.make_target(index, 0, text, attack.trigger_tokens)
        del result
    if args.mode == 'tokens':
        return
    model = attack.model
    if args.mode == 'checkpoint':
        model.gradient_checkpointing_enable()
    model.train(args.mode in ('train-no-grad', 'checkpoint'))
    print('training=', model.training, 'checkpointing=', model.is_gradient_checkpointing,
          'embedding_dtype=', model.get_input_embeddings().weight.dtype, flush=True)
    print('requested_dtype=', args.dtype, 'bnb_compute_dtypes=',
          sorted({str(m.compute_dtype) for m in model.modules() if hasattr(m, 'compute_dtype')}), flush=True)
    print('attention_classes=', sorted({type(m).__name__ for n, m in model.named_modules()
                                       if n.endswith('self_attn')}), flush=True)
    print('config=', {key: getattr(model.config, key, None) for key in (
        'use_cache', 'output_attentions', 'output_hidden_states', '_attn_implementation',
        'hidden_size', 'num_hidden_layers', 'num_attention_heads', 'num_key_value_heads',
        'max_position_embeddings')}, flush=True)
    print('forward explicitly uses use_cache/output_attentions/output_hidden_states=False', flush=True)
    print('trainable_parameters=', [(n, p.numel(), str(p.dtype)) for n, p in model.named_parameters()
                                    if p.requires_grad], flush=True)
    # Checkpoint mode stays in training mode through backward, as required by 4.32.1.
    trace = nullcontext()
    if args.trace_numerics:
        from util.numerics_trace import trace_forward_numerics
        trace = trace_forward_numerics(model)
    with trace:
        loss, gradient = attack.compute_loss(samples, attack.trigger_tokens, 0,
                                            require_grad=args.mode in ('grad', 'checkpoint'))
    print('finite mean loss=', loss, 'trigger_gradient_shape=',
          None if gradient is None else tuple(gradient.shape), flush=True)
    print('parameter_grad_GiB=', sum(p.grad.numel() * p.grad.element_size()
          for p in model.parameters() if p.grad is not None) / 1024**3, flush=True)
    print_cuda_memory('diagnostic complete')


if __name__ == '__main__':
    main()
