#!/usr/bin/env python3
"""Offline output diagnoses. Run with local environment containing tokenizers.
Metrics are copied unchanged from corrected evaluations; anchors are auxiliary.
"""
import csv,json,re,sys,hashlib
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT))
from util.overlap_metrics import strip_yaml_front_matter
from tokenizers import Tokenizer
OUT=Path(__file__).resolve().parent
TOK=Tokenizer.from_file(str(ROOT/'results/qwen/analysis/support/tokenizer/tokenizer.json'))
SPECIAL={int(k) for k,v in json.load(open(ROOT/'results/qwen/analysis/support/tokenizer/tokenizer_config.json'))['added_tokens_decoder'].items() if v.get('special')}
def body(s): return strip_yaml_front_matter(s.replace('\r\n','\n').replace('\r','\n').strip())
def encode(s): return [x for x in TOK.encode(s,add_special_tokens=False).ids if x not in SPECIAL]
def reps(ids,k=8):
 c=Counter(tuple(ids[i:i+k]) for i in range(max(0,len(ids)-k+1)))
 return (1-len(c)/sum(c.values()),max(c.values())) if c else (0,0)
def anchors(ref,pred,k=16):
 # Unique target k-grams avoid assigning boilerplate to the wrong location.
 idx={};dup=set()
 for i in range(len(ref)-k+1):
  key=tuple(ref[i:i+k])
  if key in idx: dup.add(key)
  else:idx[key]=i
 for key in dup:del idx[key]
 pairs=[]
 for j in range(len(pred)-k+1):
  i=idx.get(tuple(pred[j:j+k]))
  if i is not None:pairs.append((i,j))
 blocks=[]
 for i,j in pairs:
  if blocks and i==blocks[-1][0]+blocks[-1][2]-k+1 and j==blocks[-1][1]+blocks[-1][2]-k+1:blocks[-1][2]+=1
  else:blocks.append([i,j,k])
 # Retain >=24-token exact spans, disjoint in prediction. Diagnostic anchors only.
 keep=[];end=-1
 for b in blocks:
  if b[2]>=24 and b[1]>=end:keep.append(b);end=b[1]+b[2]
 return keep

