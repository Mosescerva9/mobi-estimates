#!/usr/bin/env python3
"""Shared templates for the Mobi Estimates static site.

Head/SEO, header/nav, footer, mobile conversion bar, icons and reusable
content components. Values come from config.py (single source of truth).
Run the build via generate.py.
"""
import os
from config import *  # noqa: F401,F403  (centralized site configuration)

OUT = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# Icons (Heroicons-style, 24x24 outline). Stored as inner markup.
# --------------------------------------------------------------------------
ICONS = {
    "calculator": '<rect x="4" y="2.75" width="16" height="18.5" rx="2.5"/><path d="M8 7h8M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15v3.5M8 18.5h4"/>',
    "ruler": '<path d="M3.5 8.5l5-5 12 12-5 5z"/><path d="M7 8l1.5 1.5M9.5 5.5L11 7M12 11l1.5 1.5M14.5 8.5L16 10"/>',
    "clipboard-check": '<path d="M9 4.5h6M9 4.5a1.5 1.5 0 011.5-1.5h3A1.5 1.5 0 0115 4.5M9 4.5H7.5A1.5 1.5 0 006 6v13.5A1.5 1.5 0 007.5 21h9a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H15"/><path d="M9.5 13.5l2 2 3.5-4"/>',
    "doc-search": '<path d="M13.5 3.5H7A1.5 1.5 0 005.5 5v14A1.5 1.5 0 007 20.5h10A1.5 1.5 0 0018.5 19V8.5z"/><path d="M13.5 3.5V8.5h5"/><circle cx="11" cy="13" r="2.2"/><path d="M12.6 14.6L14.5 16.5"/>',
    "layers": '<path d="M12 3.5l8.5 4.5L12 12.5 3.5 8z"/><path d="M3.5 12l8.5 4.5L20.5 12M3.5 16l8.5 4.5L20.5 16"/>',
    "scale": '<path d="M12 3.5v17M7 6.5h10M5 7l-2.5 6h5zM19 7l-2.5 6h5z"/><path d="M2.5 13a2.5 2.5 0 005 0M16.5 13a2.5 2.5 0 005 0M8 20.5h8"/>',
    "adjust": '<path d="M5 7h9M18 7h1M5 12h1M10 12h9M5 17h6M15 17h4"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="13" cy="17" r="2"/>',
    "refresh": '<path d="M4.5 9a7.5 7.5 0 0112.8-3.3L20 8M20 4.5V8h-3.5"/><path d="M19.5 15a7.5 7.5 0 01-12.8 3.3L4 16M4 19.5V16h3.5"/>',
    "list-check": '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 5.5l1 1 1.5-2M4 11.5l1 1 1.5-2M4 17.5l1 1 1.5-2"/>',
    "handshake": '<path d="M3 10.5l3-3 4 1 2-1.5 2 1.5 4-1 3 3"/><path d="M6 7.5V15a2 2 0 002 2l1.5-1.5 1.5 1.5 1.5-1.5 1.5 1.5a2 2 0 002-2V7.5"/><path d="M9.5 13l1.5 1.5"/>',
    "users": '<circle cx="9" cy="8" r="3"/><path d="M3.5 19a5.5 5.5 0 0111 0M16 6.5a2.8 2.8 0 010 5.5M16.5 14.5a5.5 5.5 0 014 4.5"/>',
    "bolt": '<path d="M13 2.5L4.5 13.5H11l-1 8 8.5-11H12z"/>',
    "shield": '<path d="M12 3l7.5 3v5.5c0 4.5-3 7.8-7.5 9.5C7.5 18.3 4.5 15 4.5 10.5V6z"/><path d="M9 11.5l2 2 3.5-4"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "building": '<path d="M4.5 21V5a1.5 1.5 0 011.5-1.5h7A1.5 1.5 0 0114.5 5v16M14.5 9h3.5A1.5 1.5 0 0119.5 10.5V21M3 21h18"/><path d="M7.5 7h3.5M7.5 11h3.5M7.5 15h3.5"/>',
    "building2": '<path d="M3 21h18M5 21V4.5h9V21M14 21V9h5v12"/><path d="M8 8h3M8 12h3M8 16h3M16 12h1M16 16h1"/>',
    "home": '<path d="M3.5 11.5L12 4l8.5 7.5"/><path d="M5.5 10v10.5h13V10"/><path d="M9.5 20.5V14h5v6.5"/>',
    "truck": '<path d="M2.5 6.5h11v9h-11z"/><path d="M13.5 9.5h4l3 3v3h-7z"/><circle cx="6.5" cy="17.5" r="1.8"/><circle cx="17" cy="17.5" r="1.8"/>',
    "wrench": '<path d="M14.5 6.5a3.5 3.5 0 01-4.6 4.6l-5.4 5.4a2 2 0 002.8 2.8l5.4-5.4a3.5 3.5 0 014.6-4.6l-2.3 2.3-2-2z"/>',
    "cube": '<path d="M12 2.8l8 4.4v9.6l-8 4.4-8-4.4V7.2z"/><path d="M4 7.2l8 4.4 8-4.4M12 21.2v-9.6"/>',
    "fire": '<path d="M12 3s4.5 3.5 4.5 8a4.5 4.5 0 01-9 0c0-1.5.7-2.7.7-2.7S9 11 10 11c0-3 2-5 2-8z"/>',
    "store": '<path d="M4 9.5L5 4.5h14l1 5M4 9.5h16M4 9.5v10.5h16V9.5"/><path d="M4 9.5a2.2 2.2 0 004 0 2.2 2.2 0 004 0 2.2 2.2 0 004 0 2.2 2.2 0 004 0M9 20v-5h6v5"/>',
    "bed": '<path d="M3 7v12M3 11h13a4 4 0 014 4v4M3 19h18M3 14h18"/><circle cx="7" cy="9.5" r="1.5"/>',
    "cross": '<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M12 8v8M8 12h8"/>',
    "cap": '<path d="M12 4L2.5 8.5 12 13l9.5-4.5z"/><path d="M6 10.5V15c0 1.5 2.7 3 6 3s6-1.5 6-3v-4.5M21.5 8.5V13"/>',
    "flag": '<path d="M5 21V4M5 4h11l-2 3 2 3H5"/>',
    "hammer": '<path d="M14 6l4 4M16 4l4 4-2 2-4-4z"/><path d="M14.5 9.5L6 18a2 2 0 11-2-2l8.5-8.5"/>',
    "upload": '<path d="M12 15.5V4.5M8 8l4-4 4 4"/><path d="M4.5 14v4A1.5 1.5 0 006 19.5h12a1.5 1.5 0 001.5-1.5v-4"/>',
    "phone": '<path d="M4.5 5.5c0 8 6 14 14 14l1.5-3-4-2-1.5 1.5a11 11 0 01-4.5-4.5L11.5 9.5l-2-4z"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3.5 6.5l8.5 6 8.5-6"/>',
    "pin": '<path d="M12 21s6-5.3 6-10.5A6 6 0 006 10.5C6 15.7 12 21 12 21z"/><circle cx="12" cy="10.5" r="2.2"/>',
    "lock": '<rect x="4.5" y="10" width="15" height="10.5" rx="2"/><path d="M8 10V7a4 4 0 018 0v3"/><circle cx="12" cy="15" r="1.3"/>',
    "chart": '<path d="M4 4v16h16"/><path d="M8 16v-4M12 16V8M16 16v-6"/>',
    "sparkles": '<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/><path d="M18.5 14.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7"/>',
    "check-circle": '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 12.5l2.5 2.5 4.5-5"/>',
    "x-circle": '<circle cx="12" cy="12" r="8.5"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "minus": '<path d="M6 12h12"/>',
    "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "arrow-ur": '<path d="M7 17L17 7M9 7h8v8"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "dollar": '<circle cx="12" cy="12" r="8.5"/><path d="M14.5 9c-.5-1-1.5-1.5-2.5-1.5-1.4 0-2.5.8-2.5 2s1 1.6 2.5 2 2.5 1 2.5 2.2-1.1 2-2.5 2c-1.2 0-2.2-.6-2.6-1.6M12 6v1.5M12 16.5V18"/>',
    "briefcase": '<rect x="3" y="7.5" width="18" height="12" rx="2"/><path d="M8.5 7.5V6a2 2 0 012-2h3a2 2 0 012 2v1.5M3 12.5h18"/>',
    "beaker": '<path d="M9 3.5h6M10 3.5v6L5.5 18a2 2 0 001.8 3h9.4a2 2 0 001.8-3L14 9.5v-6"/><path d="M7.5 14h9"/>',
    "globe": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.4 2.5 14.6 0 17M12 3.5c-2.5 2.4-2.5 14.6 0 17"/>',
    "doc-text": '<path d="M13.5 3.5H7A1.5 1.5 0 005.5 5v14A1.5 1.5 0 007 20.5h10A1.5 1.5 0 0018.5 19V8.5z"/><path d="M13.5 3.5V8.5h5M8.5 12.5h7M8.5 16h5"/>',
    "puzzle": '<path d="M9 4.5a1.5 1.5 0 013 0c0 .8 1 1 1.5 1H16v2.5c0 .5.2 1.5 1 1.5a1.5 1.5 0 010 3c-.8 0-1 1-1 1.5V19h-3c-.5 0-1.5.2-1.5 1a1.5 1.5 0 01-3 0c0-.8-1-1-1.5-1H4v-3.5c0-.5-.2-1.5-1-1.5"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 9.5h17M8 3v4M16 3v4"/>',
    "rocket": '<path d="M5 15c-1.5 1-2 4-2 4s3-.5 4-2M14.5 4.5C9 7 7 12 7 14l3 3c2 0 7-2 9.5-7.5C20.5 7 20 4 20 4s-3-.5-5.5.5z"/><circle cx="14.5" cy="9.5" r="1.5"/>',
}


