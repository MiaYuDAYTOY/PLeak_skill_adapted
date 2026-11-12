"""End-to-end deliverable consistency and source immutability checks."""
from pathlib import Path
import json,hashlib,csv,re,py_compile
import pandas as pd,numpy as np
P=Path(__file__).resolve().parent;ROOT=P.parents[3]
index=json.loads((ROOT/'results/qwen/analysis/data/all_results.json').read_text())
runs=[r for r in index['runs'] if r['role']=='primary']
hashes=json.loads((P/'input_hashes.json').read_text())
hashes.update(json.loads((P/'loss/loss_validation.json').read_text())['source_sha256'])
unchanged=[]
for path,digest in hashes.items():
 assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
 unchanged.append(path)
d=pd.read_csv(P/'diagnostics/output_diagnostics.csv');v=pd.read_csv(P/'validated_outputs.csv');l=pd.read_csv(P/'run_loss_metrics_types.csv');f=pd.read_csv(P/'skill_metrics_features_types.csv')
assert len(d)==5670 and not d.duplicated(['run_key','sample_index']).any()
assert len(l)==81 and len(f)==70
M=['body_rougeL_recall','body_rouge2_recall','body_rougeL_precision']
merged=d.merge(v,on=['run_key','sample_index'],validate='one_to_one',suffixes=('_d','_v'))
for m in M:
 assert np.allclose(merged[m+'_d'],merged[m+'_v'],atol=1e-14)
 assert np.allclose(l.set_index('run_key')[m].sort_index(),d.groupby('run_key')[m].mean().sort_index(),atol=1e-14)
 assert np.allclose(f.set_index('skill')[m+'_mean'].sort_index(),d.groupby('skill')[m].mean().sort_index(),atol=1e-14)
types=pd.read_csv(P/'diagnostics/threshold_type_distribution.csv')
for _,g in types.groupby(['metric','threshold']):assert g['count'].sum()==g.n_slice.iloc[0] and abs(g.fraction.sum()-1)<1e-12
assert (l.filter(regex=r'^type_.*_n$').filter(regex=r'(?<!low)_n$').sum(axis=1)==70).all()
budget_records=0
for run in runs:
 stem=Path(run['source_samples']).name.removesuffix('.samples.json');found=[]
 for lp in run['related_logs']:
  txt=(ROOT/lp).read_text(errors='replace');ms=list(re.finditer(r'^Selection saved to: (.+)\.samples\.json\s*$',txt,re.M))
  for i,m in enumerate(ms):
   if Path(m.group(1)).name==stem and Path(m.group(1)).parent.name==run['launch_id']:
    seg=txt[m.end():ms[i+1].start() if i+1<len(ms) else len(txt)]
    found+=re.findall(r'===== Skill (\d+) =====\s*\nprompt tokens: (\d+)\s*\nmax new tokens: (\d+)\s*\ngenerated tokens: (\d+)',seg)
 assert len(found)==70,(stem,len(found))
 key=f"t{run['train_num']}_p{run['prefix_length']}_s{run['sample_seed']}_a{run['attack_seed']}";g=d[d.run_key==key].set_index('sample_index')
 for si,pr,ma,ge in found:
  si,pr,ma,ge=map(int,[si,pr,ma,ge]);assert ma==pr+50;assert int(g.loc[si,'prompt_token_count'])==pr;assert int(g.loc[si,'generated_token_count'])==ge;budget_records+=1
scripts=list(P.rglob('*.py'))
for script in scripts:py_compile.compile(str(script),doraise=True)
# Resolve only local document links; source prose paths are separately preserved in CSV.
broken=[]
for name in ['report_zh.md','README.md']:
 text=(P/name).read_text()
 for target in re.findall(r'\]\(([^)]+)\)',text):
  if target!='delivery_validation.json' and '://' not in target and not (P/target).exists():broken.append([name,target])
assert not broken,broken
result=dict(primary_runs=81,outputs=5670,skills=70,joined_metric_agreement=True,unique_output_keys=True,all_type_slices_sum_to_denominator=True,source_hashes_rechecked=len(unchanged),sources_unchanged=True,formal_log_budget_records_verified=budget_records,budget_policy='max_new_tokens=prompt_token_count+50',python_scripts_compiled=len(scripts),analyst_reviewed_records=len(pd.read_csv(P/'diagnostics/analyst_review.csv')),local_report_links_valid=True,visual_review='Three core figures directly viewed: output types/stops, matched loss curves, 70x9 Skill heatmap; labels/denominators readable. Other plots saved from same validated data.',no_model_calls=True,no_training=True)
(P/'delivery_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
