#!/usr/bin/env python3
"""Offline reproduction. python3 analyze_skills.py; pandas/numpy/matplotlib only.
Outcome metrics are imported unchanged from calibrated evaluation; feature token counts
are calibrated body_target_token_count, NOT word counts. Auxiliary lexical Jaccard is
explicitly a feature only. No model calls, network, training, or input mutation.
"""
import os,sys,re,json,csv,hashlib,itertools
from pathlib import Path
from collections import Counter
import numpy as np,pandas as pd
csv.field_size_limit(100000000)
ROOT=Path(__file__).resolve().parents[5]; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from util.overlap_metrics import strip_yaml_front_matter
os.environ['MPLCONFIGDIR']=str(OUT/'mplcache')
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
M=['body_rougeL_recall','body_rouge2_recall','body_rougeL_precision'];R=M[0]
norm=lambda x:x.replace('\r\n','\n').replace('\r','\n').strip()
runs=[r for r in json.load(open(ROOT/'results/qwen/analysis/data/all_results.json'))['runs'] if r['role']=='primary']
df=pd.read_csv(ROOT/'results/qwen/analysis/data/per_skill/skill_run_details.csv')
df=df[df.run_id.isin([r['run_id'] for r in runs])].copy();df['config']='t'+df.train_num.astype(str)+'_p'+df.prefix_length.astype(str)
df['run_key']=df['config']+'_s'+df.sample_seed.astype(str)+'_a'+df.attack_seed.astype(str)
assert len(df)==5670 and df.skill.nunique()==70 and len(runs)==81
sources=dict(re.findall(r'\[SKILL\.md\]\(([^/]+)/SKILL\.md\) \| ([^|]+) \|',(ROOT/'data/skill_expansion_20260922/samples/documents/README.md').read_text()))
contexts={};ver=[];trainsets={};traintexts={};trainver=[]
for run in runs:
 key=f"t{run['train_num']}_p{run['prefix_length']}_s{run['sample_seed']}_a{run['attack_seed']}"
 manifest=json.load(open(ROOT/run['source_samples'])); mh={Path(s['path']).parent.name:s['content_sha256'] for s in manifest['test_samples']}
 with open(ROOT/run['source_results']) as f: records=list(csv.DictReader(f))
 for row in records:
  skill=Path(row['sample_path']).parent.name;t=row['context']; local=(ROOT/'data/skill_expansion_20260922/samples/documents'/skill/'SKILL.md').read_text()
  sha=hashlib.sha256(t.encode()).hexdigest();ok=t==local and sha==mh[skill] and (skill not in contexts or contexts[skill]==t)
  assert ok,(key,skill);contexts[skill]=t;ver.append(dict(run_key=key,skill=skill,context_equals_local=True,sha256_matches_manifest=True,sha256=sha))
 trainsets[key]=[]
 for s in manifest['train_samples']:
  skill=Path(s['path']).parent.name;t=(ROOT/'data/skill_expansion_20260922/samples/documents'/skill/'SKILL.md').read_text();ok=hashlib.sha256(t.encode()).hexdigest()==s['content_sha256']
  trainver.append(dict(run_key=key,skill=skill,hash_match=ok,expected_sha256=s['content_sha256'],local_sha256=hashlib.sha256(t.encode()).hexdigest()))
  if ok:traintexts[skill]=t;trainsets[key].append(skill)
pd.DataFrame(ver).to_csv(OUT/'source_validation.csv',index=False)
pd.DataFrame(trainver).to_csv(OUT/'training_source_validation.csv',index=False)
# Human-curated exploration groups, based on metadata purpose + body workflow, not file names.
groups={
 '求职与履历': [5,18,19,32,75,80,82,83,85,86,89],
 '论文写作转换与审校':[6,43,44,47,57,58,70,71,72,93,99],
 '幻灯片与图示':[13,21,33,34,40,41,50,65,66,68,69,94],
 '文档抽取与格式工具':[1,4,10,15,28,35,36,37,39,51,52,54,56,59,61,63,73,100],
 '软件文档与知识站':[22,26,27,29,45,46,90,96,97,98],
 '报告与研究工作流':[62,74,76,77,78],
 '其他专用工作流':[16,87,91]}
taskmap={i:g for g,ids in groups.items() for i in ids}
def lexical(t):
 w=re.findall(r'[A-Za-z0-9_]+|[\u4e00-\u9fff]',strip_yaml_front_matter(norm(t)).lower());return set(zip(w,w[1:],w[2:]))
