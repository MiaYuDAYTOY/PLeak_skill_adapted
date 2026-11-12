"""Read-only loss audit. Run: python3 results/qwen/analysis/soft_recall_followup/loss/analyze_loss.py
Requires numpy, pandas, matplotlib; no model/tokenizer/training/network calls.
"""
from pathlib import Path
import json,re,csv,hashlib,itertools,collections,os
os.environ.setdefault('MPLCONFIGDIR','/tmp/pleak-followup-mpl')
csv.field_size_limit(100000000)
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[5]
OUT=Path(__file__).resolve().parent
METRICS=['body_rougeL_recall','body_rouge2_recall','body_rougeL_precision']
idx=json.loads((ROOT/'results/qwen/analysis/data/all_results.json').read_text())
runs=[r for r in idx['runs'] if r['role']=='primary' and r['status']=='complete' and r['included_in_summary']]
assert len(runs)==81
logs={str(p.relative_to(ROOT)):p.read_text(errors='replace') for p in (ROOT/'results/qwen/logs').glob('*.log')}
segments=[]
for path,text in logs.items():
 starts=list(re.finditer(r'^Selection saved to: (.+)\.samples\.json\s*$',text,re.M))
 for j,m in enumerate(starts):
  end=starts[j+1].start() if j+1<len(starts) else len(text)
  segment=text[m.end():end]
  trigger_save=re.search(r'^Trigger token IDs saved to: (.+)\.trigger_ids\.json\s*$',segment,re.M)
  # Only optimization portion, never generated output or metric JSON.
  opt=segment[:trigger_save.start()] if trigger_save else segment
  currents=list(re.finditer(r'^current loss:([0-9.eE+-]+), triggers:',opt,re.M))
  accepted=list(re.finditer(r'^Loss: ([0-9.eE+-]+), triggers:',opt,re.M))
  segments.append(dict(log=path,selection=m.group(1),start_line=text[:m.start()].count('\n')+1,opt_start_line=text[:m.end()].count('\n')+1,opt=opt,current=currents,accepted=accepted,complete=bool(trigger_save),no_improvement='No improvement, ending iteration' in opt,traceback='Traceback' in opt))
rows=[];trace=[];mapping=[]
for r in runs:
 key=f"t{r['train_num']}_p{r['prefix_length']}_s{r['sample_seed']}_a{r['attack_seed']}"
 stem=Path(r['source_samples']).name.removesuffix('.samples.json')
 matches=[s for s in segments if Path(s['selection']).name==stem and Path(s['selection']).parent.name==r['launch_id']]
 assert len(matches)==1,(key,len(matches))
 s=matches[0];assert s['complete'] and s['no_improvement'] and not s['traceback'],key
 assert s['log'] in r['related_logs']
 vals=np.array([float(m.group(1)) for m in s['current']]); acc=np.array([float(m.group(1)) for m in s['accepted']])
 assert len(vals)==len(acc)+1
 assert np.allclose(vals[1:],acc,rtol=0,atol=1e-10)
 assert np.all(np.diff(vals)<0)
 sam=json.loads((ROOT/r['source_samples']).read_text());train=sam['train_samples']
 train_hash=hashlib.sha256(json.dumps([(p['path'].split('/documents/')[-1],p['content_sha256']) for p in train],sort_keys=True).encode()).hexdigest()
 assert all(sam[k]==r[k] for k in ['train_num','prefix_length','sample_seed','attack_seed'])
 ev=json.loads((ROOT/r['source_evaluation']).read_text())['samples']; assert len(ev)==70
 v=np.array([p['body_rougeL_recall'] for p in ev])
 with (ROOT/r['source_results']).open() as f: csvrows=list(csv.DictReader(f))
 # Logs preserve intermediate text but only final token IDs are explicitly persisted.
 last=s['current'][-1]
 tail=s['opt'][last.end():].split('\nNo improvement, ending iteration')[0].strip()
 log_trigger=' '.join(tail.split()); csv_trigger=' '.join(csvrows[0]['trigger'].split())
 assert log_trigger==csv_trigger,(key,log_trigger,csv_trigger)
 diffs=-np.diff(vals);n=len(diffs);drop=vals[0]-vals[-1]
 row=dict(run_key=key,run_id=r['run_id'],train_num=r['train_num'],prefix_length=r['prefix_length'],sample_seed=r['sample_seed'],attack_seed=r['attack_seed'],train_subset_hash=train_hash,train_skills='|'.join(p['path'].split('/documents/')[-1].removesuffix('/SKILL.md') for p in train),log_path=s['log'],log_selection_line=s['start_line'],initial_loss=vals[0],final_loss=vals[-1],minimum_loss=vals.min(),loss_drop=drop,relative_loss_drop=drop/vals[0],accepted_updates=n,gradient_rounds=len(vals),candidate_upper_bound=12*30*len(vals),early_drop_5=vals[0]-vals[min(5,n)],early_drop_fraction=(vals[0]-vals[min(5,n)])/drop,early_drop_per_update=(vals[0]-vals[min(5,n)])/min(5,n),max_single_drop=diffs.max(),small_update_fraction=float(np.mean(diffs<0.01)),last5_drop=vals[max(0,n-5)]-vals[-1],drop_std=diffs.std(),monotonic=True,normal_no_improvement_stop=True,log_final_trigger_matches_csv_whitespace_normalized=True,skill_recall_sd=v.std(ddof=1),skill_recall_q10=np.quantile(v,.1),skill_recall_q90=np.quantile(v,.9),low_lt01=np.mean(v<.1),low_lt02=np.mean(v<.2),low_lt03=np.mean(v<.3))
 for metric in METRICS:
  row[metric]=np.mean([p[metric] for p in ev]);assert abs(row[metric]-r['metrics']['mean_'+metric])<1e-12
 for step,(m,loss) in enumerate(zip(s['current'],vals)):
  trace.append(dict(run_key=key,run_id=r['run_id'],accepted_update_index=step,current_loss=loss,log_path=s['log'],log_line=s['opt_start_line']+s['opt'][:m.start()].count('\n')))
 rows.append(row)
 mapping.append(dict(run_key=key,run_id=r['run_id'],log_path=s['log'],log_selection_line=s['start_line'],source_samples=r['source_samples'],source_evaluation=r['source_evaluation'],source_trigger_ids=r['source_trigger_ids'],train_subset_hash=train_hash))
