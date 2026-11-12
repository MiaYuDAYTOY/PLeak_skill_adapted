"""Join independently verified analyses and preserve analyst reading annotations."""
from pathlib import Path
import os,json
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/soft-followup-mpl')
import pandas as pd,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parent
d=pd.read_csv(P/'diagnostics/output_diagnostics.csv').fillna({'labels':''})
f=pd.read_csv(P/'skills/skill_metrics_features.csv').set_index('skill')
l=pd.read_csv(P/'loss/run_loss_summary.csv')
M=['body_rougeL_recall','body_rouge2_recall','body_rougeL_precision']
labels=sorted(set('|'.join(d.labels).split('|'))-{''})
types=sorted(d.primary_type.unique())
for lab in labels:d['label_'+lab]=d.labels.str.split('|').map(lambda a:lab in a)
def grouped(unit):
 out=[]
 for name,g in d.groupby(unit):
  lo=g[g[M[0]]<.2];row={unit:name,'n_outputs':len(g),'n_low':len(lo)}
  for typ in types:
   row['type_'+typ+'_n']=int((g.primary_type==typ).sum());row['type_'+typ+'_rate']=float((g.primary_type==typ).mean());row['type_'+typ+'_low_n']=int((lo.primary_type==typ).sum());row['type_'+typ+'_low_rate']=float((lo.primary_type==typ).mean()) if len(lo) else np.nan
  for lab in labels:row['label_'+lab+'_rate']=g['label_'+lab].mean()
  row['budget_hit_rate']=g.budget_hit.mean();row['eos_rate']=g.ended_with_eos.mean();out.append(row)
 return pd.DataFrame(out)
rg=grouped('run_key');sg=grouped('skill')
l.merge(rg,on='run_key',validate='one_to_one',suffixes=('','_diagnostic')).to_csv(P/'run_loss_metrics_types.csv',index=False)
for upper in [.8,.9,.95]:
 f[f'p_partial_02_{int(upper*100)}']=d.groupby('skill')[M[0]].apply(lambda s:((s>=.2)&(s<upper)).mean())
f['majority_partial_02_95']=f.p_partial_02_95>=.5
f.join(sg.set_index('skill')).to_csv(P/'skill_metrics_features_types.csv')
sg.to_csv(P/'diagnostics/skill_type_composition.csv',index=False);rg.to_csv(P/'diagnostics/run_type_composition.csv',index=False)
rows=[]
for lo,hi in [(0,.2),(.2,.8),(.8,1.0001)]:
 g=d[(d[M[0]]>=lo)&(d[M[0]]<hi)]
 rows.append(dict(recall_from=lo,recall_to=hi,n=len(g),budget_count=int(g.budget_hit.sum()),eos_count=int(g.ended_with_eos.sum()),budget_rate=g.budget_hit.mean(),eos_rate=g.ended_with_eos.mean(),zero_rouge2_count=int((g[M[1]]==0).sum())))
pd.DataFrame(rows).to_csv(P/'diagnostics/stop_state_by_recall.csv',index=False)
feature_cols=['body_tokens','separator_count','has_input_arguments','code_fraction','table_fraction','has_report_template','example_heading_count','cjk_fraction','repeat_line_fraction']
g=f.join(sg.set_index('skill'));cor=[]
for feat in feature_cols:
 for lab in labels:
  a=g[feat].astype(float);b=g['label_'+lab+'_rate'];cor.append(dict(feature=feat,label=lab,spearman=a.rank().corr(b.rank()),n_documents=70))
pd.DataFrame(cor).to_csv(P/'feature_output_type_correlations.csv',index=False)
# Correlations with run-level proportions, demeaned within exact training condition.
rr=l.merge(rg,on='run_key');cr=[]
for feat in ['final_loss','relative_loss_drop','accepted_updates']:
 for lab in labels:
  col='label_'+lab+'_rate';a=rr[feat]-rr.groupby(['train_num','prefix_length','sample_seed'])[feat].transform('mean');b=rr[col]-rr.groupby(['train_num','prefix_length','sample_seed'])[col].transform('mean')
  cr.append(dict(feature=feat,label=lab,within_condition_pearson=a.corr(b),n_runs=81,n_groups=27))
pd.DataFrame(cr).to_csv(P/'loss_output_type_correlations.csv',index=False)
scale_checks=[]
for prefix,sub in rr.groupby('prefix_length'):
 for feat in ['final_loss','relative_loss_drop','accepted_updates']:
  for metric in M:
   a=sub[feat]-sub.groupby(['train_num','sample_seed'])[feat].transform('mean')
   b=sub[metric]-sub.groupby(['train_num','sample_seed'])[metric].transform('mean')
   scale_checks.append(dict(prefix_length=prefix,feature=feat,metric=metric,within_exact_condition_pearson=a.corr(b),n_runs=27,n_groups=9))
