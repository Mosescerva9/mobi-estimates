#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re, subprocess, urllib.parse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BLOG=ROOT/'blog'
CONTENT=BLOG/'content'
PAGES=[BLOG/'index.html', BLOG/'construction-estimating-mistakes/index.html', BLOG/'construction-markup-vs-margin/index.html', BLOG/'editorial-standards/index.html', BLOG/'how-to-estimate-labor-costs/index.html']
ARTICLE=BLOG/'construction-estimating-mistakes/index.html'
PUBLISHED_ARTICLE=BLOG/'construction-markup-vs-margin/index.html'
CSS=BLOG/'assets/blog.css'
SITEMAP=BLOG/'public-sitemap-preview.xml'
SCREENSHOT_DIR=Path('/home/hermes/Documents/Obsidian Vault/Mobi Estimates/13 Marketing/SEO Blog/screenshots/blog-system')
REQUIRED_WIDTHS=[320,360,375,390,430,768,1024,1440]
FIXTURES=BLOG/'tests/fixtures'


def parse(path):
    raw=path.read_text(); m=re.match(r'^---json\n(.*?)\n---\n(.*)$',raw,re.S)
    if not m: raise AssertionError(f'missing front matter: {path}')
    return json.loads(m.group(1)), m.group(2)

def fail_if(name, cond, failures):
    if cond: failures.append(name)

def page_for_slug(slug): return BLOG/slug/'index.html'

def classify_pricing_claim(text):
    low=text.lower()
    if 'mobi charges exactly' in low or 'official pricing' in low: return 'official_pricing'
    if '$' in text and any(x in low for x in ['formula','educational','example']): return 'educational_example'
    return 'none'

def body_links_bad(html, page_url):
    bad=[]
    for href in re.findall(r'<a [^>]*href="([^"]+)"',html):
        if href.startswith(('#','mailto:','tel:')): continue
        resolved=urllib.parse.urljoin(page_url,href)
        if resolved.endswith('/blog/sample-estimate.html') or resolved.endswith('/blog/how-it-works.html'):
            bad.append((href,resolved))
    return bad

