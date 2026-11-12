"""Continuous metric overview; all effects descriptive, never 5670 iid samples."""
import os,json
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/soft-followup-mpl')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(__file__).resolve().parent
M=['body_rougeL_recall','body_rouge2_recall','body_rougeL_precision']
LABEL=['Body ROUGE-L Recall','Body ROUGE-2 Recall','Body ROUGE-L Precision']
def summary(x):
    return {'n':len(x),'mean':x.mean(),'median':x.median(),'sd':x.std(),'min':x.min(),'q10':x.quantile(.1),'q25':x.quantile(.25),'q75':x.quantile(.75),'q90':x.quantile(.9),'max':x.max()}
def main():
    (OUT/'figures').mkdir(exist_ok=True)
    d=pd.read_csv(OUT/'validated_outputs.csv');d['config']=d.apply(lambda r:f"t{r.train_num}_p{r.prefix_length}",axis=1)
    runs=d.groupby(['run_key','run_id','train_num','prefix_length','sample_seed','attack_seed','config'])[M].mean().reset_index()
    skills=d.groupby('skill')[M].mean()
    configs=runs.groupby('config')[M].mean()
    rows=[]
    for level,frame in [('output',d),('run_mean',runs),('skill_mean',skills),('config_mean',configs)]:
        for m in M:rows.append({'level':level,'metric':m,**summary(frame[m])})
    pd.DataFrame(rows).to_csv(OUT/'metric_distributions.csv',index=False)
    rows=[]
    for (t,p),g in d.groupby(['train_num','prefix_length']):
        rr=runs[(runs.train_num==t)&(runs.prefix_length==p)]
        for m in M:rows.append({'train_num':t,'prefix_length':p,'metric':m,**summary(g[m]),'run_count':9,'run_mean_sd':rr[m].std(),'run_mean_median':rr[m].median(),'run_mean_min':rr[m].min(),'run_mean_max':rr[m].max()})
    pd.DataFrame(rows).to_csv(OUT/'config_metric_statistics.csv',index=False)
    rstats=d.groupby('run_key')[M].agg(['mean','median','std','min','max']);rstats.columns=['_'.join(x) for x in rstats.columns]
    runs.merge(rstats,on='run_key').to_csv(OUT/'run_metric_statistics.csv',index=False)
    ss=d.groupby('skill')[M].agg(['mean','median','std','min','max']);ss.columns=['_'.join(x) for x in ss.columns];ss.to_csv(OUT/'skill_metric_statistics.csv')
    sc=d.groupby(['skill','config'])[M].agg(['mean','median','std']);sc.columns=['_'.join(x) for x in sc.columns];sc=sc.reset_index()
    for m in M:sc[m+'_rank']=sc.groupby('config')[m+'_mean'].rank(ascending=False,method='average')
    sc.to_csv(OUT/'skill_config_metrics.csv',index=False)
    decomposition=[];corrs=[];stability=[]
    for m in M:
        x=d.pivot(index='skill',columns='run_key',values=m).to_numpy();mu=x.mean();a=x.mean(axis=1,keepdims=True)-mu;b=x.mean(axis=0,keepdims=True)-mu;res=x-mu-a-b;total=((x-mu)**2).sum()
        for name,v in [('skill_main',81*(a*a).sum()),('run_main',70*(b*b).sum()),('skill_run_residual',(res*res).sum())]:decomposition.append({'metric':m,'component':name,'sum_squares':v,'fraction':v/total,'note':'Balanced 70x81 descriptive SS; residual includes interaction and generation randomness; no causal attribution'})
        p=sc.pivot(index='skill',columns='config',values=m+'_mean')
        c=p.rank().corr();c.to_csv(OUT/f'config_rank_correlation_{m}.csv')
        vals=c.to_numpy()[np.triu_indices(9,1)]
        corrs.append({'metric':m,'pair_count':36,'median_spearman':np.median(vals),'min_spearman':min(vals),'max_spearman':max(vals)})
        ranks=p.rank(ascending=False)
        st=pd.DataFrame({'metric':m,'skill':p.index,'top_quartile_configs':(ranks<=18).sum(axis=1),'bottom_quartile_configs':(ranks>=53).sum(axis=1),'min_rank':ranks.min(axis=1),'max_rank':ranks.max(axis=1)})
        stability.append(st)
    pd.DataFrame(decomposition).to_csv(OUT/'descriptive_variance_decomposition.csv',index=False)
    pd.DataFrame(corrs).to_csv(OUT/'cross_config_stability.csv',index=False)
    pd.concat(stability).to_csv(OUT/'skill_rank_stability.csv',index=False)
    # Low-score slices are diagnostics, not attack-success definitions.
    slices=[]
    for m in M:
        for t in [.1,.2,.3]:slices.append({'metric':m,'threshold':t,'count':int((d[m]<t).sum()),'denominator':len(d),'fraction':float((d[m]<t).mean())})
    pd.DataFrame(slices).to_csv(OUT/'threshold_slices.csv',index=False)
    bins=np.linspace(0,1,11);hist=[]
    for m in M:
        n,_=np.histogram(d[m],bins)
        hist.extend({'metric':m,'lower':bins[i],'upper':bins[i+1],'count':int(v),'last_bin_includes_one':i==9} for i,v in enumerate(n))
    pd.DataFrame(hist).to_csv(OUT/'metric_histograms.csv',index=False)
    metriccorr=d[M].corr();metriccorr.to_csv(OUT/'metric_pearson_correlation.csv')
    fig,axs=plt.subplots(1,3,figsize=(13,4.1),sharey=True)
    for ax,m,label in zip(axs,M,LABEL):
        ax.hist(d[m],bins=bins,color='#366a95',edgecolor='white');ax.set(title=label,xlabel='Score [0,1]',xlim=(0,1));ax.grid(axis='y',alpha=.2)
    axs[0].set_ylabel('Output count');fig.suptitle('All 5,670 outputs = 81 formal runs x 70 shared Skills; bin width 0.1',fontsize=11)
    fig.tight_layout();fig.savefig(OUT/'figures/metric_distributions.png',dpi=180);plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(14,4.6),sharey=True)
    for ax,m,label in zip(axs,M,LABEL):
        for j,(config,g) in enumerate(runs.groupby('config',sort=False)):
            ax.scatter(np.repeat(j,9),g[m],alpha=.65,s=20,color='#7697b8')
            ax.errorbar(j,g[m].mean(),yerr=g[m].std(),fmt='o',color='#172f47',capsize=3)
        ax.set_xticks(range(9),[c for c,g in runs.groupby('config',sort=False)],rotation=60,ha='right');ax.set(title=label,ylim=(0,1));ax.grid(axis='y',alpha=.2)
    axs[0].set_ylabel('Mean across the same 70 Skills');fig.suptitle('Each config: 3 sample seeds x 3 attack seeds; dark point mean +/- SD of 9 runs (not CI)',fontsize=11)
    fig.tight_layout();fig.savefig(OUT/'figures/config_metric_variation.png',dpi=180);plt.close(fig)
    # Paired config changes: same sample and attack seed labels, same 70 docs. Not independent replication.
    paired=[]
    for t in [3,4,5]:
        for p1,p2 in [(8,16),(8,32),(16,32)]:
            a=runs[(runs.train_num==t)&(runs.prefix_length==p1)].set_index(['sample_seed','attack_seed'])
            b=runs[(runs.train_num==t)&(runs.prefix_length==p2)].set_index(['sample_seed','attack_seed'])
            for m in M:
                z=b[m]-a[m];paired.append({'train_num':t,'prefix_from':p1,'prefix_to':p2,'metric':m,'paired_run_labels':9,'mean_difference':z.mean(),'median_difference':z.median(),'positive_pairs':int((z>0).sum()),'min':z.min(),'max':z.max()})
    pd.DataFrame(paired).to_csv(OUT/'paired_config_differences.csv',index=False)
    print(pd.DataFrame(rows).to_string(index=False));print(pd.DataFrame(decomposition).to_string(index=False));print(pd.DataFrame(corrs).to_string(index=False))
if __name__=='__main__':main()
