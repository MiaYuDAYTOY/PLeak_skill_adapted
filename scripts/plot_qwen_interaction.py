"""Publication-style descriptive interaction plots for Qwen primary runs."""
from pathlib import Path
import os,json
os.environ.setdefault('MPLCONFIGDIR','/tmp/qwen_plot_mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/qwen/analysis/figures/interaction';OUT.mkdir(parents=True,exist_ok=True)
source=ROOT/'results/qwen/analysis/data/analysis_data.json'
data=json.loads(source.read_text())
assert data['formal_runs']==81 and data['sample_records']==5670
assert all(g['run_count']==9 and g['sample_records']==630 for g in data['groups'])
groups={(g['train_num'],g['prefix_length']):g for g in data['groups']}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':11,
    'axes.labelsize':10,'axes.labelcolor':'#334155','text.color':'#172b42',
    'xtick.color':'#64748b','ytick.color':'#64748b','axes.edgecolor':'#cbd5e1',
    'axes.linewidth':.8,'axes.spines.top':False,'axes.spines.right':False,
    'svg.fonttype':'none','legend.frameon':False,'axes.unicode_minus':True})
metrics=[('full_rate','Full-prefix ASR'),('body_recall','Body ROUGE-L recall')]
colors=['#426BA6','#CC7959','#4C9285'];markers=['o','s','^']
matrices={k:np.array([[groups[t,p][k]*100 for p in (8,16,32)] for t in (3,4,5)]) for k,_ in metrics}
def save(fig,name):
    for ext in ('png','svg'):fig.savefig(OUT/f'{name}.{ext}',dpi=260,bbox_inches='tight',facecolor='white')
    plt.close(fig)
fig,axes=plt.subplots(2,2,figsize=(11.6,7.8))
fig.subplots_adjust(left=.085,right=.975,top=.80,bottom=.18,wspace=.25,hspace=.52)
for i,(key,label) in enumerate(metrics):
    mat=matrices[key]
    for j in range(2):
        ax=axes[i,j]
        for n in range(3):
            x=[3,4,5] if j==0 else [8,16,32]
            y=mat[:,n] if j==0 else mat[n,:]
            level=([8,16,32] if j==0 else [3,4,5])[n]
            ax.plot(x,y,color=colors[n],marker=markers[n],lw=2.2,ms=6.5,
                    markeredgecolor='white',markeredgewidth=.8,label=str(level),zorder=3)
        ax.set_xticks(x)
        ax.set_xlabel('train_num' if j==0 else 'prefix_length (tokens)',labelpad=8)
        ax.set_ylabel(label+' (%)',labelpad=9)
        ax.set_title('abcd'[i*2+j]+'   Varying '+('train_num' if j==0 else 'prefix_length'),loc='left',pad=12,fontweight='bold')
        ax.grid(axis='y',color='#e7ecf1',lw=.8,zorder=0)
        ax.tick_params(axis='both',length=0,pad=7)
        ax.legend(title='prefix_length' if j==0 else 'train_num',ncol=3,
            loc='upper center',bbox_to_anchor=(.5,1.0),fontsize=9,title_fontsize=9,
            handlelength=1.6,columnspacing=1.8,labelspacing=.4,borderaxespad=0)
        ax.set_ylim((0,14) if i==0 else (45,76))
        ax.set_yticks([0,3,6,9,12] if i==0 else [45,50,55,60,65,70,75])
        if j==0:ax.set_xlim(2.84,5.16)
        else:ax.set_xlim(6,34)
fig.text(.085,.955,'Parameter interactions',fontsize=19,fontweight='bold',ha='left')
fig.text(.085,.91,'Qwen3-0.6B-Base  /  train_num × prefix_length',fontsize=11,color='#64748b')
fig.text(.085,.052,'Each point: 9 seed pairs per configuration · 70 test documents per run.',fontsize=9,color='#64748b')
fig.text(.085,.026,'Lines connect tested configurations; patterns are descriptive, without a significance claim.',fontsize=8.5,color='#64748b')
save(fig,'factor_interaction')