def heads(t):return set(re.findall(r'^\s*(#{1,6})\s+',strip_yaml_front_matter(norm(t)),re.M))
def jacc(a,b):return len(a&b)/max(1,len(a|b))
lex={s:lexical(t) for s,t in {**contexts,**traintexts}.items()};hs={s:heads(t) for s,t in {**contexts,**traintexts}.items()}
features=[]
for skill,t in contexts.items():
 body=strip_yaml_front_matter(norm(t));lines=body.splitlines();nonblank=[l.strip() for l in lines if l.strip()];ct=Counter(nonblank);n=max(1,len(body));cs=0;in_code=False;code=[]
 for l in lines:
  if re.match(r'^\s*(```|~~~)',l):in_code=not in_code;code.append(l)
  elif in_code:code.append(l)
 headings=re.findall(r'^(#{1,6})\s+(.+)',body,re.M)
 desc=re.search(r'^description:\s*(.*)',t,re.M)
 d=dict(skill=skill,source_repository=sources[skill].strip(),purpose_group=taskmap[int(skill[:3])],description_first_line=desc.group(1) if desc else '',body_start=body[:170].replace('\n','\\n'),body_end=body[-170:].replace('\n','\\n'),body_chars=len(body),body_tokens=int(df.loc[df.skill==skill,'body_target_token_count'].iloc[0]),metadata_chars=len(norm(t))-len(body),line_count=len(lines),heading_count=len(headings),max_heading_level=max([len(h[0]) for h in headings] or [0]),heading_density=len(headings)/max(1,len(lines)),list_fraction=sum(len(l) for l in lines if re.match(r'^\s*(?:[-*+] |\d+[.)] )',l))/n,table_fraction=sum(len(l) for l in lines if l.strip().startswith('|'))/n,code_fraction=sum(map(len,code))/n,separator_count=sum(bool(re.fullmatch(r'\s*(?:---+|\*\*\*+|___+)\s*',l)) for l in lines),repeat_line_fraction=sum(len(l)*(c-1) for l,c in ct.items())/n,repeat_paragraph_fraction=0.,non_ascii_fraction=sum(ord(c)>127 for c in body)/n,cjk_fraction=len(re.findall(r'[\u4e00-\u9fff]',body))/n,digit_fraction=sum(c.isdigit() for c in body)/n,starts_html_comment=body.startswith('<!--'),has_input_arguments=bool(re.search(r'^## Input Arguments',body,re.M)),has_role_statement=bool(re.search(r'\b(?:you are|your role|as an? )\b',body,re.I)),has_report_template=bool(re.search(r'^#{1,6} .*?(?:Output Report Format|Report Template|Output Format|Report Format)',body,re.M|re.I)),example_heading_count=sum(bool(re.search(r'example|template|output|示例|模板|输出',h[1],re.I)) for h in headings),late_code_fraction=sum(len(l) for l in code if l in '\n'.join(lines[int(len(lines)*.75):]))/n,enhanced_metadata_banner='CLAUDE OFFICE SKILL - Enhanced Metadata' in t)
 paras=[p.strip() for p in re.split(r'\n\s*\n',body) if len(p.strip())>=40];pc=Counter(paras);d['repeat_paragraph_fraction']=sum(len(p)*(c-1) for p,c in pc.items())/n
 features.append(d)
f=pd.DataFrame(features).set_index('skill')
# metrics + distribution: repeated runs are within-document observations.
for metric in M:
 gb=df.groupby('skill')[metric]
 for stat in ['mean','median','std','min','max']: f[metric+'_'+stat]=getattr(gb,stat)()
 for q in [.1,.25,.75,.9]:f[metric+f'_q{int(q*100)}']=gb.quantile(q)