pd.DataFrame(scale_checks).to_csv(P/'loss_within_condition_by_prefix.csv',index=False)
# A dependency sensitivity: demean rank features/outcomes within source repository.
ff=[]
for feat in feature_cols:
 a=f[feat].astype(float).rank();b=f[M[0]+'_mean'].rank();a=a-a.groupby(f.source_repository).transform('mean');b=b-b.groupby(f.source_repository).transform('mean')
 ff.append(dict(feature=feat,within_source_rank_correlation=a.corr(b),n_documents=70,n_source_families=f.source_repository.nunique(),note='Descriptive residual ranks; singleton families contribute zero; not causal adjustment'))
pd.DataFrame(ff).to_csv(P/'within_source_feature_sensitivity.csv',index=False)
ex=[]
for subset,g in [('all70',f),('exclude_christopherkenny',f[~f.source_repository.str.contains('christopherkenny')]),('christopherkenny_only',f[f.source_repository.str.contains('christopherkenny')])]:
 for feat in ['body_tokens','separator_count','has_input_arguments','code_fraction']:
  value=g[feat].astype(float).rank().corr(g[M[0]+'_mean'].rank()) if g[feat].nunique()>1 else np.nan
  ex.append(dict(subset=subset,n_documents=len(g),feature=feat,spearman=value))
pd.DataFrame(ex).to_csv(P/'feature_family_exclusion_sensitivity.csv',index=False)
# Actual readings: 54 original stratified cases plus two newly selected stopping examples.
notes={
0:('loop','交替两行trigger样文本贯穿输出。'),2:('loop','同一trigger样两行反复，与正文主题无关。'),4:('loop','Quarto文档链接反复。'),7:('loop','同一nameka行反复。'),10:('loop','Daily/Weekly/Monthly示例框架重复；不是逐字复制全文。'),11:('loop_shift','从Sarah Chen示例开始反复复制，循环与错位共存，中分。'),12:('reformat_omit','YAML包裹、开头说明缺失、标题简化，正文主体仍高覆盖。'),14:('high_extra','近完整复制后附加trigger与元数据，预算命中不等于正文截断。'),
18:('empty','剥离正文仅---，原始换行状态另看raw。'),19:('empty','正文为空。'),22:('empty','正文为空，即使持续高分Skill也有此例。'),23:('empty_loop','---循环，近空和重复共存。'),24:('empty_loop','---循环，近空和重复共存。'),25:('empty_loop','竖线表格分隔符循环，无字母数字。'),
26:('partial_restart','复制部分后回到前部继续，末尾Context Gathering，旧prefix-stop误报。'),27:('partial_restart','有较长正文覆盖，末尾回到Common Pitfalls，旧prefix-stop不足以证明截断。'),28:('high_restart','接近完整后回到Input Arguments，旧prefix-stop误报。'),29:('high_restart','完整末尾已出现后重启格式表，旧prefix-stop误报。'),30:('high_restart','近完整后回到Setup/CLI shorthand，旧prefix-stop误报。'),31:('high_restart','R=1后回到Workflow，旧prefix-stop明确误报。'),32:('high_restart','R=1后回到Setup，旧prefix-stop明确误报。'),33:('high_restart','R=1后重启When to Use，旧prefix-stop明确误报。'),
34:('short_uncertain','仅name segregation两词，8字母数字阈值未归近空，属于低有效内容漏检。'),35:('unrelated','只输出新License段，无原文主体。'),36:('loop','循环生成xberg元数据；精确8gram规则漏检。'),37:('unrelated','新增example.com资源链接列表，没有复制正文。'),38:('unrelated','只生成Apache许可证正文。'),39:('template_loop','Heading 1至145递增，精确重复8gram漏检，数字归一化标签可捕获。'),40:('metadata_rewrite','只生成title/description/keywords等元数据描述，正文未复制。'),41:('metadata_rewrite','主要输出anydoc元数据，正文未复制；不应把描述相似当正文复制。'),42:('template_loop','连续数字1到840，单行数字序列，行归一化仍可能漏检。'),43:('restructure_loop','JSON参数结构与深层空格嵌套，正文流程未重现。'),44:('restructure','将chunking转成JSON schema参数说明，观察到结构改写。'),45:('template_loop','YAML参数后review_date条目反复，保守循环阈值漏检。'),46:('rewrite_continue','从Step5开始继续编到Step21，相关主题续写但非原文复制。'),47:('rewrite_continue','PDF示例工作流及注释式步骤改写，不能仅凭低重合判拒答。'),48:('restructure','Reference List Builder被转成JSON键值，含原文内容、删节与结构改写。'),49:('reformat_omit','YAML包裹并跳开头/部分段落，不能断言只是语义概括。'),50:('shift_restart','从make.sh示例开始，后部又回到CREATE表格；错位与回跳，自动规则漏检。'),51:('partial_restart','YAML包裹正文后回到前部默认格式段落。'),52:('partial_restart','复制大部分后回到Input Arguments，不是单纯停止。'),53:('partial_omit','正文缺部分尾部规则，EOS后含异常文字；需保留复合。'),
54:('internal_skip','中间Reader Testing相关约591token缺失；末尾Attribution正常，明确漏段。'),55:('internal_skip','Reference模板至Timing一段约286token缺失，后段恢复且EOS。'),56:('internal_skip_loop','Safety Rules相关大段缺失、后面检查表局部反复；漏段与循环共存。'),60:('high_reformat','R=.994，元数据包裹与尾部多余词；旧跳段锚点不能证明大段遗漏。'),61:('high_reformat','R=.997，YAML包裹/额外词；旧跳段规则误报。'),62:('restructure_loop','JSON Clause描述后递归properties/空格；小锚点错误映射成错位，已提高覆盖条件。'),63:('shift','从文末Pass criteria对应段开始，改作Fail criteria，EOS，低覆盖。'),64:('shift','从LaTeX示例开始再复制文末转换指南，错位。'),65:('shift_loop','从Example workflow开始，例子片段反复；严格8gram阈值可能漏掉循环。'),66:('shift_restart','跳过Your Task等前部，到Sheet Music Publisher Agent，后文又回跳。'),68:('shift_restart','跳过CAPABILITIES等开头，从Trigger Guidance复制并回到Document Types。'),71:('shift_restart','从提取命令与批注示例开始，后文回到命令片段。')}
old=pd.read_csv(P/'diagnostics/manual_review_sample.csv');new=d.set_index(['run_key','sample_index']);reviews=[]
for idx,(obs,note) in notes.items():
 r=old.iloc[idx];n=new.loc[(r.run_key,r.sample_index)];reviews.append(dict(review_id=int(r.review_id),run_key=r.run_key,sample_index=int(r.sample_index),skill=r.skill,body_rougeL_recall=r[M[0]],initial_primary=r.primary_type,final_primary=n.primary_type,reading_observation=obs,reading_note=note,primary_rule_changed=r.primary_type!=n.primary_type,review_method='Analyst direct reading of reference and output head/middle/tail plus anchors; targeted gap reads; not independent human gold labels'))