def icon(name, cls=""):
    inner = ICONS.get(name, "")
    c = ' class="%s"' % cls if cls else ""
    return ('<svg%s width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" '
            'aria-hidden="true">%s</svg>') % (c, inner)


# --------------------------------------------------------------------------
# Navigation model
# --------------------------------------------------------------------------
SERVICES_MENU = [
    ("quantity-takeoffs.html", "doc-search", "Quantity Takeoffs", "Measured quantities from your drawings"),
    ("construction-cost-estimating.html", "calculator", "Construction Cost Estimates", "Labor, material, equipment & sub costs"),
    ("general-contractor-estimating.html", "building2", "GC & Multi-Trade", "Full-project, multi-trade estimates"),
    ("subcontractor-estimating.html", "wrench", "Subcontractor Estimating", "Trade-specific takeoffs & pricing"),
    ("overflow-estimating.html", "refresh", "Overflow Estimating", "Extra capacity when bids pile up"),
    ("services.html", "layers", "All Services", "Browse the full service list"),
]

NAV = [
    ("services.html", "Services", "services"),  # has dropdown
    ("pricing.html", "Pricing", "pricing"),
    ("sample-estimate.html", "Sample Estimate", "sample"),
    ("how-it-works.html", "How It Works", "how"),
    ("about.html", "About", "about"),
    ("faq.html", "FAQ", "faq"),
    ("contact.html", "Contact", "contact"),
]


