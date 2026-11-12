"""Offline full audit; run with Python providing tokenizers==0.21.1.
No model calls, no source writes. Original evaluator's whole-token LCS retained.
"""
import csv, hashlib, json, sys
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from util.overlap_metrics import strip_yaml_front_matter, rouge_overlap
from tokenizers import Tokenizer
OUT = Path(__file__).resolve().parent
DATA = ROOT / 'results/qwen/analysis/data'
csv.field_size_limit(100_000_000)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s): return s.replace('\r\n','\n').replace('\r','\n').strip()
def main():
    index=json.loads((DATA/'all_results.json').read_text())
    runs=[r for r in index['runs'] if r['role']=='primary' and r['scope']=='formal_test70' and r['status']=='complete']
    assert len(runs)==81
    assert Counter((r['train_num'],r['prefix_length']) for r in runs)==Counter({(t,p):9 for t in [3,4,5] for p in [8,16,32]})
    combos={(r['train_num'],r['prefix_length'],r['sample_seed'],r['attack_seed']) for r in runs}
    assert combos=={(t,p,s,a) for t in [3,4,5] for p in [8,16,32] for s in [0,1,2] for a in [1,2,3]}
    tokpath=ROOT/'results/qwen/analysis/support/tokenizer/tokenizer.json'
    tok=Tokenizer.from_file(str(tokpath)); special={x['id'] for x in json.loads(tokpath.read_text())['added_tokens'] if x['special']}
    def enc(s): return [i for i in tok.encode(s,add_special_tokens=False).ids if i not in special]
    detail=list(csv.DictReader((DATA/'per_skill/skill_run_details.csv').open(encoding='utf-8-sig')))
    lookup={(r['run_id'],int(r['sample_index'])):r for r in detail}
    assert len(lookup)==len(detail)==5670
    errors=[]; rows=[]; hashes={}; targets={}; tests=None; decode_ok=0; maxerr=0; sets=[]
    fields=['body_rougeL_recall','body_rouge2_recall','body_rougeL_precision']
    for run in runs:
        short=f"t{run['train_num']}_p{run['prefix_length']}_s{run['sample_seed']}_a{run['attack_seed']}"
        ep=ROOT/run['source_evaluation']; gp=ep.parent/'decoded_generations.jsonl'; cp=ROOT/run['source_results']; sp=ROOT/run['source_samples']
        for p in [ep,gp,cp,sp]:hashes[str(p.relative_to(ROOT))]=sha(p)
        ev=json.loads(ep.read_text()); gens=[json.loads(l) for l in gp.read_text().splitlines()]; raw=list(csv.DictReader(cp.open()))
        assert len(ev['samples'])==len(gens)==len(raw)==70
        paths=tuple(s['sample_path'] for s in ev['samples'])
        if tests is None:tests=paths
        assert paths==tests
        subsets=json.loads(sp.read_text())['train_samples'];sets.append({'run_key':short,'train_samples':subsets})
        for e,g,c in zip(ev['samples'],gens,raw):
            i=e['index']; assert i==g['sample_index']==int(c['sample_index']); assert e['sample_path']==g['sample_path']==c['sample_path']
            skill=Path(e['sample_path']).parent.name
            body=strip_yaml_front_matter(norm(c['context'])); pred=strip_yaml_front_matter(norm(g['generation']))
            if skill not in targets:targets[skill]=(c['context'],enc(body))
            assert targets[skill][0]==c['context']
            ids=json.loads(c['raw_generation_ids']); dec=tok.decode(ids,skip_special_tokens=True)
            if dec!=g['generation']: errors.append([short,i,'decode'])
            else:decode_ok+=1
            pt=enc(pred); vals=rouge_overlap(targets[skill][1],pt)
            assert len(pt)==e['body_prediction_token_count'];assert len(targets[skill][1])==e['body_target_token_count']
            d=lookup[(run['run_id'],i)]
            for f in fields:
                err=max(abs(vals[f[5:]]-e[f]),abs(float(d[f])-e[f]));maxerr=max(maxerr,err)
                if err>1e-12:errors.append([short,i,f,err])
            rows.append({'run_key':short,'run_id':run['run_id'],'skill':skill,'sample_index':i,**{k:run[k] for k in ['train_num','prefix_length','sample_seed','attack_seed']},**{k:e[k] for k in fields+['body_target_token_count','body_prediction_token_count','ended_with_eos']},'source_evaluation':str(ep.relative_to(ROOT)),'source_generation':str(gp.relative_to(ROOT)),'source_results':str(cp.relative_to(ROOT))})
        for f in fields:
            mean=sum(e[f] for e in ev['samples'])/70
            assert abs(mean-run['metrics']['mean_'+f])<1e-12
        print(short,'audited',flush=True)
    assert len(targets)==70;assert not errors,errors[:10]
    for p in [DATA/'all_results.json',DATA/'per_skill/skill_run_details.csv',ROOT/'Sampler.py',ROOT/'util/overlap_metrics.py',tokpath]:hashes[str(p.relative_to(ROOT))]=sha(p)
    with (OUT/'validated_outputs.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    (OUT/'input_hashes.json').write_text(json.dumps(hashes,indent=2))
    result={'primary_runs':len(runs),'outputs':len(rows),'skills':len(targets),'identical_test_order':True,'factorial_complete':True,'raw_decode_exact_agreements':decode_ok,'metric_max_absolute_error':maxerr,'metric_mismatches':errors,'excluded_index_records':[{'run_id':r['run_id'],'role':r['role'],'status':r['status']} for r in index['runs'] if r not in runs], 'tokenizer_sha256':sha(tokpath),'previous_soft_recall_actual_path':'results/qwen/analysis/data/soft_recall','user_requested_soft_recall_path_exists':(ROOT/'results/qwen/analysis/soft_recall').exists()}
    (OUT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