df=pd.DataFrame(rows).sort_values(['train_num','prefix_length','sample_seed','attack_seed']);tdf=pd.DataFrame(trace)
assert df.groupby(['train_num','sample_seed']).train_subset_hash.nunique().eq(1).all()
assert df.groupby(['train_num','prefix_length','sample_seed']).size().eq(3).all()
df.to_csv(OUT/'run_loss_summary.csv',index=False);tdf.to_csv(OUT/'loss_trajectories.csv',index=False);pd.DataFrame(mapping).to_csv(OUT/'run_log_mapping.csv',index=False)
features=['initial_loss','final_loss','loss_drop','relative_loss_drop','accepted_updates','early_drop_5','early_drop_fraction','early_drop_per_update','max_single_drop','small_update_fraction','last5_drop','drop_std']
# Report fixed-prefix and within exact t/p/s comparisons. No pooled cross-prefix loss ranks.
corr=[]
def sp(x,y): return pd.Series(x).rank().corr(pd.Series(y).rank())
for prefix,g in df.groupby('prefix_length'):
 for feature in features:
  for metric in METRICS+['low_lt02','skill_recall_sd']:
   corr.append(dict(scope='same_prefix',prefix_length=prefix,n_runs=len(g),feature=feature,metric=metric,spearman=sp(g[feature].to_numpy(),g[metric].to_numpy()),pearson=g[feature].corr(g[metric])))
groups=['train_num','prefix_length','sample_seed']
resid=df[features+METRICS+['low_lt02','skill_recall_sd']]-df.groupby(groups)[features+METRICS+['low_lt02','skill_recall_sd']].transform('mean')
for feature in features:
 for metric in METRICS+['low_lt02','skill_recall_sd']:
  corr.append(dict(scope='centered_within_t_p_s',prefix_length='all_centered_no_loss_ranking',n_runs=81,feature=feature,metric=metric,spearman=sp(resid[feature].to_numpy(),resid[metric].to_numpy()),pearson=resid[feature].corr(resid[metric])))
pd.DataFrame(corr).to_csv(OUT/'loss_correlations.csv',index=False)
pairs=[]
for cond,g in df.groupby(groups):
 for (_,a),(_,b) in itertools.combinations(g.iterrows(),2):
  if a.body_rougeL_recall>b.body_rougeL_recall:a,b=b,a
  p=dict(train_num=cond[0],prefix_length=cond[1],sample_seed=cond[2],lower_recall_run=a.run_key,higher_recall_run=b.run_key,recall_gap=b.body_rougeL_recall-a.body_rougeL_recall,lower_recall_final_loss=a.final_loss,higher_recall_final_loss=b.final_loss,absolute_final_loss_gap=abs(b.final_loss-a.final_loss),better_recall_has_lower_loss=b.final_loss<a.final_loss)
  for metric in METRICS[1:]:p[metric+'_gap']=b[metric]-a[metric]
  pairs.append(p)
pairs=pd.DataFrame(pairs).sort_values('recall_gap',ascending=False);pairs.to_csv(OUT/'matched_attack_seed_pairs.csv',index=False)
# Nine training-subset clusters, preserving all prefix/attack cells. Exploratory intervals.
rng=np.random.default_rng(20261105);clusters=list(df.groupby(['train_num','sample_seed']).groups.values());ci=[]
for feature in ['final_loss','relative_loss_drop','accepted_updates','early_drop_fraction']:
 for metric in METRICS+['low_lt02']:
  vals=[]
  for _ in range(3000):
   ids=np.concatenate([np.array(clusters[i]) for i in rng.integers(0,len(clusters),len(clusters))]);x=resid.loc[ids,feature].to_numpy();y=resid.loc[ids,metric].to_numpy();vals.append(np.corrcoef(x,y)[0,1])
  ci.append(dict(feature=feature,metric=metric,centered_pearson=resid[feature].corr(resid[metric]),bootstrap_lower=np.quantile(vals,.025),bootstrap_upper=np.quantile(vals,.975),clusters=9,replicates=3000))
