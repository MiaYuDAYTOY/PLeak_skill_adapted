"""Replay the historical seed-1 success and compare checkpoint gradients.

No trigger optimization and no changes to production experiment defaults.
"""
import argparse
import csv
import gc
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import tempfile

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / 'results/web/seed 1/webtesting_12_llama_llama_3_target_prefix8_seed1.csv'


def normalized(text):
    return text.replace('\r\n', '\n').replace('\r', '\n').strip()


def prepare(root=ROOT, reference=REFERENCE):
    """Restore the historical 80/20 split, not today's 30/70 split."""
    files = sorted((root / 'data/webapp').rglob('SKILL.md'))
    if len(files) != 100:
        raise ValueError('Historical regression requires the original 100 webapp files')
    random.Random(0).shuffle(files)
    train_paths, test_paths = files[:3], files[80:]
    with reference.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(test_paths):
        raise ValueError('Historical test count changed')
    for path, row in zip(test_paths, rows):
        text = path.read_text(encoding='utf-8')
        text += '' if text.endswith('\n') else '\n'
        if text != row['context']:
            raise ValueError(f'Historical test content/order mismatch: {path}')
    trigger = rows[0]['trigger']
    if any(row['trigger'] != trigger for row in rows):
        raise ValueError('Reference CSV contains multiple triggers')
    ids = json.loads(reference.with_suffix('.trigger_ids.json').read_text())
    if len(ids) != 12 or any(type(x) is not int for x in ids):
        raise ValueError('Expected 12 historical trigger IDs')
    def metadata(paths):
        return [{'path': str(p), 'sha256_raw': hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in paths]
    return {
        'reference_csv': str(reference), 'historical_attack_seed': 1,
        'historical_full_reproductions': sum(
            bool(normalized(r['context'])) and
            normalized(r['generation']).startswith(normalized(r['context']))
            for r in rows),
        'historical_test_count': len(rows),
        'train_samples': metadata(train_paths), 'test_samples': metadata(test_paths),
        'trigger_text': trigger, 'trigger_ids': ids,
        'note': 'Replay uses a freshly reset generation RNG, not the unavailable historical post-training RNG state.',
    }


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                    encoding='utf-8')


def seed_all(seed):
    import numpy as np
    import torch
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def release():
    import torch
    gc.collect()
    torch.cuda.empty_cache()


def memory(reset=False):
    import torch
    result = {}
    for device in range(torch.cuda.device_count()):
        torch.cuda.synchronize(device)
        if reset:
            torch.cuda.reset_peak_memory_stats(device)
        result[str(device)] = {
            'allocated_GiB': torch.cuda.memory_allocated(device) / 1024**3,
            'peak_allocated_GiB': torch.cuda.max_memory_allocated(device) / 1024**3,
            'reserved_GiB': torch.cuda.memory_reserved(device) / 1024**3,
        }
    return result


def compare_gradients(a, b, candidates_a, candidates_b):
    import torch
    a, b = a.float(), b.float()
    if a.shape != b.shape or not torch.isfinite(a).all() or not torch.isfinite(b).all():
        raise ValueError('Gradient shape mismatch or non-finite gradient')
    norm_a, norm_b = a.norm().item(), b.norm().item()
    if norm_a == 0 or norm_b == 0:
        raise ValueError('Zero gradient cannot establish checkpoint equivalence')
    return {
        'cosine_similarity': torch.nn.functional.cosine_similarity(
            a.flatten(), b.flatten(), dim=0).item(),
        'max_absolute_difference': (a - b).abs().max().item(),
        'relative_l2_difference': (a - b).norm().item() / norm_a,
        'allclose_rtol_1e-3_atol_1e-6': torch.allclose(a, b, rtol=1e-3, atol=1e-6),
        'top30_candidate_overlap_per_position': [
            len(set(x) & set(y)) / len(x) for x, y in zip(candidates_a, candidates_b)],
    }


