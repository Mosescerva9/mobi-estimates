#!/usr/bin/env python3
from __future__ import annotations
import html, json, re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BLOG = ROOT / 'blog'
CONTENT = BLOG / 'content'
PUBLIC_BASE = 'https://mobiestimates.com/blog/'
POLICY_PATH = BLOG / 'automation' / 'publication-policy.json'
try:
    POLICY = json.loads(POLICY_PATH.read_text())
except Exception:
    POLICY = {}
PREVIEW_BASE = POLICY.get('preview_base_url', PUBLIC_BASE)


def parse_doc(path: Path) -> tuple[dict, str]:
    raw = path.read_text()
    m = re.match(r'^---json\n(.*?)\n---\n(.*)$', raw, re.S)
    if not m:
        raise ValueError(f'missing canonical ---json front matter: {path}')
    meta = json.loads(m.group(1))
    meta['_source'] = str(path.relative_to(ROOT))
    meta['content'] = path.name
    meta['draft'] = meta.get('status') != 'published'
    meta['noindex'] = bool(meta.get('noindex', meta['draft']))
    return meta, m.group(2).strip()


def load_posts() -> list[dict]:
    posts = []
    for p in sorted(CONTENT.glob('*.md')):
        meta, _ = parse_doc(p)
        posts.append(meta)
    return sorted(posts, key=lambda x: (x.get('planned_publish_at') or '9999', x['slug']))

POSTS = load_posts()
POST_BY_SLUG = {p['slug']: p for p in POSTS}


def slugify(s: str) -> str:
    s = re.sub(r'[^a-z0-9\s-]', '', s.lower())
    return re.sub(r'[\s-]+', '-', s).strip('-')


def inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', s)
    s = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'\*(.*?)\*', r'<em>\1</em>', s)
    s = re.sub(r'`(.*?)`', r'<code>\1</code>', s)
    return s


def render_table(lines: list[str]) -> str:
    raw_rows = [ln.strip().strip('|').split('|') for ln in lines if not re.match(r'^\|\s*:?-', ln)]
    rows = [[cell.strip() for cell in row] for row in raw_rows]
    if not rows: return ''
    headers = rows[0]
    cls = 'blog-table estimate-table' if headers[:3] == ['Estimate component', 'Example amount', 'Notes'] else 'blog-table'
    out = [f'<div class="blog-table-wrap"><table class="{cls}">']
    out.append('<thead><tr>' + ''.join(f'<th>{inline(h)}</th>' for h in headers) + '</tr></thead><tbody>')
    for row in rows[1:]:
        cells=[]
        for i,c in enumerate(row):
            label = headers[i] if i < len(headers) else ''
            cells.append(f'<td data-label="{html.escape(label)}">{inline(c)}</td>')
        out.append('<tr>' + ''.join(cells) + '</tr>')
    out.append('</tbody></table></div>')
    return ''.join(out)


def render_markdown(md: str):
    md = re.sub(r'^# .+\n\n?', '', md, count=1, flags=re.M)
    parts=[]; toc=[]; table=[]; ul=False; ol=False; checks=False
    def close_lists():
        nonlocal ul, ol, checks
        if ul: parts.append('</ul>'); ul=False
        if ol: parts.append('</ol>'); ol=False
        if checks: parts.append('</ul>'); checks=False
    def flush_table():
        nonlocal table
        if table:
            close_lists(); parts.append(render_table(table)); table=[]
    for line in md.splitlines():
        if line.startswith('|'):
            table.append(line); continue
        flush_table()
        if not line.strip(): continue
        if line.startswith('## '):
            close_lists(); title=line[3:].strip(); hid=slugify(title); toc.append((2,title,hid)); parts.append(f'<h2 id="{hid}">{inline(title)}</h2>')
        elif line.startswith('### '):
            close_lists(); title=line[4:].strip(); hid=slugify(title); toc.append((3,title,hid)); parts.append(f'<h3 id="{hid}">{inline(title)}</h3>')
        elif line.startswith('- [ ] '):
            if not checks:
                close_lists(); parts.append('<ul class="check-grid">'); checks=True
            parts.append(f'<li><span class="box" aria-hidden="true"></span><span>{inline(line[6:])}</span></li>')
        elif line.startswith('- '):
            if not ul:
                close_lists(); parts.append('<ul>'); ul=True
            parts.append(f'<li>{inline(line[2:])}</li>')
        elif re.match(r'^\d+\. ', line):
            if not ol:
                close_lists(); parts.append('<ol>'); ol=True
            item_text = re.sub(r'^\d+\. ', '', line)
            parts.append(f'<li>{inline(item_text)}</li>')
        elif line.startswith('> '):
            close_lists(); parts.append(f'<aside class="note-callout">{inline(line[2:])}</aside>')
        else:
            close_lists(); parts.append(f'<p>{inline(line)}</p>')
    flush_table(); close_lists()
    return ''.join(parts), toc


