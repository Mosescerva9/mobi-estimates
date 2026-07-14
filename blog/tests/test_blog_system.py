#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re, subprocess, sys, tempfile, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BLOG=ROOT/'blog'
CONTENT=BLOG/'content'
PAGES=[BLOG/'index.html', BLOG/'construction-estimating-mistakes/index.html', BLOG/'construction-markup-vs-margin/index.html', BLOG/'editorial-standards/index.html']
ARTICLE=BLOG/'construction-estimating-mistakes/index.html'
CSS=BLOG/'assets/blog.css'
SITEMAP=BLOG/'public-sitemap-preview.xml'
SCREENSHOT_DIR=Path('/home/hermes/Documents/Obsidian Vault/Mobi Estimates/13 Marketing/SEO Blog/screenshots/blog-system')
REQUIRED_WIDTHS=[320,360,375,390,430,768,1024,1440]


def parse(path):
    raw=path.read_text(); m=re.match(r'^---json\n(.*?)\n---\n(.*)$',raw,re.S)
    if not m: raise AssertionError(f'missing front matter: {path}')
    return json.loads(m.group(1)), m.group(2)

def fail_if(name, cond, failures):
    if cond: failures.append(name)

def main():
    failures=[]
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in PAGES if p.exists()}
    r=subprocess.run(['python3','marketing-site/blog/scripts/generate_blog.py'],cwd=ROOT.parent,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
    fail_if('generator failed: '+r.stdout, r.returncode!=0, failures)
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in PAGES if p.exists()}
    fail_if('generated-file drift after deterministic regenerate', before and before!=after, failures)
    metas=[]
    for md in CONTENT.glob('*.md'):
        meta,body=parse(md); metas.append(meta)
        required=['id','slug','title','seo_title','meta_description','excerpt','category','tags','search_intent','primary_query','secondary_queries','editorial_attribution','status','risk_level','domain_review_status','noindex','schema_type','validation_status','approval_requirement']
        for k in required: fail_if(f'{md.name} missing {k}', k not in meta, failures)
        fail_if(f'{md.name} draft has public published_at', meta.get('status')!='published' and bool(meta.get('published_at')), failures)
        fail_if(f'{md.name} draft indexable', meta.get('status')!='published' and not meta.get('noindex',True), failures)
        utility=sum(1 for term in ['example','formula','checklist','table','diagnostic','workflow','calculation'] if term in body.lower())
        fail_if(f'{md.name} lacks original utility', utility<2, failures)
    for p in PAGES:
        html=p.read_text()
        fail_if(f'{p}: missing noindex', 'noindex, nofollow' not in html, failures)
        fail_if(f'{p}: h1 count not one', html.count('<h1') != 1, failures)
        fail_if(f'{p}: hash placeholder link', '<a href="#"' in html, failures)
        for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>',html,re.S): json.loads(m)
    a=ARTICLE.read_text(); css=CSS.read_text()
    fail_if('H1 may clip: mobile hero lacks safe-area padding', 'env(safe-area-inset-top)' not in css, failures)
    fail_if('H1 may clip: header offset not defined', '--header-offset:76px' not in css, failures)
    fail_if('mobile breadcrumb behavior not intentional', '.blog-breadcrumb{display:none}' not in css or '.mobile-back{display:inline-block}' not in css, failures)
    fail_if('mobile process steps not readable at 320/360', '@media(max-width:360px)' not in css or '.process-steps{grid-template-columns:1fr}' not in css, failures)
    fail_if('process graphic missing', 'process-steps' not in a, failures)
    fail_if('internal process commentary visible', 'not navigation' in a.lower(), failures)
    fail_if('draft displays false public Published label', 'Published:' in a, failures)
    fail_if('updated date visible in draft/equal-first-launch state', 'Updated:' in a, failures)
    fail_if('estimator review claim present', 'Reviewed by an estimator' in a or 'expert reviewed' in a.lower(), failures)
    fail_if('draft sitemap includes draft URLs', '<url><loc>' in SITEMAP.read_text(), failures)
    missing=[]
    for w in REQUIRED_WIDTHS:
        for section in ['hero','body','table','cta','footer']:
            if not (SCREENSHOT_DIR/f'{w}-{section}.png').exists(): missing.append(f'{w}-{section}')
    fail_if('missing responsive visual artifacts: '+','.join(missing[:12]), bool(missing), failures)
    # Broken-fixture sanity: high-risk official pricing must be blocked by policy/risk routing.
    policy=json.loads((BLOG/'automation/publication-policy.json').read_text())
    fail_if('autopublish unexpectedly enabled', policy.get('autopublish_enabled'), failures)
    fail_if('kill switch unexpectedly off', not policy.get('kill_switch'), failures)
    result={'status':'ok' if not failures else 'failed','failures':failures,'checked_pages':[str(p) for p in PAGES],'canonical_articles':[m['id'] for m in metas]}
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if not failures else 1)
if __name__=='__main__': main()
