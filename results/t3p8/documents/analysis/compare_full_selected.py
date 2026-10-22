"""Compare archived t3p8 results, including the same held-out documents.

Only reads saved generations/evaluations; does not execute a model or re-score text.
Run from any directory with Python 3 (standard library only).
"""

import csv
import hashlib
import io
import json
import re
import statistics as stats
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
INPUTS = {}


def read_bytes(path):
    raw = path.read_bytes()
    INPUTS[str(path.relative_to(ROOT))] = hashlib.sha256(raw).hexdigest()
    return raw


def read_json(path):
    return json.loads(read_bytes(path))


def doc(path):
    return Path(path).parent.name


def summarize(samples):
    n = len(samples)
    result = {k: stats.mean(x[k] for x in samples) for k in (
        'rougeL_recall', 'rougeL_precision', 'rouge2_recall',
        'body_rougeL_recall', 'body_rougeL_precision', 'body_rouge2_recall',
        'token_recall', 'token_precision', 'full_skill_prefix', 'ended_with_eos')}
    result.update(
        observations=n,
        full_leak_count=sum(x['full_skill_prefix'] for x in samples),
        empty_count=sum(x['prediction_token_count'] == 0 for x in samples),
        empty_rate=stats.mean(x['prediction_token_count'] == 0 for x in samples),
        high_overlap_count=sum(x['body_rougeL_recall'] >= 0.9 for x in samples),
    )
    nonempty = [x for x in samples if x['prediction_token_count'] > 0]
    result['nonempty_body_rougeL_recall'] = stats.mean(x['body_rougeL_recall'] for x in nonempty)
    return result


def pct(x):
    return f'{100*x:.2f}%'


def pp(x):
    return f'{100*x:+.2f}'


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join('---' for _ in headers) + ' |'] +
                     ['| ' + ' | '.join(map(str, row)) + ' |' for row in rows])