pd.DataFrame(ci).to_csv(OUT/'within_condition_cluster_bootstrap.csv',index=False)
# Each pairwise direction is descriptive; 81 pairs share 81 runs, not independent experiments.
selected=[pairs.iloc[0],pairs[pairs.absolute_final_loss_gap<.01].iloc[0]]
worst=df[(df.relative_loss_drop>.6)&(df.body_rougeL_recall<.1)&(df.prefix_length==8)].sort_values('body_rougeL_recall').iloc[0]
wg=df[(df.train_num==worst.train_num)&(df.prefix_length==worst.prefix_length)&(df.sample_seed==worst.sample_seed)].sort_values('body_rougeL_recall')
third=pairs[(pairs.lower_recall_run==wg.iloc[0].run_key)&(pairs.higher_recall_run==wg.iloc[-1].run_key)].iloc[0]
selected.append(third)
pd.DataFrame(selected).to_csv(OUT/'selected_pairs.csv',index=False)
fig,axes=plt.subplots(1,3,figsize=(16,4.7))
for ax,p,title in zip(axes,selected,['Largest matched recall gap','Similar final loss (<0.01)','Large loss decrease, weak recall']):
 for key in [p.lower_recall_run,p.higher_recall_run]:
  d=df[df.run_key==key].iloc[0];tr=tdf[tdf.run_key==key]
  ax.plot(tr.accepted_update_index,tr.current_loss,marker='.',label=f'{key}: R={d.body_rougeL_recall:.3f}, R2={d.body_rouge2_recall:.3f}, P={d.body_rougeL_precision:.3f}')
 ax.set_title(title);ax.set_xlabel('Accepted trigger updates (initial = 0)');ax.set_ylabel('Training prefix cross-entropy');ax.grid(alpha=.2);ax.legend(fontsize=7)
fig.suptitle('Same train_num / prefix_length / sample_seed per panel; each final metric is mean of 70 fixed test Skills',fontsize=10)
fig.tight_layout();fig.savefig(OUT/'matched_loss_curves.png',dpi=180);plt.close(fig)
fig,axes=plt.subplots(1,3,figsize=(13,4.5),sharey=True)
for ax,(prefix,g) in zip(axes,df.groupby('prefix_length')):
 for t,h in g.groupby('train_num'):ax.scatter(h.final_loss,h.body_rougeL_recall,label=f'train_num={t}',s=35)
 ax.set_title(f'prefix_length={prefix}; n=27 runs');ax.set_xlabel('Final prefix cross-entropy');ax.grid(alpha=.2);ax.legend(fontsize=8)
axes[0].set_ylabel('Mean body ROUGE-L Recall (70 Skills/run)');fig.suptitle('Final loss vs final test recall; points are runs; no error bars or causal fit',fontsize=10);fig.tight_layout();fig.savefig(OUT/'final_loss_recall.png',dpi=180);plt.close(fig)
audit=dict(primary_runs=len(df),loss_trace_records=len(tdf),all_runs_mapped_uniquely=True,all_accepted_loss_equals_next_current=True,all_monotonic=True,all_final_equals_min=True,all_normal_no_improvement_stop=True,all_final_trigger_text_matches_csv_after_whitespace_normalization=True,all_train_subsets_constant_within_train_num_sample_seed=True,all_eval_metric_means_match_index=True,formal_logs=sorted(df.log_path.unique()),all_log_attempts=[{k:v for k,v in s.items() if k not in ['opt','current','accepted']}|dict(current_count=len(s['current']),accepted_count=len(s['accepted'])) for s in segments],source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'Attack.py',ROOT/'main.py',ROOT/'results/qwen/analysis/data/all_results.json']+[ROOT/x for x in sorted(df.log_path.unique())]},intermediate_trigger_text_available=True,intermediate_explicit_token_id_checkpoints_found=[],intermediate_test_evaluations_found=[],checkpoint_name_scan=[str(p.relative_to(ROOT)) for p in (ROOT/'results/qwen').rglob('*') if re.search(r'checkpoint|intermediate|step_\d',p.name,re.I)])
(OUT/'loss_validation.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
print(df[['initial_loss','final_loss','relative_loss_drop','accepted_updates','body_rougeL_recall','low_lt02']].describe().to_string())
print('\nSELECTED\n',pd.DataFrame(selected).to_string(index=False))
print('\nWITHIN CONDITION CORRELATIONS\n',pd.DataFrame(ci).to_string(index=False))
print('\nDIRECTION',pairs.better_recall_has_lower_loss.sum(),len(pairs),'large gap',pairs[pairs.recall_gap>.1].better_recall_has_lower_loss.sum(),len(pairs[pairs.recall_gap>.1]))