def writecsv(name,rows):
 rows=list(rows)
 if rows:
  with open(OUT/name,'w',newline='',encoding='utf-8-sig') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
 index=json.load(open(ROOT/'results/qwen/analysis/data/all_results.json'))
 runs=[x for x in index['runs'] if x['role']=='primary' and x['scope']=='formal_test70' and x['included_in_summary']]
 rows=[];texts={};hashmismatch=[];refs={}
 for run in runs:
  key=f"t{run['train_num']}_p{run['prefix_length']}_s{run['sample_seed']}_a{run['attack_seed']}"
  ev=json.load(open(ROOT/run['source_evaluation']));mets={s['index']:s for s in ev['samples']}
  dec={x['sample_index']:x['generation'] for x in map(json.loads,open(ROOT/run['source_decoded_generations']))}
  csv.field_size_limit(sys.maxsize)
  originals=list(csv.DictReader(open(ROOT/run['source_results'])))
  for src in originals:
   si=int(src['sample_index']);m=mets[si];skill=Path(src['sample_path']).parent.name
   if skill not in refs:
    context=src['context'];local=ROOT/'data/skill_expansion_20260922/samples/documents'/skill/'SKILL.md'
    if local.read_text()!=context:hashmismatch.append(skill)
    ref=encode(body(context));refs[skill]=(context,ref)
   context,ref=refs[skill];predtext=body(dec[si]);pred=encode(predtext)
   assert len(ref)==m['body_target_token_count'] and len(pred)==m['body_prediction_token_count'],(key,si)
   rr,rm=reps(ref);pr,pm=reps(pred);bl=anchors(ref,pred)
   n=len(ref);pn=len(pred); R=m['body_rougeL_recall'];P=m['body_rougeL_precision']
   alnum=sum(c.isalnum() for c in predtext);blank=not predtext.strip();near=alnum<8
   loop=(pn>=64 and pm>=5 and pr>=.55 and pr-rr>=.25)
   covered=sum(b[2] for b in bl)/max(1,pn)
   first=bl[0] if bl else [-1,-1,0];last=bl[-1] if bl else [-1,-1,0]
   shifted=bool(bl and covered>=.3 and first[1]<=max(32,.1*pn) and first[0]>=max(48,.1*n))
   jumps=[]
   pred8={tuple(pred[j:j+8]) for j in range(max(0,pn-7))}
   for a,b in zip(bl,bl[1:]):
    rg=b[0]-(a[0]+a[2]);pg=b[1]-(a[1]+a[2])
    gapgrams=[tuple(ref[j:j+8]) for j in range(a[0]+a[2],b[0]-7)]
    missing_fraction=sum(g not in pred8 for g in gapgrams)/max(1,len(gapgrams))
    if rg>=max(48,.05*n) and 0<=pg<=max(24,.25*rg) and missing_fraction>=.7 and R<.98: jumps.append([a[0]+a[2],b[0],pg,missing_fraction])
   max_end=max([b[0]+b[2] for b in bl] or [0])
   rollback=any(b[0]<a[0]+a[2]-max(48,.05*n) for a,b in zip(bl,bl[1:]))
   prefix_stop=bool(bl and R<.9 and not shifted and not rollback and first[0]<=max(24,.03*n) and first[1]<=max(32,.1*pn) and max_end<=.9*n and pn-(last[1]+last[2])<=max(32,.1*pn) and covered>=.65)
   restart=bool(max_end>=.9*n and any(b[0]<a[0]+a[2]-.5*n for a,b in zip(bl,bl[1:])))
   rawtext=dec[si]
   whitespace_loop=bool(len(rawtext)>=128 and alnum<8)
   normalized_lines=[re.sub(r'\d+','<N>',s.strip()) for s in predtext.splitlines() if s.strip()]
   linecounts=Counter(normalized_lines)
   template_repeat=sum(len(s)*(c-1) for s,c in linecounts.items())/max(1,sum(map(len,normalized_lines)))
   template_loop=bool(max(linecounts.values(),default=0)>=5 and template_repeat>=.55)
   eos=src['ended_with_eos'].lower()=='true';budget=int(src['generated_token_count'])==int(src['prompt_token_count'])+50
   stop='eos' if eos else 'budget' if budget else 'other_unknown'
   labels=[]
   for test,label in [(blank,'blank'),(near and not blank,'near_empty'),(loop,'repetitive_loop'),(shifted,'shifted_start'),(prefix_stop,'prefix_copy_then_stop'),(bool(jumps),'internal_skip_anchor'),(restart,'document_restart'),(rollback and not restart,'partial_document_restart'),(whitespace_loop,'whitespace_or_separator_loop'),(template_loop,'numeric_normalized_line_loop')]:
    if test:labels.append(label)
   if blank or near:primary='empty_or_near_empty'
   elif loop:primary='repetitive_loop'
   elif shifted and jumps:primary='shifted_and_skips'
   elif shifted:primary='shifted_start'
   elif prefix_stop:primary='prefix_copy_then_stop'
   elif jumps:primary='internal_skips'
   elif R>=.9:primary='high_coverage_other'
   else:primary='other_uncertain'
   record={'run_key':key,'run_id':run['run_id'],'skill':skill,'sample_index':si,**{k:run[k] for k in ['train_num','prefix_length','sample_seed','attack_seed']},**{k:m[k] for k in ['body_rougeL_recall','body_rouge2_recall','body_rougeL_precision','body_target_token_count','body_prediction_token_count']},'primary_type':primary,'labels':'|'.join(labels),'stop_state':stop,'ended_with_eos':eos,'budget_hit':budget,'generated_token_count':src['generated_token_count'],'prompt_token_count':src['prompt_token_count'],'nonspace_alnum_chars':alnum,'prediction_repeat8_fraction':pr,'reference_repeat8_fraction':rr,'max_repeat8_count':pm,'anchor_prediction_coverage':covered,'first_anchor_reference_fraction':first[0]/n if bl else -1,'first_anchor_prediction_position':first[1],'last_anchor_reference_fraction':(last[0]+last[2])/n if bl else -1,'internal_skip_count':len(jumps),'anchors_json':json.dumps(bl),'skip_intervals_json':json.dumps(jumps),'source_decoded_generations':run['source_decoded_generations'],'source_results':run['source_results'],'evidence_output_head':predtext[:180].replace('\n','\\n'),'evidence_output_tail':predtext[-120:].replace('\n','\\n')}
   record.update(max_anchor_reference_fraction=max_end/n,numeric_normalized_line_repeat_fraction=template_repeat,rule_version='unique16gram_runs24_v2_conservative_omission')
   rows.append(record);texts[key+'|'+str(si)]={'reference_body':body(context),'prediction_body':predtext}
  print(key,flush=True)
 writecsv('output_diagnostics.csv',rows)
 json.dump(texts,open(OUT/'review_texts.json','w'),ensure_ascii=False)
 summary=[]
 for metric in ['body_rougeL_recall','body_rouge2_recall','body_rougeL_precision']:
  for threshold in [.1,.2,.3]:
   sel=[x for x in rows if x[metric]<threshold];counts=Counter(x['primary_type'] for x in sel)
   for typ,count in sorted(counts.items()):summary.append({'metric':metric,'threshold':threshold,'n_slice':len(sel),'primary_type':typ,'count':count,'fraction':count/len(sel)})
 writecsv('threshold_type_distribution.csv',summary)
 for unit in ['skill','run_key']:
  groups=defaultdict(list)
  for x in rows:groups[x[unit]].append(x)
  result=[];types=sorted(set(x['primary_type'] for x in rows))
  for key,group in groups.items():
   low=[x for x in group if x['body_rougeL_recall']<.2]
   rec={unit:key,'n_outputs':len(group),'n_low':len(low)}
   for typ in types:rec[typ+'_all']=sum(x['primary_type']==typ for x in group);rec[typ+'_low']=sum(x['primary_type']==typ for x in low)
   for lab in ['blank','near_empty','repetitive_loop','shifted_start','prefix_copy_then_stop','internal_skip_anchor']:rec[lab+'_label_rate']=sum(lab in x['labels'].split('|') for x in group)/len(group)
   result.append(rec)
  writecsv(unit+'_type_counts.csv',result)
 json.dump({'runs':len(runs),'outputs':len(rows),'skills':len(refs),'local_context_mismatch':hashmismatch,'rule_version':'unique16gram_runs24_v2_conservative_omission','metric_policy':'unchanged corrected evaluator fields','primary_counts':dict(Counter(x['primary_type'] for x in rows))},open(OUT/'validation.json','w'),indent=2)
if __name__=='__main__':main()