def main():
    full = read_json(ROOT / 'full data/analysis/rouge_reevaluation/all_nine_summary.json')['runs']
    ids = sorted(full)
    selected = {r: read_json(ROOT / 'selecteddata/runs' / r / 'evaluation.json') for r in ids}
    assert len(ids) == 9
    groups = {'fulldata': full, 'selecteddata': selected}
    folders = {'fulldata': 'full data', 'selecteddata': 'selecteddata'}
    metadata, sample_maps, test_maps, errors = {}, {}, {}, {}
    for group, runs in groups.items():
        metadata[group], sample_maps[group], test_maps[group], errors[group] = {}, {}, {}, {}
        for r, run in runs.items():
            base = ROOT / folders[group] / 'runs' / r
            meta = read_json(base / 'samples.json')
            metadata[group][r] = meta
            test = {doc(x['path']): x['content_sha256'] for x in meta['test_samples']}
            train_hashes = {x['content_sha256'] for x in meta['train_samples']}
            assert train_hashes.isdisjoint(test.values()), (group, r, 'train/test overlap')
            assert len(test) == len(meta['test_samples'])
            test_maps[group][r] = test
            samples = [x for x in run['samples'] if 'body_rougeL_recall' in x]
            smap = {doc(x['sample_path']): x for x in samples}
            assert len(smap) == len(samples) == run['metrics']['evaluated_samples']
            assert set(smap) <= set(test)
            sample_maps[group][r] = smap
            for k in ('rougeL_recall', 'rougeL_precision', 'rouge2_recall',
                      'body_rougeL_recall', 'body_rougeL_precision', 'body_rouge2_recall'):
                assert abs(stats.mean(x[k] for x in samples) - run['metrics']['mean_' + k]) < 1e-12
            raw = read_bytes(base / 'results.csv').decode('utf-8-sig')
            rows = list(csv.DictReader(io.StringIO(raw, newline='')))
            errs = [x['error'] for x in rows if x.get('error')]
            assert len(rows) == run['metrics']['total_samples']
            assert len(errs) == run['metrics']['failed_samples']
            errors[group][r] = {
                'count': len(errs),
                'types': dict(Counter(x.split('(')[0] for x in errs)),
                'gpu_capacity_in_error_messages': dict(Counter(
                    re.findall(r'total capacity of ([0-9.]+ GiB)', x)[0]
                    if re.findall(r'total capacity of ([0-9.]+ GiB)', x) else 'unknown'
                    for x in errs)),
            }

    common = set.intersection(*(set(m) for gm in test_maps.values() for m in gm.values()))
    assert len(common) == 21
    for d in common:
        assert len({gm[r][d] for gm in test_maps.values() for r in ids}) == 1
        assert all(d in gm[r] for gm in sample_maps.values() for r in ids)
        assert len({gm[r][d]['target_token_count'] for gm in sample_maps.values() for r in ids}) == 1
        assert len({gm[r][d]['body_target_token_count'] for gm in sample_maps.values() for r in ids}) == 1

    result = {'created': '2026-10-08', 'difference_direction': 'selecteddata minus fulldata',
              'aggregation': 'Equal run weight; empty outputs retained as zero. Generation errors excluded from conditional quality; also reported separately.',
              'common_test_documents': sorted(common), 'groups': {}, 'run_comparison': [],
              'seed_group_comparison': [], 'training_documents': {}, 'errors': errors}
    scores = {}
    for group, runs in groups.items():
        scores[group] = {'original': {}, 'common': {}}
        result['training_documents'][group] = {}
        for r in ids:
            scores[group]['original'][r] = summarize(list(sample_maps[group][r].values()))
            scores[group]['common'][r] = summarize([sample_maps[group][r][d] for d in sorted(common)])
            result['training_documents'][group][r] = [doc(x['path']) for x in metadata[group][r]['train_samples']]
        total = sum(r['metrics']['total_samples'] for r in runs.values())
        failed = sum(r['metrics']['failed_samples'] for r in runs.values())
        gd = {'total_attempts': total, 'failures': failed, 'failure_rate': failed/total,
              'training_pool_sizes': sorted({metadata[group][r]['train_pool_size'] for r in ids})}
        for scope in ['original', 'common']:
            per_run = scores[group][scope]
            flat = [x for r in ids for d, x in sample_maps[group][r].items()
                    if scope == 'original' or d in common]
            vals = [x['body_rougeL_recall'] for x in per_run.values()]
            gd[scope] = {
                'macro': {k: stats.mean(x[k] for x in per_run.values())
                          for k in per_run[ids[0]] if k not in ('observations', 'full_leak_count', 'empty_count', 'high_overlap_count')},
                'pooled': summarize(flat),
                'run_body_rougeL_recall_dispersion': {'sd': stats.stdev(vals), 'median': stats.median(vals), 'min': min(vals), 'max': max(vals)},
                'run_scores': per_run,
            }
        result['groups'][group] = gd

    for r in ids:
        result['run_comparison'].append({'run': r, **{
            scope: {'full': scores['fulldata'][scope][r]['body_rougeL_recall'],
                    'selected': scores['selecteddata'][scope][r]['body_rougeL_recall'],
                    'delta': scores['selecteddata'][scope][r]['body_rougeL_recall'] - scores['fulldata'][scope][r]['body_rougeL_recall']}
            for scope in ['original', 'common']}})
    for dimension, values in [('sample_seed', [0, 1, 2]), ('attack_seed', [1, 2, 3])]:
        for seed in values:
            selected_ids = [r for r in ids if full[r][dimension] == seed]
            result['seed_group_comparison'].append({'dimension': dimension, 'seed': seed, **{
                scope: {g: stats.mean(scores[g][scope][r]['body_rougeL_recall'] for r in selected_ids)
                        for g in groups} for scope in ['original', 'common']}})
    result['common_document_details'] = [{
        'document': d, 'content_sha256': test_maps['fulldata'][ids[0]][d],
        **{g: summarize([sample_maps[g][r][d] for r in ids]) for g in groups},
    } for d in sorted(common)]
    result['input_sha256'] = INPUTS
    for path, expected in INPUTS.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    result['verification'] = {'source_hashes_unchanged': True, 'saved_means_reproduced': True,
                              'common_content_hashes_and_token_counts_identical': True,
                              'common_documents_successful_in_all_18_runs': True,
                              'train_test_content_disjoint_in_each_run': True}
    (OUT / 'fulldata_vs_selecteddata_comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')

    f, s = (result['groups'][g] for g in groups)
    of, os = f['original'], s['original']
    cf, cs = f['common'], s['common']
    metrics = [('正文 ROUGE-L recall', 'body_rougeL_recall'), ('正文 ROUGE-L precision', 'body_rougeL_precision'),
               ('正文 ROUGE-2 recall', 'body_rouge2_recall'), ('全文 ROUGE-L recall', 'rougeL_recall'),
               ('全文 ROUGE-2 recall', 'rouge2_recall'), ('完整原文前缀泄漏率', 'full_skill_prefix'),
               ('空内容输出率', 'empty_rate')]
    global_rows = [[label, pct(of['macro'][k]), pct(os['macro'][k]), pp(os['macro'][k]-of['macro'][k])] for label, k in metrics]
    common_rows = [[label, pct(cf['macro'][k]), pct(cs['macro'][k]), pp(cs['macro'][k]-cf['macro'][k])] for label, k in metrics[:3]]
    for label, count, rate in [('完整原文前缀泄漏', 'full_leak_count', 'full_skill_prefix'), ('空内容输出', 'empty_count', 'empty_rate')]:
        common_rows.append([label, f"{cf['pooled'][count]}/189（{pct(cf['pooled'][rate])}）", f"{cs['pooled'][count]}/189（{pct(cs['pooled'][rate])}）", pp(cs['pooled'][rate]-cf['pooled'][rate])])
    run_rows = [[x['run'], pct(x['original']['full']), pct(x['original']['selected']), pp(x['original']['delta']),
                 pct(x['common']['full']), pct(x['common']['selected']), pp(x['common']['delta'])] for x in result['run_comparison']]
    group_rows = [[x['dimension'], x['seed'], pct(x['original']['fulldata']), pct(x['original']['selecteddata']),
                   pct(x['common']['fulldata']), pct(x['common']['selecteddata'])] for x in result['seed_group_comparison']]
    train_rows = [[seed, '、'.join(result['training_documents']['fulldata'][f's{seed}a1']),
                   '、'.join(result['training_documents']['selecteddata'][f's{seed}a1'])] for seed in [0, 1, 2]]
    common_delta = cs['macro']['body_rougeL_recall'] - cf['macro']['body_rougeL_recall']
    wins = sum(x['common']['delta'] > 0 for x in result['run_comparison'])
    report = f'''# fulldata 与 selecteddata 对照分析：documents / train3 / prefix8

更新：2026-10-08。使用 fulldata 补评后的九组，以及 selecteddata 九组原始逐样本指标；本次未运行模型。

## 结论

**当前记录不支持“筛选提升了平均泄漏效果”。各自测试集上基本持平；在完全相同的 21 篇测试文档上，fulldata 的正文重合更高。selecteddata 的观察到的优势是生成无报错，但 seed 波动更大。**

共同测试集上，正文 ROUGE-L recall 从 {pct(cf['macro']['body_rougeL_recall'])} 降到 {pct(cs['macro']['body_rougeL_recall'])}，差 {pp(common_delta)} 个百分点，相对下降 {pct(-common_delta/cf['macro']['body_rougeL_recall'])}；正文 ROUGE-2 recall 同样下降。两组完整泄漏均为 3/189。这个结果是当前两套实验流程的描述性比较，不是长度筛选的独立因果效应。

## 1. 原始测试范围的总体对照

除特别注明外，比例先在每次成功评估样本中求平均，再将九次实验等权平均；“差”均为 selecteddata 减 fulldata，单位为百分点。生成成功包含空输出，不等于攻击成功。

{table(['指标', 'fulldata', 'selecteddata', '差（百分点）'], global_rows)}

- 生成尝试：fulldata 606 次，成功评估 521 次、失败 85 次（{pct(f['failure_rate'])}）；selecteddata 234 次，234 次均完成。
- 原始完整泄漏观测数：3/521 与 4/234；fulldata 按观测加权为 {pct(of['pooled']['full_skill_prefix'])}，与表中实验等权的 {pct(of['macro']['full_skill_prefix'])} 有区别。
- 原始空内容观测数：129/521 与 69/234；fulldata 按观测加权为空 {pct(of['pooled']['empty_rate'])}，与表中 {pct(of['macro']['empty_rate'])} 的实验等权分母不同。
- 两组 exact Markdown / token match 均为 0。完整泄漏定义是“输出以整个规范化原文开头”，允许额外尾部，不能与严格完全相等混用。

直接总平均只显示总体接近：正文 RL recall 相差 {pp(os['macro']['body_rougeL_recall']-of['macro']['body_rougeL_recall'])} 个百分点。原始泄漏率优势并不能直接说明筛选更好，因为 selecteddata 测试集更小，且重新划分了文档。

## 2. 同一批测试文档的对照

按 `samples.json` 的内容 SHA-256 核对，两个测试集交集为 **21 篇**。这些文档在全部 18 次实验都成功评估，内容哈希、全文及正文 token 数一致，且不属于任一对应运行的训练样本。每个方案 21×9=189 次观测；无需丢弃其中任何失败行，因为此交集上没有失败。

{table(['指标', 'fulldata', 'selecteddata', '差（百分点）'], common_rows)}

因此，不能用 fulldata 更多 OOM 或不同测试长度来解释这张表的差异：这两个分母问题已在共同子集中消除。但这 21 篇属于双方均可运行的短文档，不能外推到全部 100 篇。

selecteddata 在同名 seed 的九组中有 {wins} 组正文 RL recall 较高、{9-wins} 组较低，改善不稳定。共同集上完整泄漏率相同，说明原始 1.71% 对约 0.57% 的差距不构成稳定优势证据。

作为空输出诊断，仅保留非空输出时，共同集正文 RL recall 为 fulldata {pct(cf['pooled']['nonempty_body_rougeL_recall'])}、selecteddata {pct(cs['pooled']['nonempty_body_rougeL_recall'])}。这两个分母分别为 134、126，已不是逐文档配对，仅用于说明空输出并非全部原因；不能替代上表主结果。

## 3. 九组差异与 seed 波动

{table(['组合', '原范围 full', '原范围 selected', '原范围差', '共同集 full', '共同集 selected', '共同集差'], run_rows)}

以上均为正文 ROUGE-L recall；差的单位是百分点。“同名 seed”只用于索引，两个方案所选训练文档、测试顺序和随机数消耗不相同，不等于相同随机条件的严格配对试验。

原范围九次均值的标准差：fulldata {100*of['run_body_rougeL_recall_dispersion']['sd']:.2f} 个百分点，selecteddata {100*os['run_body_rougeL_recall_dispersion']['sd']:.2f} 个百分点。中位数分别为 {pct(of['run_body_rougeL_recall_dispersion']['median'])} 和 {pct(os['run_body_rougeL_recall_dispersion']['median'])}。

selecteddata 的 s1a2 和 s2a3 是两个高分组合，合计约占九组正文 RL recall 分数总和的 50.6%；低分组合尤其是 s2a1、s2a2 抵消了它们。不能只挑这两组代表筛选方案。

{table(['分组', 'seed', '原范围 full', '原范围 selected', '共同集 full', '共同集 selected'], group_rows)}

attack_seed=2 在 fulldata 中较好，attack_seed=3 在 selecteddata 中较好，排序反转。优先解决不同训练集合下的稳定性，不应把某个整数 seed 视为普遍有效的配置。每个 sample_seed 只有 3 个 attack_seed，三组训练集合也不是足够多的独立重复；本报告不把 189 条观测当成 189 篇独立文档，不作显著性或因果结论。

## 4. 哪些变化混在一起

1. **长度筛选后重新划分数据。**100 篇先保留 36 篇，然后分成 10 篇训练池、26 篇测试；fulldata 的训练池为 30 篇（sample_seed=2 为排除一篇 OOM 文档后的 29 篇），原测试池为 70 篇。相同 split_seed 不保证相同 train/test 成员。
2. **实际训练三篇完全不同。**两个方案同名 sample_seed 的训练集合没有交集，比较同时包含长度限制、训练内容和训练池规模的变化。
3. **运行环境与失败分母不同。**fulldata 的 85 次失败全部为 CUDA OOM。错误记录显示旧五组 GPU 容量 79.25 GiB，新四组 23.52 GiB；新四组还预排除了 6 篇已知 OOM 文档。不能把原始 14.03% 对 0 的差距全部归因于筛选，也不能据此比较运行速度或成本。
4. **随机性未完全分离。**当前生成代码对 llama 使用随机采样；固定 attack_seed 不保证训练、生成和测试顺序的随机影响完全一致。需要把它们分别记录和控制。

{table(['sample_seed', 'fulldata 实际训练文档', 'selecteddata 实际训练文档'], train_rows)}

## 5. 建议及优先顺序

**第一优先：固定评估口径，保留双方基线。**将本报告的 21 篇共同集作为当前历史对照的主表，原测试范围作为覆盖面和运行可行性的附表。主指标采用正文 RL recall，辅以正文 R2 recall、完整原文前缀泄漏、空输出率、失败率；空输出计零，OOM 单独报告。后续如调整训练或筛选规则，这 21 篇会成为开发集，最终结论还需要未参与调参的留出测试集。

**第二优先：做受控的训练数据筛选对照。**先冻结测试集及训练候选池，筛选仅施加于训练候选池，避免筛选后重新切分。保持 train3、prefix8、trigger12、模型版本、优化预算、GPU/精度、生成预算与解码设置一致；比较“从原训练候选池抽取”与“从满足长度规则的候选池抽取”。每个方案事先生成多个训练三元组清单，以实际路径和哈希复现，保持 seed 列表和重复次数一致，并分开记录训练采样、攻击优化、推理生成的随机种子。

这项实验估计“训练筛选策略”的整体效果。由于筛选必然改变训练成员，不能声称只改变了长度；若还要排除训练池规模影响，可增加“与筛选池等量的随机子池”对照。补充相同测试文档、相同生成预算的无优化触发器基线，区分低水平文本重合与优化带来的增益。

**第三优先：先复查输出失败模式，再追加大量 seed。**对 selecteddata 低分组合 s2a1/s2a2 的空输出，与高分组合 s1a2/s2a3 对照，检查保存的输出长度、结束 token、优化损失与触发器；不要先改阈值追求测试分数。可先复用现有触发器，在共同测试集用明确记录的生成 seed 重复推理，以较低代价判断高低分是否受解码随机性影响；再决定是否增加训练三元组和优化重复。

**数据策略建议：暂不把 selecteddata 替代 fulldata。**当前长度筛选可保留为满足资源与上下文预算的可运行子集，但尚无平均效果提升证据。研究代表性时保留 full 母集，按预先规定的长度区间分层记录覆盖率及可运行性；长文档若采用截断或分块，单列为新实验条件，不能与整篇原文指标混合。筛选规则应围绕预算和覆盖面制定，而非依据测试分数事后挑样本。

## 6. 可追溯文件

- [逐实验、分组及 21 篇文档对照 JSON](fulldata_vs_selecteddata_comparison.json)
- [复算脚本](compare_full_selected.py)：仅使用 Python 标准库，运行后生成本报告和 JSON。
- [fulldata 统一补评结果](../full%20data/analysis/rouge_reevaluation/all_nine_summary.json)
- [selecteddata 原始评估目录](../selecteddata/runs/)

校验包括：18 组逐条均值复现、测试文档内容哈希与 token 数一致、共同文档在全部运行均有评分、各运行训练/测试内容哈希无交集、输入文件 SHA-256 未变化。JSON 保存输入哈希与全部共同文档名单。原始生成、原始指标和现有 Excel 未修改。
'''
    (OUT / 'fulldata_vs_selecteddata_对照分析.md').write_text(report)
    print(json.dumps({'common_documents': len(common), 'common_full_body_RL': cf['macro']['body_rougeL_recall'],
                      'common_selected_body_RL': cs['macro']['body_rougeL_recall'],
                      'common_delta': common_delta, 'checks': result['verification'],
                      'report': str(OUT / 'fulldata_vs_selecteddata_对照分析.md')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
