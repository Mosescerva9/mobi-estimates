#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BLOG = ROOT / 'blog'
AUTO = BLOG / 'automation'
CONTENT = BLOG / 'content'
RUNS = AUTO / 'run-records'
LOCKS = AUTO / 'locks'
RUNS.mkdir(parents=True, exist_ok=True); LOCKS.mkdir(parents=True, exist_ok=True)


def load_json(p): return json.loads(Path(p).read_text())
def save_json(p, data): Path(p).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')

def parse_doc(path: Path):
    raw=path.read_text(); m=re.match(r'^---json\n(.*?)\n---\n(.*)$', raw, re.S)
    if not m: raise SystemExit(f'missing canonical front matter: {path}')
    return json.loads(m.group(1)), m.group(2)

def write_doc(path: Path, meta: dict, body: str):
    path.write_text('---json\n'+json.dumps(meta, indent=2, sort_keys=True)+'\n---\n'+body)

def posts():
    out={}
    for p in CONTENT.glob('*.md'):
        m,b=parse_doc(p); out[m['id']]=(p,m,b)
    return out

def run(cmd, check=True):
    r=subprocess.run(cmd, cwd=ROOT.parent, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
    if check and r.returncode: raise SystemExit(r.stdout)
    return {'cmd':cmd,'returncode':r.returncode,'output':r.stdout[-6000:]}

def audit(action, article_id=None, status='ok', **extra):
    ts=dt.datetime.now(dt.timezone.utc).isoformat()
    rec={'timestamp_utc':ts,'action':action,'article_id':article_id,'status':status,**extra}
    name=(ts.replace(':','').replace('+','Z')+'_'+action+(('_'+article_id) if article_id else '')+'.json')
    (RUNS/name).write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n')
    return rec

def policy(): return load_json(AUTO/'publication-policy.json')
def queue(): return load_json(AUTO/'publication-queue.json')

def classify(meta, body):
    text=(json.dumps(meta)+'\n'+body).lower()
    high=['licensing','tax','legal','worker classification','insurance','bonding','safety compliance','guarantee','testimonial','official mobi pricing','free estimate']
    medium=['labor burden','overhead','contingency','cash flow','financial calculation','profit margin']
    if any(x in text for x in high): return 'high' if meta.get('risk_level')=='high' else meta.get('risk_level','medium')
    if any(x in text for x in medium): return 'medium' if meta.get('risk_level')!='low' else 'low'
    return meta.get('risk_level','low')

def validate(article_id=None):
    checks=[]
    checks.append(run(['python3','marketing-site/blog/scripts/generate_blog.py']))
    checks.append(run(['python3','marketing-site/blog/tests/test_blog_system.py']))
    all_posts=posts()
    failures=[]
    for aid,(path,meta,body) in all_posts.items():
        if meta.get('id')!=aid: failures.append(f'id mismatch {path}')
        if meta.get('status')=='published' and meta.get('noindex'): failures.append(f'published noindex {aid}')
        if meta.get('status')!='published' and not meta.get('noindex', True): failures.append(f'draft indexable {aid}')
        if meta.get('published_at') and meta.get('status')!='published': failures.append(f'draft has public published_at {aid}')
        risk=classify(meta, body)
        if risk in ['medium','high'] and meta.get('domain_review_status') not in ['approved','not_required']:
            # OK for draft; block only publish eligibility
            pass
        # original value minimum heuristic
        value_terms=sum(1 for term in ['example','formula','checklist','table','diagnostic','workflow','calculation'] if term in body.lower())
        if value_terms < 2: failures.append(f'insufficient original utility {aid}')
    if failures: raise SystemExit('\n'.join(failures))
    rec=audit('validate', article_id, results=checks, checked_articles=sorted(all_posts))
    print(json.dumps(rec,indent=2))

def eligible(article_id):
    pol=policy(); all_posts=posts()
    if article_id not in all_posts: return False, ['unknown article']
    path,meta,body=all_posts[article_id]
    reasons=[]
    if pol.get('kill_switch'): reasons.append('kill_switch_enabled')
    if not pol.get('autopublish_enabled'): reasons.append('autopublish_disabled')
    if meta.get('status') not in ['approved','scheduled']: reasons.append(f'status_not_publishable:{meta.get("status")}')
    risk=classify(meta, body)
    if risk not in pol.get('allowed_autonomous_risk_levels',[]): reasons.append(f'risk_not_allowed:{risk}')
    if risk in ['medium','high'] and meta.get('domain_review_status')!='approved': reasons.append('domain_review_not_approved')
    if meta.get('validation_status') not in ['passed','passed_shadow_preview']: reasons.append('validation_not_passed')
    return not reasons, reasons

def acquire(article_id, idem):
    lock=LOCKS/(article_id+'.lock')
    if lock.exists(): raise SystemExit(f'publication lock exists: {lock}')
    lock.write_text(idem+'\n')
    return lock

def release(lock):
    if lock and lock.exists(): lock.unlink()

def publish(article_id, mode):
    all_posts=posts(); q=queue(); idem=hashlib.sha256((article_id+':'+mode+':'+dt.datetime.now().date().isoformat()).encode()).hexdigest()[:16]
    dry = mode in ['dry-run','preview','shadow']
    ok,reasons=eligible(article_id)
    # dry/preview may run with eligibility blockers to prove gates, but scheduled cannot.
    if not ok and not dry:
        rec=audit('publish_blocked',article_id,status='blocked',mode=mode,reasons=reasons)
        print(json.dumps(rec,indent=2)); raise SystemExit(2)
    lock=None; backup=None
    try:
        lock=acquire(article_id, idem)
        path,meta,body=all_posts[article_id]
        backup={'path':str(path),'meta':meta,'body':body}
        if dry:
            steps=['confirm_eligible_or_record_blockers','confirm_risk_policy','acquire_lock','simulate_status_publish','simulate_noindex_removal','generate_site','simulate_sitemap','run_predeployment_tests','simulate_deployment_record','simulate_live_qa','release_lock']
            run(['python3','marketing-site/blog/scripts/generate_blog.py'])
            test=run(['python3','marketing-site/blog/tests/test_blog_system.py'])
            rec=audit('publish_dry_run',article_id,mode=mode,status='ok',eligibility_blockers=reasons,idempotency_key=idem,steps=steps,test=test)
            print(json.dumps(rec,indent=2)); return
        # Production path exists but is guarded; not expected in this task.
        meta['status']='published'; meta['published_at']=dt.datetime.now(dt.timezone.utc).isoformat(); meta['noindex']=False; meta['canonical_url']='https://mobiestimates.com/blog/'+meta['slug']+'/'
        write_doc(path, meta, body)
        run(['python3','marketing-site/blog/scripts/generate_blog.py']); run(['python3','marketing-site/blog/tests/test_blog_system.py'])
        rec=audit('publish',article_id,mode=mode,status='published',idempotency_key=idem,rollback_point=backup)
        print(json.dumps(rec,indent=2))
    except Exception as e:
        if backup:
            Path(backup['path']).write_text('---json\n'+json.dumps(backup['meta'],indent=2,sort_keys=True)+'\n---\n'+backup['body'])
            run(['python3','marketing-site/blog/scripts/generate_blog.py'], check=False)
        rec=audit('publish_failed',article_id,status='failed',error=str(e),idempotency_key=idem)
        print(json.dumps(rec,indent=2)); raise
    finally:
        release(lock)

def rollback(article_id, dry=True):
    run(['python3','marketing-site/blog/scripts/generate_blog.py'])
    rec=audit('rollback_simulation' if dry else 'rollback',article_id,status='ok',dry_run=dry,steps=['restore_previous_commit_or_deployment','regenerate_site','restore_sitemap','run_tests','record_incident'])
    print(json.dumps(rec,indent=2))

def verify_live(article_id):
    rec=audit('verify_live_simulation',article_id,status='blocked',reason='No live deployment URL exists in shadow mode; production verification requires deployed URL and credentials/connectors.')
    print(json.dumps(rec,indent=2))

def pause():
    p=policy(); p['kill_switch']=True; p['autopublish_enabled']=False; save_json(AUTO/'publication-policy.json',p); print('autopublish paused')

def resume():
    p=policy();
    if not Path(AUTO/'activation-approved.flag').exists(): raise SystemExit('Missing activation-approved.flag; explicit Moses authorization required.')
    p['kill_switch']=False; p['autopublish_enabled']=True; save_json(AUTO/'publication-policy.json',p); print('autopublish resumed for allowed low-risk policy only')

def shadow():
    validate()
    results=[]
    for aid in posts().keys():
        try:
            publish(aid,'shadow')
            rollback(aid, dry=True)
            results.append({'article_id':aid,'shadow_publish':'ok','rollback':'ok'})
        except SystemExit as e:
            results.append({'article_id':aid,'shadow_publish':'failed','code':e.code})
    rec=audit('shadow_run',status='ok',results=results,activation_ready=False,reason='Shadow-mode count below activation threshold and explicit authorization not present.')
    print(json.dumps(rec,indent=2))

def status(article_id=None):
    data={'policy':policy(),'queue':queue(),'articles':{aid:meta for aid,(p,meta,b) in posts().items()}}
    if article_id: data={'article':data['articles'].get(article_id),'eligible':eligible(article_id)}
    print(json.dumps(data,indent=2,sort_keys=True))

def main():
    ap=argparse.ArgumentParser(prog='hermes blog')
    sub=ap.add_subparsers(dest='cmd',required=True)
    sub.add_parser('validate')
    p=sub.add_parser('publish'); p.add_argument('article_id'); g=p.add_mutually_exclusive_group(); g.add_argument('--dry-run',action='store_true'); g.add_argument('--preview',action='store_true'); g.add_argument('--scheduled',action='store_true')
    r=sub.add_parser('rollback'); r.add_argument('article_id'); r.add_argument('--dry-run',action='store_true',default=True)
    v=sub.add_parser('verify-live'); v.add_argument('article_id')
    sub.add_parser('pause-autopublish'); sub.add_parser('resume-autopublish'); sub.add_parser('queue'); s=sub.add_parser('status'); s.add_argument('article_id',nargs='?'); sub.add_parser('shadow-run')
    a=ap.parse_args()
    if a.cmd=='validate': validate()
    elif a.cmd=='publish': publish(a.article_id, 'dry-run' if a.dry_run else 'preview' if a.preview else 'scheduled' if a.scheduled else 'dry-run')
    elif a.cmd=='rollback': rollback(a.article_id, dry=True)
    elif a.cmd=='verify-live': verify_live(a.article_id)
    elif a.cmd=='pause-autopublish': pause()
    elif a.cmd=='resume-autopublish': resume()
    elif a.cmd=='queue': print(json.dumps(queue(),indent=2))
    elif a.cmd=='status': status(a.article_id)
    elif a.cmd=='shadow-run': shadow()
if __name__=='__main__': main()