def main():
    failures=[]
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in PAGES if p.exists()}
    r=subprocess.run(['python3','marketing-site/blog/scripts/generate_blog.py'],cwd=ROOT.parent,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
    fail_if('generator failed: '+r.stdout, r.returncode!=0, failures)
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in PAGES if p.exists()}
    fail_if('generated-file drift after deterministic regenerate', before and before!=after, failures)

    # Gold-standard reference immutability/sanity.
    ref=BLOG/'reference/gold-standard-article'
    fail_if('gold standard reference missing', not ref.exists(), failures)
    fail_if('gold standard canonical source missing approved ID', 'construction-markup-vs-margin' not in (ref/'canonical-source.md').read_text(), failures)
    fail_if('quality rubric missing', not (BLOG/'quality/rubric.json').exists(), failures)
    fail_if('definition of done missing', not (BLOG/'quality/definition-of-done.md').exists(), failures)

    metas=[]; published=[]
    for md in CONTENT.glob('*.md'):
        meta,body=parse(md); metas.append(meta)
        required=['id','slug','title','seo_title','meta_description','excerpt','category','tags','search_intent','primary_query','secondary_queries','editorial_attribution','status','risk_level','domain_review_status','noindex','schema_type','validation_status','approval_requirement']
        for k in required: fail_if(f'{md.name} missing {k}', k not in meta, failures)
        if meta.get('status')=='published':
            published.append(meta)
            fail_if(f'{md.name} published remains noindex', bool(meta.get('noindex')), failures)
            fail_if(f'{md.name} missing published_at', not meta.get('published_at'), failures)
            fail_if(f'{md.name} updated_at set on first publication', bool(meta.get('updated_at')), failures)
        else:
            fail_if(f'{md.name} draft has public published_at', bool(meta.get('published_at')), failures)
            fail_if(f'{md.name} draft indexable', not meta.get('noindex',True), failures)
        utility=sum(1 for term in ['example','formula','checklist','table','diagnostic','workflow','calculation','template','decision'] if term in body.lower())
        fail_if(f'{md.name} lacks original utility', utility<2, failures)
        fail_if(f'{md.name} unapproved free-estimate language', 'free estimate' in body.lower(), failures)
        fail_if(f'{md.name} unsupported Mobi claim', any(x in body.lower() for x in ['guaranteed win','accuracy percentage','guaranteed savings']), failures)

    for p in [x for x in PAGES if x.exists()]:
        html=p.read_text()
        fail_if(f'{p}: h1 count not one', html.count('<h1') != 1, failures)
        fail_if(f'{p}: hash placeholder link', '<a href="#"' in html, failures)
        fail_if(f'{p}: internal implementation note public', 'not navigation' in html.lower(), failures)
        for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>',html,re.S): json.loads(m)
    fail_if('blog archive canonical malformed', 'https://mobiestimates.com/blog//' in (BLOG/'index.html').read_text(), failures)
    for meta in metas:
        html=page_for_slug(meta['slug']).read_text()
        if meta.get('status')=='published':
            fail_if(f'{meta["slug"]}: published has noindex', 'noindex, nofollow' in html, failures)
            fail_if(f'{meta["slug"]}: missing canonical', f'https://mobiestimates.com/blog/{meta["slug"]}/' not in html, failures)
            fail_if(f'{meta["slug"]}: missing visible Published', 'Published:' not in html, failures)
            fail_if(f'{meta["slug"]}: visible Updated on first launch', 'Updated:' in html, failures)
        else:
            fail_if(f'{meta["slug"]}: draft missing noindex', 'noindex, nofollow' not in html, failures)
            fail_if(f'{meta["slug"]}: draft displays false public Published label', 'Published:' in html, failures)
            fail_if(f'{meta["slug"]}: draft visible in public archive', f'{meta["slug"]}/' in (BLOG/'index.html').read_text(), failures)
        fail_if(f'{meta["slug"]}: broken blog-relative CTA link', bool(body_links_bad(html, f'https://mobiestimates.com/blog/{meta["slug"]}/')), failures)

    a=ARTICLE.read_text(); pub=PUBLISHED_ARTICLE.read_text(); css=CSS.read_text()
    fail_if('H1 may clip: mobile hero lacks safe-area padding', 'env(safe-area-inset-top)' not in css, failures)
    fail_if('H1 may clip: header offset not defined', '--header-offset:76px' not in css, failures)
    fail_if('mobile breadcrumb behavior not intentional', '.blog-breadcrumb{display:none}' not in css or '.mobile-back{display:inline-block}' not in css, failures)
    fail_if('mobile process steps not readable at 320/360', '@media(max-width:360px)' not in css or '.process-steps{grid-template-columns:1fr}' not in css, failures)
    fail_if('process graphic missing', 'process-steps' not in a or 'process-steps' not in pub, failures)
    fail_if('estimator review claim present', 'Reviewed by an estimator' in pub or 'expert reviewed' in pub.lower(), failures)
    fail_if('third-party source attribution implies ownership', 'our procore' in pub.lower() or 'our jobtread' in pub.lower(), failures)

    sitemap=SITEMAP.read_text()
    for meta in metas:
        in_sitemap=f'https://mobiestimates.com/blog/{meta["slug"]}/' in sitemap
        fail_if(f'{meta["slug"]}: sitemap publication state wrong', in_sitemap != (meta.get('status')=='published' and not meta.get('noindex')), failures)

    # Fixture assertions: good educational dollars pass classification; broken pricing/free-offer/draft-state fixtures fail.
    good=(FIXTURES/'good/educational-dollar-example.md').read_text()
    fail_if('educational dollar example misclassified', classify_pricing_claim(good)!='educational_example', failures)
    bad_price=(FIXTURES/'broken/official-mobi-pricing.md').read_text()
    fail_if('official Mobi pricing fixture not detected', classify_pricing_claim(bad_price)!='official_pricing', failures)
    bad_offer=(FIXTURES/'broken/unapproved-free-estimate.md').read_text().lower()
    fail_if('free-estimate fixture not detected', 'free estimate' not in bad_offer or 'guaranteed' not in bad_offer, failures)
    bad_state=(FIXTURES/'broken/draft-publication-state.html').read_text().lower()
    fail_if('broken draft fixture not detected', not ('published:' in bad_state and 'index, follow' in bad_state and 'not navigation' in bad_state), failures)

    missing=[]
    for w in REQUIRED_WIDTHS:
        for section in ['hero','body','table','cta','footer']:
            if not (SCREENSHOT_DIR/f'{w}-{section}.png').exists(): missing.append(f'{w}-{section}')
    fail_if('missing responsive visual artifacts: '+','.join(missing[:12]), bool(missing), failures)
    policy=json.loads((BLOG/'automation/publication-policy.json').read_text())
    fail_if('autopublish unexpectedly enabled', policy.get('autopublish_enabled'), failures)
    fail_if('kill switch unexpectedly off', not policy.get('kill_switch'), failures)
    result={'status':'ok' if not failures else 'failed','failures':failures,'checked_pages':[str(p) for p in PAGES if p.exists()],'canonical_articles':[m['id'] for m in metas],'published_articles':[m['id'] for m in published]}
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if not failures else 1)
if __name__=='__main__': main()
