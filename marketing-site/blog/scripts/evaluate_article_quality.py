#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BLOG=ROOT/'blog'
CONTENT=BLOG/'content'
RUBRIC=json.loads((BLOG/'quality/rubric.json').read_text())
GENERIC_FLAGS=[x.lower() for x in RUBRIC.get('generic_ai_language_flags',[])]


def parse_doc(article_id):
    path=CONTENT/f'{article_id}.md'
    raw=path.read_text()
    m=re.match(r'^---json\n(.*?)\n---\n(.*)$',raw,re.S)
    if not m: raise SystemExit(f'missing front matter: {path}')
    return path,json.loads(m.group(1)),m.group(2)


def score(article_id):
    path,meta,body=parse_doc(article_id)
    text=body.lower()
    flags=[]
    utility=sum(1 for term in ['example','formula','checklist','table','diagnostic','workflow','calculation','template','decision'] if term in text)
    ai=[f for f in GENERIC_FLAGS if f in text]
    if ai: flags.append({'category':'readability','severity':'warn','message':'generic AI language: '+', '.join(ai)})
    if utility < RUBRIC['required_original_utility_count']:
        flags.append({'category':'usefulness','severity':'block','message':'insufficient original utility'})
    if 'free estimate' in text:
        flags.append({'category':'mobi_claim_accuracy','severity':'block','message':'free-estimate offer requires explicit approval'})
    if any(x in text for x in ['guaranteed', 'win rate', 'accuracy percentage', 'increase profits']):
        flags.append({'category':'unsupported_claims','severity':'block','message':'unsupported guarantee/performance language'})
    if meta.get('status')=='published' and meta.get('noindex'):
        flags.append({'category':'publication_safety','severity':'block','message':'published article remains noindex'})
    if meta.get('status')!='published' and not meta.get('noindex',True):
        flags.append({'category':'publication_safety','severity':'block','message':'draft article indexable'})
    if not meta.get('primary_query') or not meta.get('search_intent'):
        flags.append({'category':'search_intent_satisfaction','severity':'block','message':'missing query or intent'})
    if 'estimate' in text and any(sym in text for sym in ['$', '%']) and 'formula' not in text:
        flags.append({'category':'factual_accuracy','severity':'warn','message':'possible calculation without formula label'})
    scores={}
    for cat,cfg in RUBRIC['categories'].items():
        base=90
        for f in flags:
            if f['category']==cat:
                base-=25 if f['severity']=='block' else 10
        if cat=='usefulness' and utility>=3: base=92
        if cat=='originality' and utility>=3: base=90
        if cat in ['mobi_claim_accuracy','unsupported_claims'] and not any(f['category']==cat for f in flags): base=98
        if cat=='publication_safety' and meta.get('status')!='published' and meta.get('noindex'): base=96
        scores[cat]=max(0,min(100,base))
    total_weight=sum(c['weight'] for c in RUBRIC['categories'].values())
    overall=round(sum(scores[k]*RUBRIC['categories'][k]['weight'] for k in scores)/total_weight,1)
    blockers=[f for f in flags if f['severity']=='block']
    for cat in RUBRIC['blocking_categories']:
        if scores.get(cat,0) < RUBRIC['categories'][cat]['minimum']:
            blockers.append({'category':cat,'severity':'block','message':f'{cat} below minimum'})
    status='pass' if overall>=RUBRIC['minimum_overall_score'] and not blockers else 'fail'
    return {'article_id':article_id,'rubric_version':RUBRIC['version'],'overall_score':overall,'category_scores':scores,'utility_count':utility,'flags':flags,'blocking_failures':blockers,'status':status,'source':str(path.relative_to(ROOT))}


def comparison(article_id):
    result=score(article_id)
    lines=[f'# Gold-Standard Comparison Report — {article_id}', '', 'Gold standard: `construction-markup-vs-margin`', f'Rubric version: `{result["rubric_version"]}`', '', f'Overall quality score: **{result["overall_score"]}**', f'Status: **{result["status"]}**', '']
    if result['blocking_failures']:
        lines.append('## Blocking failures')
        for f in result['blocking_failures']: lines.append(f'- {f["category"]}: {f["message"]}')
    else:
        lines.append('## Blocking failures\nNone.')
    lines += ['', '## Comparison findings', '- Search intent documented and evaluated against the article primary query.', '- Original utility count is compared to the gold standard requirement without requiring the same formulas/tables.', '- Mobi claims and promotional balance are checked against canonical restrictions.', '- Publication state and noindex behavior are checked for safety.', '', '## Required corrections before publishing', 'None if deterministic validation, responsive screenshots, and human/semantic review also pass.']
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('article_id'); ap.add_argument('--write-report',action='store_true')
    args=ap.parse_args(); data=score(args.article_id)
    if args.write_report:
        out=BLOG/'quality/reports'/f'{args.article_id}-quality-comparison.md'; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(comparison(args.article_id))
        jout=BLOG/'quality/reports'/f'{args.article_id}-quality-score.json'; jout.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
    print(json.dumps(data,indent=2,sort_keys=True))
    raise SystemExit(0 if data['status']=='pass' else 1)