def rel_prefix(depth: int) -> str: return '../' * depth


def robots(meta): return 'noindex, nofollow' if meta.get('draft') or meta.get('noindex') else 'index, follow'


def head(meta, depth=1, article=False):
    rp=rel_prefix(depth)
    rb=robots(meta)
    canonical = '' if rb.startswith('noindex') else f'<link rel="canonical" href="{html.escape(meta.get("canonical_url") or PUBLIC_BASE + meta.get("slug", "") + "/")}">'
    base_for_og = PREVIEW_BASE if meta.get('draft') or meta.get('noindex') else PUBLIC_BASE
    og_image = f'{base_for_og}{meta.get("slug", "")}/{Path(meta.get("og_image", "")).name}' if meta.get('og_image') else 'https://mobiestimates.com/assets/img/hero-structure.jpg'
    schema=''
    if article:
        data={'@context':'https://schema.org','@type':meta.get('schema_type','Article'),'headline':meta['title'],'description':meta['meta_description'],'author':{'@type':'Organization','name':meta['editorial_attribution']},'publisher':{'@type':'Organization','name':'Mobi Estimates'}}
        if meta.get('published_at') and not meta.get('draft'): data['datePublished']=meta['published_at']
        if meta.get('updated_at') and meta.get('updated_at') != meta.get('published_at'): data['dateModified']=meta['updated_at']
        schema=f'<script type="application/ld+json">{json.dumps(data,sort_keys=True)}</script>'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><title>{html.escape(meta['seo_title'])}</title><meta name="description" content="{html.escape(meta['meta_description'])}"><meta name="robots" content="{rb}">{canonical}<meta property="og:title" content="{html.escape(meta['title'])}"><meta property="og:description" content="{html.escape(meta['meta_description'])}"><meta property="og:type" content="{'article' if article else 'website'}"><meta property="og:image" content="{og_image}"><meta name="twitter:card" content="summary_large_image"><link rel="icon" type="image/png" sizes="32x32" href="{rp}assets/img/favicon-32.png"><link rel="stylesheet" href="{rp}assets/css/styles.css?v=12"><link rel="stylesheet" href="{rp}blog/assets/blog.css?v=2">{schema}<script>window.MOBI_BLOG_PREVIEW={str(meta.get('draft') or meta.get('noindex')).lower()};</script></head><body>'''


def site_header(depth=1):
    rp=rel_prefix(depth)
    return f'''<header class="site-header"><a class="skip-link" href="#main">Skip to content</a><div class="container nav"><a class="brand" href="{rp}index.html" aria-label="Mobi Estimates home"><img src="{rp}assets/img/mobi-logo.png" alt="Mobi Estimates" width="170" height="68"></a><nav class="nav-links hide-mobile" aria-label="Primary"><a class="nav-link" href="{rp}services.html">Services</a><a class="nav-link active" href="{rp}blog/">Resources</a><a class="nav-link" href="{rp}sample-estimate.html">Sample Estimate</a><a class="nav-link" href="{rp}how-it-works.html">How It Works</a><a class="nav-link" href="{rp}pricing.html">Pricing</a></nav><div class="nav-actions"><a class="btn btn-primary hide-mobile" href="{rp}sample-estimate.html">See Sample</a><button class="nav-toggle" aria-label="Open menu" aria-expanded="false">☰</button></div></div></header>'''


def footer(depth=1):
    rp=rel_prefix(depth)
    return f'''<footer id="site-footer" class="site-footer"><div class="container"><div class="footer-grid"><div><img src="{rp}assets/img/mobi-logo-white.png" alt="Mobi Estimates" style="height:36px;margin-bottom:18px"><p style="color:#9fb1cc;max-width:34ch;font-size:.94rem;line-height:1.7">On-demand construction estimating and workflow support for contractors.</p></div><div><h4>Services</h4><a href="{rp}construction-estimating-services.html">Construction Estimating</a><br><a href="{rp}quantity-takeoffs.html">Quantity Takeoffs</a><br><a href="{rp}general-contractor-estimating.html">GC & Multi-Trade</a></div><div><h4>Company</h4><a href="{rp}sample-estimate.html">Sample Estimate</a><br><a href="{rp}how-it-works.html">How It Works</a><br><a href="{rp}faq.html">FAQ</a></div><div><h4>Get Started</h4><a href="{rp}sample-estimate.html">See a Sample Estimate</a><br><a href="{rp}upload-plans.html">Upload Plans</a></div></div><div class="footer-bottom"><span>&copy; 2026 Mobi Estimates. All rights reserved.</span><span><a href="{rp}privacy.html">Privacy Policy</a> <a href="{rp}terms.html">Terms</a></span></div></div></footer><script src="{rp}assets/js/site.js?v=12" defer></script><script src="{rp}blog/assets/blog-analytics.js" defer></script></body></html>'''


def date_meta(post):
    if post.get('draft'):
        return f'<span class="draft-badge">Draft preview</span>' + (f'<span>Planned publication: {post["planned_publish_at"]}</span>' if post.get('planned_publish_at') else '')
    bits=[]
    if post.get('published_at'): bits.append(f'<span>Published: {post["published_at"]}</span>')
    if post.get('updated_at') and post.get('updated_at') != post.get('published_at'): bits.append(f'<span>Updated: {post["updated_at"]}</span>')
    return ''.join(bits)


def process_graphic():
    return '''<figure class="process-graphic" aria-labelledby="process-title"><figcaption id="process-title">A simple bid-review workflow for catching estimating mistakes before submission.</figcaption><ol class="process-steps"><li><strong>01</strong><span>Review documents</span></li><li><strong>02</strong><span>Build scope</span></li><li><strong>03</strong><span>Price work</span></li><li><strong>04</strong><span>Review bid</span></li></ol></figure>'''


def render_article(post):
    _, md = parse_doc(CONTENT / post['content'])
    body,toc=render_markdown(md)
    toc_html=''.join(f'<a href="#{hid}" class="toc-l{lvl}" data-analytics="toc_click">{html.escape(title)}</a>' for lvl,title,hid in toc if lvl==2 and title!='Sources and further reading')
    related=[]
    for slug in post.get('related_posts',[]):
        other=POST_BY_SLUG.get(slug)
        if not other: continue
        if other.get('draft'):
            related.append(f'<span class="related-card">{html.escape(other["title"])}<em>Coming soon — draft, not linked publicly</em></span>')
        else:
            related.append(f'<a class="related-card" href="../{slug}/" data-analytics="related_click">{html.escape(other["title"])}</a>')
    rel_html=''.join(related) or '<p class="muted">Related articles will appear here as the cluster is published.</p>'
    html_doc=head(post, depth=2, article=True)+site_header(depth=2)+f'''<main id="main"><section class="blog-hero"><div class="container"><a class="mobile-back" href="../">← Resources</a><nav class="blog-breadcrumb" aria-label="Breadcrumb"><a href="../../index.html">Home</a><span>/</span><a href="../">Blog</a><span>/</span><span>{html.escape(post['category'])}</span></nav><span class="eyebrow on-dark">{html.escape(post['category'])}</span><h1>{html.escape(post['title'])}</h1><p class="blog-subtitle">{html.escape(post['excerpt'])}</p><div class="article-meta">{date_meta(post)}<span>{html.escape(post['reading_time'])}</span><span>{html.escape(post['editorial_attribution'])}</span></div>{process_graphic()}</div></section><section class="blog-layout-section"><div class="container blog-layout"><article class="blog-article">{body}<section id="mobi-next-step" class="article-cta"><h2>Want to see what an organized estimate can look like?</h2><p>Review a sample deliverable before making any commitment.</p><p><a class="btn" href="../../sample-estimate.html" data-analytics="sample_cta_click">See a Sample Estimate</a> <a class="btn btn-secondary" href="../../how-it-works.html" data-analytics="learn_cta_click">Learn How Mobi Works</a></p></section><section class="related-reading"><h2>Related reading</h2><div class="related-grid">{rel_html}</div></section></article><aside class="toc-card" aria-label="Table of contents"><strong>In this article</strong>{toc_html}</aside></div></section></main>'''+footer(depth=2)
    out=ROOT/'blog'/post['slug']/'index.html'; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(html_doc)
    img=BLOG/post.get('featured_image','')
    if img.exists(): shutil.copy2(img, out.parent/img.name)


def render_archive():
    meta={'seo_title':'Mobi Estimates Blog | Construction Estimating Resources','title':'Mobi Estimates Blog','meta_description':'Practical estimating, bidding, and construction-business guides from Mobi Estimates.','slug':'','draft':True,'noindex':True}
    cards=[]
    for p in POSTS:
        href=f'{p["slug"]}/'
        cards.append(f'<article class="blog-card"><span class="tag">{html.escape(p["category"])}</span><h2><a href="{href}" data-analytics="archive_click">{html.escape(p["title"])}</a></h2><p>{html.escape(p["excerpt"])}</p><div class="card-meta">{date_meta(p)}<span>{p["reading_time"]}</span></div></article>')
    html_doc=head(meta, depth=1)+site_header(depth=1)+f'''<main id="main"><section class="blog-archive-hero"><div class="container"><span class="draft-badge">Draft preview</span><h1>Construction estimating resources</h1><p class="lead">Useful estimating, pricing, bidding, and contractor-business guides. Draft articles are visible here only for internal preview.</p></div></section><section class="section-tight"><div class="container blog-card-grid">{''.join(cards) or '<p>No articles yet.</p>'}</div></section></main>'''+footer(depth=1)
    (ROOT/'blog/index.html').write_text(html_doc)


def render_editorial():
    meta={'seo_title':'Mobi Editorial Standards | Draft','title':'Mobi Editorial Standards','meta_description':'How Mobi researches, reviews, corrects, and updates construction estimating content.','slug':'editorial-standards','draft':True,'noindex':True}
    body='''<h1>Mobi Editorial Standards</h1><p>This draft page explains how Mobi Estimates prepares construction estimating content before publication.</p><h2>Research and sourcing</h2><p>We prioritize official sources, neutral industry resources, product documentation, and clearly attributed third-party sources. Search and competitor research informs coverage but should not be copied.</p><h2>Product and offer claims</h2><p>Mobi product claims, pricing, promotions, turnaround times, and guarantees require canonical documentation and approval before publication.</p><h2>Industry review</h2><p>Some articles may need review by an experienced estimator, general contractor, construction accountant, attorney, insurer, or other qualified professional. We do not claim professional review unless a real reviewer completes it.</p><h2>AI assistance</h2><p>AI tools may assist drafting and formatting. Factual claims, calculations, sources, product claims, and publication state must be validated before release.</p><h2>Corrections and updates</h2><p>We correct material errors when found. Updated dates should be used for meaningful post-publication revisions, not routine draft edits or first launch.</p>'''
    html_doc=head(meta, depth=2)+site_header(depth=2)+f'<main id="main"><section class="blog-layout-section"><div class="container"><article class="blog-article standards-page"><span class="draft-badge">Draft preview</span>{body}</article></div></section></main>'+footer(depth=2)
    out=ROOT/'blog/editorial-standards/index.html'; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(html_doc)


def render_public_sitemap_preview():
    urls=[(p.get('canonical_url') or f'{PUBLIC_BASE}{p["slug"]}/') for p in POSTS if not p.get('draft') and not p.get('noindex')]
    (BLOG/'public-sitemap-preview.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + ''.join(f'<url><loc>{html.escape(u)}</loc></url>\n' for u in urls) + '</urlset>\n')
    # generated archive data for inspection; not canonical
    (BLOG/'generated-posts.json').write_text(json.dumps(POSTS, indent=2, sort_keys=True))

for p in POSTS: render_article(p)
render_archive(); render_editorial(); render_public_sitemap_preview()
print('generated', len(POSTS), 'posts from canonical markdown front matter')
