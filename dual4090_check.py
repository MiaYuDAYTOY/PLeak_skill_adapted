"""One bounded dual-4090 check: longest planned training and retained test input.

Reuses production model loading, HotFlip loss, and Sampler generation. No search.
Each GPU stage runs in its own process, so OOM state cannot leak into the next one.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parent
TRIGGER = ROOT / ('results/documents_train3-4-5_20260927_144503_54uehhb5/'
    'documents_12_llama_llama_train3_test70_target_prefix8_dtypebfloat16_gc'
    '_repeat1_sample_seed1_attack_seed2.trigger_ids.json')


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def content(path):
    text = Path(path).read_text(encoding='utf-8')
    return text if text.endswith('\n') else text + '\n'


class OneSample:
    def __init__(self, record):
        text = content(record['path'])
        if hashlib.sha256(text.encode()).hexdigest() != record['content_sha256']:
            raise ValueError('Sample content changed after planning')
        self.dataset = [{'content': text}]
        self.sample_metadata = [record]

    def __len__(self):
        return 1

    def __getitem__(self, index):
        return self.dataset[index]['content']


def seed_all(seed):
    import numpy as np
    import torch
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def factory(model_path=None):
    from ModelFactory import ModelFactory
    obj = ModelFactory()
    if model_path:
        obj.MODEL_CONF['llama']['alias'] = model_path
    return obj


def cpu_attack(tokenizer, prefix, seed):
    import torch
    from Attack import HotFlip
    from util.template import TextTemplate
    seed_all(seed)
    attack = HotFlip.__new__(HotFlip)
    attack.device = torch.device('cpu')
    attack.target_model = 'llama'
    attack.template = TextTemplate(prefix_1='', prefix_2='')
    attack.tokenizer = tokenizer
    attack.vocab_size = factory().get_vocab_size('llama')
    attack.user_prefix = ''
    attack.prefix_length = prefix
    attack.trigger_tokens = attack.init_triggers(12)
    return attack


def make_plan(args):
    import main as experiment
    import numpy as np
    tokenizer = factory(args.model_path).get_tokenizer('llama')
    prefix = args.prefix_length or max(experiment.PREFIX_LENGTHS)
    attack = cpu_attack(tokenizer, prefix, 1)
    train_ids = attack.trigger_tokens.tolist()
    test_ids = json.loads(args.trigger_ids.read_text())
    if len(test_ids) != 12 or any(type(x) is not int or not 0 <= x < attack.vocab_size for x in test_ids):
        raise ValueError('Expected 12 valid generation trigger IDs')
    trigger = attack._decode_trigger_tokens(np.asarray(test_ids))
    files = sorted((ROOT / 'data/skill_expansion_20260922/samples/documents').rglob('SKILL.md'))
    random.Random(0).shuffle(files)
    split = int(len(files) * .3)
    pool, tests = files[:split], files[split:]
    indices = sorted({i for n in experiment.TRAIN_NUMS for seed in experiment.SAMPLE_SEEDS
                      for i in random.Random(seed).sample(range(len(pool)), n)})
    train_records, test_records = [], []
    def record(path, index):
        return {'path': str(path.resolve()), 'pool_index': index,
                'content_sha256': hashlib.sha256(content(path).encode()).hexdigest()}
    for i in indices:
        r = record(pool[i], i)
        inputs, labels, _, _ = attack.make_target(i, 0, content(pool[i]), attack.trigger_tokens)
        r.update(input_tokens=inputs.shape[1], supervised_tokens=int(labels.ne(-100).sum()))
        train_records.append(r)
    for i, path in enumerate(tests):
        if path.parent.name in experiment.KNOWN_OOM_TEST_SKILLS.get('documents', set()):
            continue
        r = record(path, i)
        prompt = content(path) + attack.template.format_trigger(trigger)
        length = len(tokenizer.encode(prompt, add_special_tokens=True))
        r.update(prompt_tokens=length, max_length=2 * length + 50, max_new_tokens=length + 50)
        test_records.append(r)
    plan = {
        'train_scope': {'train_nums': experiment.TRAIN_NUMS, 'sample_seeds': experiment.SAMPLE_SEEDS,
                        'unique_samples': len(train_records)},
        'test_policy': 'current_known_oom_exclusions', 'retained_test_count': len(test_records),
        'prefix_length': prefix, 'train_seed': 1, 'generation_seed': 1,
        'train_trigger_ids': train_ids, 'generation_trigger_ids': test_ids,
        'generation_trigger_source': str(args.trigger_ids.resolve()), 'generation_trigger_text': trigger,
        'train': max(train_records, key=lambda x: x['input_tokens']),
        'generate': max(test_records, key=lambda x: x['prompt_tokens']),
        'model_path': args.model_path, 'dtype': 'bfloat16', 'quantization': '4bit',
        'device_map': 'auto', 'checkpoint_training_only': True,
        'generation': {'num_beams': 3, 'do_sample': True, 'temperature': .9, 'top_p': .6,
                       'max_length_rule': '2 * prompt_tokens + 50'},
        'train_candidates': train_records, 'test_candidates': test_records,
        'versions': {name: importlib.metadata.version(name) for name in
                     ['torch', 'transformers', 'bitsandbytes', 'accelerate', 'tokenizers']},
    }
    # Llama-2-7B has 32 attention heads; this is ONE matrix, not total memory.
    plan['eager_fp32_matrix_estimate_GiB'] = {
        'assumed_num_attention_heads': 32,
        'train_batch1': 32 * plan['train']['input_tokens']**2 * 4 / 1024**3,
        'generation_prefill_3beams': 3 * 32 * plan['generate']['prompt_tokens']**2 * 4 / 1024**3,
        'generation_at_budget_3beams_no_cache': 3 * 32 * (plan['generate']['max_length'] - 1)**2 * 4 / 1024**3,
    }
    return plan


def memory(reset=False):
    import torch
    result = {}
    for device in range(torch.cuda.device_count()):
        torch.cuda.synchronize(device)
        if reset:
            torch.cuda.reset_peak_memory_stats(device)
        free, total = torch.cuda.mem_get_info(device)
        result[str(device)] = {
            'name': torch.cuda.get_device_name(device), 'total_GiB': total / 1024**3,
            'free_now_GiB': free / 1024**3,
            'allocated_GiB': torch.cuda.memory_allocated(device) / 1024**3,
            'peak_allocated_GiB': torch.cuda.max_memory_allocated(device) / 1024**3,
            'peak_reserved_GiB': torch.cuda.max_memory_reserved(device) / 1024**3,
        }
    return result


def gpu_stage(args):
    import torch
    import numpy as np
    plan = json.loads(args.plan.read_text())
    result = {'stage': args.stage, 'status': 'started', 'sample': plan[args.stage]}
    destination = args.output_dir / f'{args.stage}.json'
    save(destination, result)
    start = time.monotonic()
    try:
        if torch.cuda.device_count() != 2 or any('4090' not in torch.cuda.get_device_name(i) for i in range(2)):
            raise RuntimeError('GPU stages require exactly two visible RTX 4090s; use CUDA_VISIBLE_DEVICES=0,1')
        seed_all(1)
        result['before_load'] = memory(reset=True)
        model = factory(plan['model_path']).get_model('llama', compute_dtype=torch.bfloat16)
        mapping = getattr(model, 'hf_device_map', {})
        result['hf_device_map'] = {k: str(v) for k, v in mapping.items()}
        devices = {str(v).replace('cuda:', '') for v in mapping.values()}
        if devices != {'0', '1'}:
            raise RuntimeError(f'Model must be on both GPUs without CPU/disk offload, got {devices}')
        result['embedding_dtype'] = str(model.get_input_embeddings().weight.dtype)
        result['bnb_compute_dtypes'] = sorted({str(m.compute_dtype) for m in model.modules()
                                              if hasattr(m, 'compute_dtype')})
        result['attention_classes'] = sorted({type(m).__name__ for n, m in model.named_modules()
                                              if n.endswith('self_attn')})
        result['model_use_cache'] = model.config.use_cache
        result['num_attention_heads'] = model.config.num_attention_heads
        result['after_load'] = memory()
        result['load_seconds'] = time.monotonic() - start
        save(destination, result)
        tokenizer = factory(plan['model_path']).get_tokenizer('llama')
        sample = OneSample(plan[args.stage])
        memory(reset=True)
        compute_start = time.monotonic()
        if args.stage == 'train':
            model.gradient_checkpointing_enable()
            attack = cpu_attack(tokenizer, plan['prefix_length'], plan['train_seed'])
            attack.device = torch.device('cuda:0')
            attack.model = model
            ids = np.asarray(plan['train_trigger_ids'])
            loss, gradient = attack.compute_loss(sample, ids, 0, require_grad=True)
            result.update(loss=loss, gradient_shape=list(gradient.shape),
                          gradient_finite=bool(torch.isfinite(gradient).all().item()),
                          gradient_norm=float(gradient.float().norm().item()))
            if not result['gradient_finite'] or result['gradient_norm'] == 0:
                raise RuntimeError('Missing, zero, or non-finite trigger gradient')
        else:
            from Sampler import Sampler
            from util.template import TextTemplate
            sampler = Sampler.__new__(Sampler)
            sampler.device = torch.device('cuda:0')
            sampler.target_model = 'llama'
            sampler.template = TextTemplate(prefix_1='', prefix_2='')
            sampler.model, sampler.tokenizer = model, tokenizer
            sampler.defender = None
            model.eval()
            seed_all(plan['generation_seed'])
            outputs = sampler.sample_sequence(sample, plan['generation_trigger_text'],
                                              trigger_token_ids=plan['generation_trigger_ids'])
            Sampler.save_to_csv(str(args.output_dir / 'generation.csv'), outputs,
                                plan['generation_trigger_text'])
            row = outputs[0]
            result['generation'] = {k: row[k] for k in
                ['status', 'error', 'prompt_token_count', 'generated_token_count', 'ended_with_eos']}
            result['reached_length_budget'] = row['generated_token_count'] == plan['generate']['max_new_tokens']
            if row['status'] != 'ok':
                raise RuntimeError(row['error'])
        result['compute_seconds'] = time.monotonic() - compute_start
        result['status'] = 'passed'
    except Exception as error:
        result.update(status='failed', error=repr(error))
        traceback.print_exc()
    finally:
        result['elapsed_seconds'] = time.monotonic() - start
        try:
            result['memory'] = memory()
        except Exception as error:
            result['memory_error'] = repr(error)
        save(destination, result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['plan', 'all', 'train', 'generate'], default='plan')
    parser.add_argument('--timeout-minutes', type=float, default=20)
    parser.add_argument('--prefix-length', type=int, default=None)
    parser.add_argument('--trigger-ids', type=Path, default=TRIGGER)
    parser.add_argument('--model-path', default=None)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--plan', type=Path)
    args = parser.parse_args()
    if not 0 < args.timeout_minutes < float('inf') or (args.prefix_length is not None and args.prefix_length <= 0):
        parser.error('Timeout and prefix length must be positive and finite')
    if args.output_dir is None:
        (ROOT / 'results').mkdir(exist_ok=True)
        args.output_dir = Path(tempfile.mkdtemp(prefix='dual4090_', dir=ROOT / 'results'))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.stage in ('train', 'generate'):
        if args.plan is None:
            parser.error('GPU child stages require --plan; use --stage all')
        return gpu_stage(args)
    started = time.monotonic()
    plan = make_plan(args)
    plan_path = args.output_dir / 'plan.json'
    save(plan_path, plan)
    print('Output:', args.output_dir, flush=True)
    for phase in ['train', 'generate']:
        print(phase, json.dumps(plan[phase]), flush=True)
    print('One eager FP32 attention matrix (GiB):',
          json.dumps(plan['eager_fp32_matrix_estimate_GiB']), flush=True)
    if plan['eager_fp32_matrix_estimate_GiB']['train_batch1'] > 24:
        print('WARNING: one training attention matrix alone exceeds 24 GiB; '
              'layer sharding across two GPUs cannot split that matrix.', flush=True)
    if args.stage == 'plan':
        return 0
    summary = {'timeout_minutes': args.timeout_minutes, 'stages': {}}
    for phase in ['train', 'generate']:
        remaining = args.timeout_minutes * 60 - (time.monotonic() - started)
        if remaining <= 0:
            summary['stages'][phase] = {'status': 'not_run_time_budget_exhausted'}
            continue
        cmd = [sys.executable, '-u', str(Path(__file__).resolve()), '--stage', phase,
               '--plan', str(plan_path), '--output-dir', str(args.output_dir)]
        env = dict(os.environ, PLEAK_DEBUG='1')
        print(f'Starting {phase}; remaining wall-time budget {remaining:.0f}s', flush=True)
        try:
            completed = subprocess.run(cmd, env=env, timeout=remaining, check=False)
            path = args.output_dir / f'{phase}.json'
            summary['stages'][phase] = json.loads(path.read_text()) if path.exists() else {'status': 'failed_before_report'}
            summary['stages'][phase]['exit_code'] = completed.returncode
        except subprocess.TimeoutExpired:
            summary['stages'][phase] = {'status': 'timeout', 'note': 'Timeout is not proof of OOM'}
        save(args.output_dir / 'summary.json', summary)
    summary['elapsed_seconds'] = time.monotonic() - started
    summary['both_stages_passed'] = all(summary['stages'][s].get('status') == 'passed' and
                                       summary['stages'][s].get('exit_code') == 0 for s in ['train', 'generate'])
    save(args.output_dir / 'summary.json', summary)
    print('Finished:', args.output_dir / 'summary.json', flush=True)
    print('Both stages passed:', summary['both_stages_passed'], flush=True)
    return 0 if summary['both_stages_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