def cta_attr(name):
    """data attribute for analytics-ready click tracking."""
    return ' data-analytics="%s"' % name if name else ""


def btn(label, href, kind="primary", ic=None, size="", cls="", data="", attrs=""):
    sz = " btn-" + size if size else ""
    lead_icon = icon(ic) + " " if ic else ""
    return '<a class="btn btn-%s%s %s" href="%s"%s%s>%s%s</a>' % (
        kind, sz, cls, href, cta_attr(data), (" " + attrs if attrs else ""), lead_icon, label)


def header(active=""):
    links = []
    for href, label, key in NAV:
        if key == "services":
            menu_items = "".join(
                '<a class="menu-item" href="%s"><span class="mi-ic">%s</span>'
                '<span><strong>%s</strong><span>%s</span></span></a>'
                % (h, icon(ic), t, d) for h, ic, t, d in SERVICES_MENU
            )
            links.append(
                '<div class="has-menu">'
                '<a class="nav-link %s" href="%s" aria-haspopup="true">Services %s</a>'
                '<div class="menu-panel" role="menu">%s</div></div>'
                % ("active" if active == key else "", href,
                   icon("chevron-down", "inline-chev"), menu_items)
            )
        else:
            links.append('<a class="nav-link %s" href="%s">%s</a>'
                         % ("active" if active == key else "", href, label))
    nav_links = "".join(links)

    m_services = "".join('<a class="m-link" href="%s">%s</a>' % (h, t)
                         for h, ic, t, d in SERVICES_MENU)
    m_main = "".join('<a class="m-link %s" href="%s">%s</a>'
                     % ("active" if active == key else "", href, label)
                     for href, label, key in NAV if key != "services")

    return '''<header class="site-header">
  <a class="skip-link" href="#main">Skip to content</a>
  <div class="container nav">
    <a class="brand" href="index.html" aria-label="%s home">
      <img src="assets/img/mobi-logo.png" alt="%s" width="170" height="68" fetchpriority="high">
    </a>
    <nav class="nav-links hide-mobile" aria-label="Primary">%s</nav>
    <div class="nav-actions">
      %s
      <button class="nav-toggle" aria-label="Open menu" aria-expanded="false" aria-controls="mobileDrawer">%s</button>
    </div>
  </div>
  <div class="mobile-drawer" id="mobileDrawer">
    <div class="scrim"></div>
    <nav class="panel" aria-label="Mobile">
      <div class="flex items-center" style="justify-content:space-between;margin-bottom:8px">
        <img src="assets/img/mobi-logo.png" alt="%s" style="height:30px">
        <button class="nav-close" aria-label="Close menu">%s</button>
      </div>
      %s
      <div class="m-section">Services</div>
      %s
      <div style="margin-top:auto;padding-top:18px;display:grid;gap:10px">
        %s
      </div>
    </nav>
  </div>
</header>''' % (SITE_NAME, SITE_NAME, nav_links,
                btn(CTA_JOIN[0], CTA_JOIN[1], "primary", "arrow-right", cls="hide-mobile", data="nav_join"),
                icon("menu"), SITE_NAME, icon("x"), m_main, m_services,
                btn(CTA_JOIN[0], CTA_JOIN[1], "primary", "arrow-right", cls="btn-block", data="drawer_join"))