def gradients(manifest, output):
    import numpy as np
    import torch
    from Attack import HotFlip
    from diagnose_attack import SelectedSamples
    from util.template import TextTemplate
    samples = SelectedSamples([Path(x['path']) for x in manifest['train_samples']])
    seed_all(1)
    attack = HotFlip(trigger_token_length=12, shadow_model='llama', prefix_length=8,
                     template=TextTemplate(prefix_1='', prefix_2=''), compute_dtype=torch.bfloat16)
    probes = {'initial': attack.trigger_tokens.copy(),
              'learned': np.asarray(manifest['trigger_ids'], dtype=int)}
    reports = {}
    for probe, ids in probes.items():
        observations = []
        for enabled in (False, True):
            if enabled:
                attack.model.gradient_checkpointing_enable()
            else:
                attack.model.gradient_checkpointing_disable()
            attack.model.eval()
            attack.model.zero_grad(set_to_none=True)
            release()
            seed_all(1)
            memory(reset=True)
            loss, gradient = attack.compute_loss(samples, ids, 0, require_grad=True)
            candidates = attack.hotflip_attack(gradient, num_candidates=30).tolist()
            cpu_gradient = gradient.detach().float().cpu()
            label = f'{probe}_checkpoint_{enabled}'
            record = {'loss': loss, 'memory': memory(), 'trigger_ids': ids.tolist()}
            save(output / f'{label}.json', record)
            torch.save(cpu_gradient, output / f'{label}.gradient.pt')
            observations.append((record, cpu_gradient, candidates))
            del gradient
            print(label, json.dumps(record), flush=True)
        a, b = observations
        reports[probe] = {'loss_without_checkpoint': a[0]['loss'],
                          'loss_with_checkpoint': b[0]['loss'],
                          'absolute_loss_difference': abs(a[0]['loss'] - b[0]['loss']),
                          **compare_gradients(a[1], b[1], a[2], b[2])}
        save(output / 'gradient_comparison.json', reports)
        print(probe, json.dumps(reports[probe]), flush=True)
    del attack
    release()


def replay(manifest, output, generation_seed):
    import torch
    from Sampler import Sampler
    from diagnose_attack import SelectedSamples
    from util.template import TextTemplate
    samples = SelectedSamples([Path(x['path']) for x in manifest['test_samples']])
    reports = {}
    # None reproduces the old ModelFactory loading defaults, including bnb FP16.
    for label, dtype in [('legacy_default', None), ('bfloat16', torch.bfloat16)]:
        sampler = Sampler(target_model='llama', template=TextTemplate(prefix_1='', prefix_2=''),
                          compute_dtype=dtype)
        seed_all(generation_seed)
        memory(reset=True)
        results = sampler.sample_sequence(samples, triggers=manifest['trigger_text'],
                                          trigger_token_ids=manifest['trigger_ids'])
        sampler.save_to_csv(str(output / f'replay_{label}.csv'), results, manifest['trigger_text'])
        report = sampler.evaluate_skill_leakage(results)
        report['memory'] = memory()
        report['embedding_dtype'] = str(sampler.model.get_input_embeddings().weight.dtype)
        report['generation_seed'] = generation_seed
        save(output / f'replay_{label}.metrics.json', report)
        reports[label] = {k: v for k, v in report.items() if k != 'samples'}
        save(output / 'replay_comparison.json', reports)
        del sampler
        release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['prepare', 'gradients', 'replay', 'all'], default='prepare')
    parser.add_argument('--generation-seed', type=int, default=1)
    parser.add_argument('--results-dir', type=Path, default=ROOT / 'results')
    args = parser.parse_args()
    if not 0 <= args.generation_seed < 2**32:
        parser.error('generation-seed must be in [0, 2**32)')
    manifest = prepare()
    args.results_dir.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='webtesting_regression_', dir=args.results_dir))
    manifest['generation_seed'] = args.generation_seed
    manifest['versions'] = {}
    for name in ['torch', 'transformers', 'bitsandbytes', 'accelerate', 'tokenizers']:
        try:
            manifest['versions'][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            manifest['versions'][name] = 'not installed'
    save(output / 'manifest.json', manifest)
    print('Results:', output, flush=True)
    print('Historical reference:', manifest['historical_full_reproductions'], '/ 20', flush=True)
    if args.mode == 'prepare':
        return
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('Run GPU probes in the pleak CUDA environment; prepare needs no GPU')
    if args.mode in ('gradients', 'all'):
        gradients(manifest, output)
    if args.mode in ('replay', 'all'):
        replay(manifest, output, args.generation_seed)
    print('Completed:', output, flush=True)


if __name__ == '__main__':
    main()
