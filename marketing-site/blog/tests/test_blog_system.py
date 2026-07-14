#!/usr/bin/env python3
from __future__ import annotations
import json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PAGES=[ROOT/'blog/index.html', ROOT/'blog/construction-estimating-mistakes/index.html', ROOT/'blog/construction-markup-vs-margin/index.html', ROOT/'blog/editorial-standards/index.html']
ARTICLE=ROOT/'blog/construction-estimating-mistakes/index.html'
CSS=ROOT/'blog/assets/blog.css'
SITEMAP=ROOT/'blog/public-sitemap-preview.xml'
SCREENSHOT_DIR=Path('/home/hermes/Documents/Obsidian Vault/Mobi Estimates/13 Marketing/SEO Blog/screenshots/blog-system')
REQUIRED_WIDTHS=[320,360,375,390,430,768,1024,1440]

def fail_if(name, cond, failures):
    if cond: failures.append(name)

def main():
    failures=[]
    css=CSS.read_text()
    for p in PAGES:
        html=p.read_text()
        fail_if(f'{p}: missing noindex', 'noindex, nofollow' not in html, failures)
        fail_if(f'{p}: h1 count not one', html.count('<h1') != 1, failures)
        fail_if(f'{p}: hash placeholder link', '<a href="#"' in html, failures)
    a=ARTICLE.read_text()
    fail_if('H1 may clip: mobile hero lacks safe-area padding', 'env(safe-area-inset-top)' not in css, failures)
    fail_if('H1 may clip: header offset not defined', '--header-offset:76px' not in css, failures)
    fail_if('H1 may clip: mobile H1 rule missing', '@media(max-width:640px)' not in css or '.blog-hero h1' not in css, failures)
    fail_if('mobile breadcrumb behavior not intentional', '.blog-breadcrumb{display:none}' not in css or '.mobile-back{display:inline-block}' not in css, failures)
    fail_if('mobile process steps not readable at 320/360', '@media(max-width:360px)' not in css or '.process-steps{grid-template-columns:1fr}' not in css, failures)
    fail_if('process graphic missing', 'process-steps' not in a, failures)
    fail_if('internal process commentary visible', 'not navigation' in a.lower(), failures)
    fail_if('draft displays false public published label', 'Published:' in a, failures)
    fail_if('draft missing draft badge/planned publication handling', 'Draft preview' not in a, failures)
    fail_if('updated date visible in draft/equal-first-launch state', 'Updated:' in a, failures)
    fail_if('estimator review claim present', 'Reviewed by an estimator' in a or 'expert reviewed' in a.lower(), failures)
    fail_if('editorial attribution missing', 'Prepared by Mobi Estimates editorial team' not in a, failures)
    fail_if('draft sitemap includes draft URLs', '<url><loc>' in SITEMAP.read_text(), failures)
    fail_if('future related post creates live link', 'href="../construction-markup-vs-margin/"' in a and 'Coming soon' in a, failures)
    # Visual-regression artifacts for every required width must exist after capture.
    missing=[]
    for w in REQUIRED_WIDTHS:
        for section in ['hero','body','table','cta','footer']:
            if not (SCREENSHOT_DIR/f'{w}-{section}.png').exists(): missing.append(f'{w}-{section}')
    fail_if('missing responsive visual artifacts: '+','.join(missing[:12]), bool(missing), failures)
    result={'status':'ok' if not failures else 'failed','failures':failures,'checked_pages':[str(p) for p in PAGES]}
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if not failures else 1)
if __name__=='__main__': main()