def footer():
    services_links = "".join('<a href="%s">%s</a><br>' % (h, t)
                             for h, ic, t, d in SERVICES_MENU[:-1])
    # Email + (phone only if verified) + service area
    contact_rows = '<a href="mailto:%s" style="display:flex;gap:9px;align-items:center" data-analytics="email_click">%s %s</a>' % (
        EMAIL, icon("mail"), EMAIL)
    if PHONE and PHONE_HREF:
        contact_rows += '<a href="tel:%s" style="display:flex;gap:9px;align-items:center" data-analytics="phone_click">%s %s</a>' % (
            PHONE_HREF, icon("phone"), PHONE)
    contact_rows += '<span style="display:flex;gap:9px;align-items:center;color:#9fb1cc">%s Serving the United States, nationwide</span>' % icon("pin")

    return '''<footer class="site-footer">
  <div class="container">
    <div class="footer-grid">
      <div>
        <img src="assets/img/mobi-logo-white.png" alt="%s" style="height:36px;margin-bottom:18px">
        <p style="color:#9fb1cc;max-width:34ch;font-size:.94rem;line-height:1.7">
          Construction estimating capacity for supported scopes — per-project pricing or ongoing monthly support, nationwide.</p>
        <div style="margin-top:18px;display:grid;gap:8px;font-size:.92rem">%s</div>
      </div>
      <div>
        <h4>Services</h4>
        %s
      </div>
      <div>
        <h4>Company</h4>
        <a href="pricing.html">Pricing</a><br>
        <a href="sample-estimate.html">Sample Estimate</a><br>
        <a href="monthly-estimating-support.html">Monthly Support</a><br>
        <a href="how-it-works.html">How It Works</a><br>
        <a href="about.html">About</a><br>
        <a href="faq.html">FAQ</a><br>
        <a href="contact.html">Contact</a>
      </div>
      <div>
        <h4>Get Started</h4>
        <a href="upload-plans.html">Upload Plans</a><br>
        <a href="capacity-plan.html">Monthly Capacity Plan</a><br>
        <a href="sample-estimate.html">Sample Estimate</a>
        <div style="margin-top:18px">
          %s
        </div>
      </div>
    </div>
    <div class="footer-bottom">
      <span>&copy; <span id="year">2026</span> %s. All rights reserved.</span>
      <span style="display:flex;gap:18px;flex-wrap:wrap">
        <a href="privacy.html">Privacy Policy</a>
        <a href="terms.html">Terms of Service</a>
        <a href="disclaimer.html">Estimating Disclaimer</a>
      </span>
    </div>
  </div>
</footer>''' % (SITE_NAME, contact_rows, services_links,
                btn(CTA_JOIN[0], CTA_JOIN[1], "primary", "arrow-right", cls="btn-block", data="footer_join"),
                SITE_NAME)