cmap=LinearSegmentedColormap.from_list('conditional',['#B66D5C','#F9FAFB','#426BA6'])
fig=plt.figure(figsize=(11.8,7.1))
gs=fig.add_gridspec(2,4,left=.11,right=.93,bottom=.19,top=.76,wspace=.18,hspace=.85,width_ratios=[1,.20,1,.035])
effects={}
for i,(key,label) in enumerate(metrics):
    m=matrices[key];effects[key]={}
    limit=max(abs(np.diff(m,axis=0)).max(),abs(np.diff(m,axis=1)).max())
    for j in range(2):
        ax=fig.add_subplot(gs[i,j*2])
        delta=np.diff(m,axis=0) if j==0 else np.diff(m,axis=1).T
        effects[key]['train_changes' if j==0 else 'prefix_changes']=delta.tolist()
        im=ax.imshow(delta,cmap=cmap,vmin=-limit,vmax=limit,aspect='auto')
        for row in range(2):
            for col in range(3):
                val=delta[row,col]
                ax.text(col,row,f'{val:+.2f}',ha='center',va='center',fontsize=16,
                    color='white' if abs(val)>limit*.58 else '#243449',fontweight='medium')
        ax.set_xticks(range(3));ax.set_yticks(range(2))
        ax.set_xticklabels(['8','16','32'] if j==0 else ['3','4','5'])
        ax.set_yticklabels(['3 → 4','4 → 5'] if j==0 else ['8 → 16','16 → 32'])
        ax.set_xlabel('prefix_length' if j==0 else 'train_num',labelpad=8)
        ax.set_ylabel('Δ train_num' if j==0 else 'Δ prefix_length',labelpad=8)
        ax.set_title('abcd'[i*2+j]+'   '+label,loc='left',pad=12,fontweight='bold')
        ax.set_xticks(np.arange(-.5,3,1),minor=True);ax.set_yticks(np.arange(-.5,2,1),minor=True)
        ax.grid(which='minor',color='white',lw=3)
        ax.tick_params(which='both',length=0,pad=7)
        for spine in ax.spines.values():spine.set_visible(False)
    cb=fig.colorbar(im,cax=fig.add_subplot(gs[i,3]));cb.outline.set_visible(False)
    cb.set_label('Δ (percentage points)',fontsize=9,labelpad=10);cb.ax.tick_params(length=0,labelsize=8)
fig.text(.11,.955,'Conditional changes',fontsize=19,fontweight='bold')
fig.text(.11,.91,'The same parameter change can have different effects across configurations.',fontsize=10.5,color='#64748b')
fig.text(.11,.843,'INCREASE train_num',fontsize=10,fontweight='bold',color='#426BA6')
fig.text(.553,.843,'INCREASE prefix_length',fontsize=10,fontweight='bold',color='#426BA6')
fig.text(.11,.04,'Blue: increase · Terracotta: decrease · Values show percentage-point changes between tested levels.',fontsize=9,color='#64748b')
save(fig,'conditional_changes')
(OUT/'plot_data.json').write_text(json.dumps({'source':str(source.relative_to(ROOT)),'train_values':[3,4,5],'prefix_values':[8,16,32],'configuration_percent':{k:v.tolist() for k,v in matrices.items()},'changes_pp':effects},ensure_ascii=False,indent=2))
(OUT/'README.md').write_text('''# 训练文档数 × 监督前缀：描述性交互图

- [双向交互作用图](factor_interaction.png) · [SVG](factor_interaction.svg)：行是完整前缀 ASR、正文 ROUGE-L Recall；左列横轴为训练文档数，右列为监督前缀长度。
- [条件变化幅度图](conditional_changes.png) · [SVG](conditional_changes.svg)：显示相邻已测试参数值之间的指标增减，单位为百分点。同一行正负号不同直接表示效果方向随另一参数改变。
- [绘图数据及变化幅度](plot_data.json)

每个配置采用冻结的 9 次正式主运行，共 630 条测试记录。ASR 为完整前缀成功数/630；Recall 为记录均值。没有混入被替代尝试。

正文 Recall 的例子：prefix_length=32 时，train_num=3→4→5 为 61.14%→50.73%→61.16%；prefix_length=16→32 时，train_num=3 上升 7.83 个百分点，train_num=4 下降 10.13 个百分点，train_num=5 下降 5.11 个百分点。

ASR 的例子：prefix_length=8 时，train_num=3→4→5 为 3.97%→10.63%→7.94%；prefix_length=8→16 时，train_num=3 上升 0.48 个百分点，train_num=4 下降 2.38 个百分点，train_num=5 不变。

合适表述：在已测试网格内，增加训练文档数或延长监督前缀，并未带来一致的单调提升；变化的方向和幅度取决于另一参数的取值。这是对配置均值的描述，不等于所有固定参数条件下均非单调，也不声称统计显著的交互效应。seed 对共用测试文档，不能直接把 630 条记录视为独立实验。

复现：`python3 scripts/plot_qwen_interaction.py`。
''')
print(json.dumps({k:v.tolist() for k,v in matrices.items()},indent=2))