for key,si,obs,note in [('t3_p8_s0_a3',31,'prefix_stop_budget','复制前部到table代码块闭合前，预算用尽；原文后续Rust示例及Reference缺失。'),('t3_p16_s0_a3',9,'prefix_stop_eos','复制到Empty input后EOS；原文末尾配置和CLI引用缺失。')]:
 n=new.loc[(key,si)];reviews.append(dict(review_id=100+len(reviews),run_key=key,sample_index=si,skill=n.skill,body_rougeL_recall=n[M[0]],initial_primary='new_review',final_primary=n.primary_type,reading_observation=obs,reading_note=note,primary_rule_changed=False,review_method='Analyst direct reading of actual reference/output tail and token anchors'))
pd.DataFrame(reviews).to_csv(P/'diagnostics/analyst_review.csv',index=False)
review_summary={'reviewed_records':len(reviews),'initial_packet_records':72,'unreviewed_packet_records':72-len(notes),'method':'Purposive stratified review, not random error-rate estimation; same cases informed rule refinement','initial_to_final_changes_among_reviewed':sum(x['primary_rule_changed'] for x in reviews),'observations':pd.Series([x['reading_observation'] for x in reviews]).value_counts().to_dict()}
(P/'diagnostics/review_summary.json').write_text(json.dumps(review_summary,ensure_ascii=False,indent=2))
fig,axs=plt.subplots(1,2,figsize=(12,4.6))
name={'repetitive_loop':'Repeated token sequences','empty_or_near_empty':'Empty / near-empty','other_uncertain':'Other / uncertain','shifted_start':'Shifted copying start'}
colors=['#315d82','#7d9bb6','#d5a353','#9d746a']
for threshold,offset in zip([.1,.2,.3],[-.25,0,.25]):
 g=d[d[M[0]]<threshold];vc=g.primary_type.value_counts()
 axs[0].bar(np.arange(4)+offset,[vc.get(x,0)/len(g)*100 for x in name],width=.24,label=f'R<{threshold}; n={len(g)}')
axs[0].set_xticks(range(4),list(name.values()),rotation=20,ha='right');axs[0].set_ylabel('Percent of low-Recall slice');axs[0].legend(fontsize=8);axs[0].set_title('Mutually exclusive primary types (rule v2)')
st=pd.DataFrame(rows);xx=np.arange(3);axs[1].bar(xx-.18,st.budget_rate*100,.35,label='Budget hit');axs[1].bar(xx+.18,st.eos_rate*100,.35,label='EOS');axs[1].set_xticks(xx,[f'R<{.2}\nn={st.iloc[0]["n"]:.0f}',f'0.2<=R<0.8\nn={st.iloc[1]["n"]:.0f}',f'R>=0.8\nn={st.iloc[2]["n"]:.0f}']);axs[1].set_ylabel('Percent within Recall band');axs[1].legend();axs[1].set_title('Stopping state does not establish truncation')
fig.suptitle('81 formal runs x 70 shared Skills; observed counts, no confidence intervals',fontsize=11);fig.tight_layout();fig.savefig(P/'figures/output_types_and_stops.png',dpi=180);plt.close(fig)
print(json.dumps(review_summary,ensure_ascii=False));print(pd.DataFrame(rows).to_string(index=False))