def mobile_bar():
    return '''<div class="mobile-cta-bar" id="mobileCtaBar">
  <a class="btn btn-primary" href="%s" data-analytics="mbar_join">%s %s</a>
  <button class="mbar-close" aria-label="Dismiss quick actions">%s</button>
</div>''' % (CTA_JOIN[1], icon("arrow-right"), CTA_JOIN[0], icon("x"))


def head_config():
    import json
    cfg = '<script>window.MOBI=%s;</script>' % json.dumps({
        "endpoint": FORM_ENDPOINT,
        "leadEndpoint": LEAD_CAPTURE_ENDPOINT,
        "email": EMAIL,
    })
    if not ANALYTICS_ID:
        return cfg
    ga = ('<script async src="https://www.googletagmanager.com/gtag/js?id=%s"></script>'
          '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}'
          'gtag("js",new Date());gtag("config","%s");</script>') % (ANALYTICS_ID, ANALYTICS_ID)
    return cfg + ga


def org_schema():
    import json
    data = {
        "@context": "https://schema.org",
        "@type": "ProfessionalService",
        "name": SITE_NAME,
        "description": "Outsourced construction estimating, quantity takeoffs, cost estimates and bid preparation for contractors nationwide.",
        "url": CANONICAL_BASE + "/",
        "email": EMAIL,
        "areaServed": "US",
        "serviceType": "Construction estimating and quantity takeoff services",
    }
    if PHONE:
        data["telephone"] = PHONE
    return '<script type="application/ld+json">%s</script>' % json.dumps(data)


def page(filename, title, description, body, active="", extra_head="",
         schema_extra="", og_image="assets/img/hero-structure.jpg", robots="index, follow"):
    canonical = CANONICAL_BASE + "/" + ("" if filename == "index.html" else filename)
    og_url = CANONICAL_BASE + "/" + og_image
    html = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>
<meta name="description" content="%s">
<meta name="robots" content="%s">
<link rel="canonical" href="%s">
<meta property="og:title" content="%s">
<meta property="og:description" content="%s">
<meta property="og:type" content="website">
<meta property="og:url" content="%s">
<meta property="og:image" content="%s">
<meta property="og:site_name" content="%s">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/png" sizes="32x32" href="assets/img/favicon-32.png">
<link rel="apple-touch-icon" href="assets/img/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:ital,wght@0,400;0,500;0,600;0,700;0,800;1,500;1,600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="assets/css/styles.css?v=%s">
%s
%s
%s
%s
</head>
<body>
%s
<main id="main">
%s
</main>
%s
%s
<script src="assets/js/site.js?v=%s" defer></script>
</body>
</html>''' % (title, description, robots, canonical, title, description, canonical, og_url, SITE_NAME,
              ASSET_VER, head_config(), org_schema(), schema_extra, extra_head,
              header(active), body, footer(), mobile_bar(), ASSET_VER)
    path = os.path.join(OUT, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return filename


# --------------------------------------------------------------------------
# Reusable content components
# --------------------------------------------------------------------------
def service_card(href, ic, title, desc, delay=0, cta="Learn more"):
    return '''<a class="card card-hover reveal" data-delay="%d" href="%s" style="display:block">
  <div class="icon-box">%s</div>
  <h3>%s</h3>
  <p>%s</p>
  <span class="tag" style="margin-top:16px">%s %s</span>
</a>''' % (delay, href, icon(ic), title, desc, cta, icon("arrow-ur"))


def feature_item(ic, title, desc, delay=0):
    return '''<div class="feature reveal" data-delay="%d">
  <div class="fi">%s</div>
  <div><h3>%s</h3><p>%s</p></div>