f['p_lt10']=df.groupby('skill')[R].apply(lambda x:(x<.1).mean());f['p_lt20']=df.groupby('skill')[R].apply(lambda x:(x<.2).mean());f['p_lt30']=df.groupby('skill')[R].apply(lambda x:(x<.3).mean());f['p_ge95']=df.groupby('skill')[R].apply(lambda x:(x>=.95).mean());f['p_mid20_80']=df.groupby('skill')[R].apply(lambda x:((x>=.2)&(x<.8)).mean())
f['exploratory_pattern']=np.select([(f.p_lt20>=.3)&(f.p_ge95>=.1),f.p_mid20_80>=.5],['frequent_low_occasional_near1','majority_partial'],default='other')
cfg=df.groupby(['skill','config'])[M].mean().reset_index();cfg['rank']=cfg.groupby('config')[R].rank(ascending=False,method='average');cfg.to_csv(OUT/'skill_config_metrics_ranks.csv',index=False)
ranks=cfg.pivot(index='skill',columns='config',values='rank');f['min_config_rank']=ranks.min(axis=1);f['max_config_rank']=ranks.max(axis=1);f['configs_top20']=(ranks<=20).sum(axis=1);f['configs_bottom20']=(ranks>50).sum(axis=1)
f['above_run_mean_rate']=df.assign(v=df[R]>df.groupby('run_key')[R].transform('mean')).groupby('skill').v.mean()
# Auxiliary train-test textual resemblance, independent of outcome metric tokenization.
sim=[]
for key,trs in trainsets.items():
 for skill in contexts:sim.append(dict(run_key=key,skill=skill,n_hash_verified_train=len(trs),max_train_word_trigram_jaccard=max(jacc(lex[skill],lex[x]) for x in trs),mean_train_word_trigram_jaccard=np.mean([jacc(lex[skill],lex[x]) for x in trs]),max_train_heading_level_jaccard=max(jacc(hs[skill],hs[x]) for x in trs),nearest_train=max(trs,key=lambda x:jacc(lex[skill],lex[x]))))
sim=pd.DataFrame(sim);sim.to_csv(OUT/'training_similarity.csv',index=False)
f['mean_max_train_word_trigram_jaccard']=sim.groupby('skill').max_train_word_trigram_jaccard.mean();f['mean_train_heading_level_jaccard']=sim.groupby('skill').max_train_heading_level_jaccard.mean()
num=['body_tokens','metadata_chars','heading_density','list_fraction','table_fraction','code_fraction','separator_count','repeat_line_fraction','repeat_paragraph_fraction','non_ascii_fraction','cjk_fraction','digit_fraction','starts_html_comment','has_input_arguments','has_role_statement','has_report_template','example_heading_count','enhanced_metadata_banner','mean_max_train_word_trigram_jaccard','mean_train_heading_level_jaccard']
def rho(a,b):return pd.Series(a).rank().corr(pd.Series(b).rank())
rng=np.random.default_rng(20261105);corr=[]
for col in num:
 a=f[col].astype(float).to_numpy();b=f[R+'_mean'].to_numpy();samples=[]
 for _ in range(1500):
  ix=rng.integers(0,len(a),len(a));
  if len(np.unique(a[ix]))>1:samples.append(rho(a[ix],b[ix]))
 A=np.column_stack([np.ones(len(f)),f.body_tokens.rank().to_numpy()]);ar=f[col].rank().to_numpy();br=f[R+'_mean'].rank().to_numpy();par=np.corrcoef(ar-A@np.linalg.lstsq(A,ar,rcond=None)[0],br-A@np.linalg.lstsq(A,br,rcond=None)[0])[0,1] if col!='body_tokens' else float('nan')
 corr.append(dict(feature=col,spearman=rho(a,b),ci_low=np.quantile(samples,.025) if samples else None,ci_high=np.quantile(samples,.975) if samples else None,partial_rank_length=par,n_documents=70))
corr=pd.DataFrame(corr);corr.to_csv(OUT/'feature_correlations.csv',index=False)
within=[]
for key,g in df.groupby('run_key'):
 gg=g.set_index('skill').join(f[num])
 for col in num:within.append(dict(run_key=key,feature=col,spearman=rho(gg[col].astype(float).to_numpy(),gg[R].to_numpy()),n_documents=70))
within=pd.DataFrame(within);within.to_csv(OUT/'within_run_feature_correlations.csv',index=False)
family=f.groupby('source_repository').agg(n=('body_tokens','size'),mean_recall=(R+'_mean','mean'),min_recall=(R+'_mean','min'),max_recall=(R+'_mean','max'),members=('purpose_group',lambda x:','.join(x.index)))
family.to_csv(OUT/'source_family_summary.csv');f.groupby('purpose_group').agg(n=('body_tokens','size'),mean_recall=(R+'_mean','mean'),min_recall=(R+'_mean','min'),max_recall=(R+'_mean','max'),members=('body_tokens',lambda x:','.join(x.index))).to_csv(OUT/'purpose_groups.csv')
# Length-matched descriptive pairs (relative length difference <=10%).
pairs=[]
for a,b in itertools.combinations(f.index,2):
 rel=abs(f.loc[a,'body_tokens']-f.loc[b,'body_tokens'])/min(f.loc[a,'body_tokens'],f.loc[b,'body_tokens'])
 if rel<=.1:
  av,bv=f.loc[a,R+'_mean'],f.loc[b,R+'_mean'];hi,lo=(a,b) if av>bv else (b,a)
  delta=cfg.pivot(index='skill',columns='config',values=R).loc[hi]-cfg.pivot(index='skill',columns='config',values=R).loc[lo]
  pairs.append(dict(high=hi,low=lo,high_tokens=f.loc[hi,'body_tokens'],low_tokens=f.loc[lo,'body_tokens'],relative_length_difference=rel,recall_gap=abs(av-bv),configs_high_beats_low=int((delta>0).sum()),same_family=f.loc[a,'source_repository']==f.loc[b,'source_repository'],same_purpose=f.loc[a,'purpose_group']==f.loc[b,'purpose_group']))