</div>''' % (delay, icon(ic), title, desc)


def check_list(items, cls=""):
    lis = "".join('<li>%s<span>%s</span></li>' % (icon("check-circle"), i) for i in items)
    return '<ul class="check-list %s">%s</ul>' % (cls, lis)


def pain_card(ic, text, delay=0):
    return '''<div class="card reveal pain-card" data-delay="%d">
  <span class="pain-ic">%s</span><p>%s</p>
</div>''' % (delay, icon(ic), text)


def project_card(plan, delay=0):
    """One-time Pay Per Project card ($599, not a subscription)."""
    feats = check_list(plan["features"])
    period = plan.get("period")
    suffix = '<span class="per"> %s</span>' % period if period else ""
    return '''<div class="card pkg %s reveal" data-delay="%d">
  <span class="pkg-badge">One-time option</span>
  <h3>%s</h3>
  <div class="pkg-price">%s%s</div>
  <p class="pkg-sub">%s</p>
  %s
  %s
</div>''' % ("featured" if plan.get("featured") else "", delay, plan["name"], plan["price"], suffix,
             plan["best_for"], feats,
             btn(plan["cta"], plan["href"], "primary",
                 cls="btn-block", data="project_plan_%s" % plan["id"]))


def monthly_card(plan, delay=0):
    """Monthly subscription card showing the approved regular price."""
    feats = check_list(plan["features"])
    badge = '<span class="pkg-badge">%s</span>' % plan["badge"] if plan.get("badge") else ""
    price = '<div class="pkg-price">%s<span class="per"> %s</span></div>' % (plan["price"], plan["period"])
    return '''<div class="card pkg %s reveal" data-delay="%d">
  %s
  <h3>%s</h3>
  %s
  <p class="pkg-sub">%s</p>
  %s
  %s
</div>''' % ("featured" if plan.get("featured") else "", delay, badge, plan["name"], price,
             plan["best_for"], feats,
             btn(plan["cta"], plan["href"], "primary" if plan.get("featured") else "outline",
                 cls="btn-block", data="monthly_plan_%s" % plan["id"]))


def cta_band(heading="Ready to add estimating capacity?",
             sub="Compare our monthly plans and the one-time Pay Per Project option, then choose what fits your business.",
             primary=None, secondary=None):
    primary = primary or (CTA_PRIMARY[0], CTA_PRIMARY[1], "arrow-right")
    secondary = secondary or (CTA_PRICING[0], CTA_PRICING[1])
    return '''<section class="section">
  <div class="container">
    <div class="cta-band reveal">
      <div class="blueprint"></div>
      <div style="position:relative;max-width:660px">
        <span class="eyebrow on-dark">Get started</span>
        <h2 style="margin-top:14px">%s</h2>
        <p class="lead" style="color:#cdddf7;margin-top:14px">%s</p>
        <div class="flex gap-3 wrap" style="margin-top:26px">
          %s
          %s
        </div>
      </div>
    </div>
  </div>
</section>''' % (heading, sub,
                 btn(primary[0], primary[1], "primary", primary[2] if len(primary) > 2 else "upload", data="ctaband_primary"),
                 btn(secondary[0], secondary[1], "ghost", data="ctaband_secondary"))


def page_hero(eyebrow, title, subtitle, crumbs):
    crumb_html = '<a href="index.html">Home</a>'
    for label, href in crumbs:
        if href:
            crumb_html += '<span class="sep">/</span><a href="%s">%s</a>' % (href, label)
        else:
            crumb_html += '<span class="sep">/</span><span>%s</span>' % label
    return '''<section class="page-hero">
  <div class="blueprint"></div><div class="glow"></div>
  <div class="container" style="padding-block:clamp(48px,7vw,86px)">
    <nav class="breadcrumb reveal" aria-label="Breadcrumb">%s</nav>
    <span class="eyebrow on-dark reveal">%s</span>
    <h1 class="reveal" data-delay="60" style="margin-top:16px;max-width:20ch">%s</h1>
    <p class="lead reveal" data-delay="120" style="color:#cdddf7;margin-top:18px;max-width:64ch">%s</p>
  </div>
</section>''' % (crumb_html, eyebrow, title, subtitle)


def faq_schema(items):
    import json
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in items
        ],
    }
    return '<script type="application/ld+json">%s</script>' % json.dumps(data)