pd.DataFrame(pairs).sort_values('recall_gap',ascending=False).to_csv(OUT/'length_matched_pairs.csv',index=False)
f.sort_values(R+'_mean',ascending=False).to_csv(OUT/'skill_metrics_features.csv')
rankcorr=ranks.corr();rankcorr.to_csv(OUT/'config_rank_correlations.csv');upper=rankcorr.to_numpy()[np.triu_indices(9,1)]
# Orthogonal balanced two-way descriptive sum-of-squares, no causal interpretation.
piv=df.pivot(index='skill',columns='run_key',values=R);v=piv.to_numpy();grand=v.mean();ss=((v-grand)**2).sum();sdoc=v.shape[1]*((v.mean(axis=1)-grand)**2).sum();srun=v.shape[0]*((v.mean(axis=0)-grand)**2).sum()
summary=dict(n_outputs=len(df),n_docs=len(f),n_runs=len(runs),context_hash_checks=len(ver),n_train_unique=len(traintexts),rank_correlation_min=float(upper.min()),rank_correlation_median=float(np.median(upper)),rank_correlation_max=float(upper.max()),all9_top20=f.index[f.configs_top20==9].tolist(),all9_bottom20=f.index[f.configs_bottom20==9].tolist(),patterns=f.exploratory_pattern.value_counts().to_dict(),variance_descriptive=dict(skill=sdoc/ss,run=srun/ss,interaction_and_sampling_residual=1-(sdoc+srun)/ss),within_run_correlations=within.groupby('feature').spearman.agg(['median','min','max']).to_dict('index'))
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
# Figure labels English to ensure glyph reliability. Observed spread, not confidence intervals.
order=f.sort_values(R+'_mean').index;fig,ax=plt.subplots(figsize=(11,15));g=f.loc[order];ax.barh(range(70),g[R+'_mean'],color='#327b95');ax.set_yticks(range(70),[s for s in order],fontsize=6);ax.set_xlim(0,1);ax.set_xlabel('Mean body ROUGE-L Recall (81 formal runs / Skill; 70 Skills)');ax.set_title('Persistent Skill differences: all formal outputs');fig.tight_layout();fig.savefig(OUT/'skill_means.png',dpi=160);plt.close(fig)
fig,ax=plt.subplots(figsize=(10,15));im=ax.imshow(cfg.pivot(index='skill',columns='config',values=R).loc[order],aspect='auto',vmin=0,vmax=1,cmap='viridis');ax.set_yticks(range(70),order,fontsize=6);ax.set_xticks(range(9),ranks.columns,rotation=45);ax.set_title('Body ROUGE-L Recall by Skill and configuration\nEach cell: mean of 3 sample seeds x 3 attack seeds; no error bars');fig.colorbar(im,ax=ax,label='body ROUGE-L Recall');fig.tight_layout();fig.savefig(OUT/'skill_config_heatmap.png',dpi=160);plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(12,5));axs[0].scatter(f.body_tokens,f[R+'_mean'],alpha=.7);axs[0].set(xlabel='Body target tokens (official tokenizer)',ylabel='Mean body ROUGE-L Recall',title='70 Skills; each mean over 81 runs');axs[1].scatter(f.p_lt20,f.p_ge95,c=np.where(f.p_mid20_80>=.5,1,0),cmap='coolwarm',vmin=0,vmax=1);axs[1].set(xlabel='Fraction of 81 runs with Recall < 0.2',ylabel='Fraction with Recall >= 0.95',title='Observed patterns; red = majority partial [0.2, 0.8)');fig.tight_layout();fig.savefig(OUT/'length_and_patterns.png',dpi=160);plt.close(fig)
print(json.dumps(summary,ensure_ascii=False,indent=2));print(corr.sort_values('spearman').to_string(index=False))
