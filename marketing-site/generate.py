#!/usr/bin/env python3
"""Page content + site build for Mobi Estimates. Run: python3 generate.py"""
import os
from build import *  # noqa: F401,F403  (templates) — also re-exports config via build


# ==========================================================================
# Small content helpers
# ==========================================================================
def numbered_item(i, href, ic, title, desc):
    return ('<a class="num-item reveal" href="%s">'
            '<span class="n">%02d</span>'
            '<span class="nc"><h3>%s</h3><p>%s</p></span>'
            '<span class="ni">%s</span></a>') % (href, i, title, desc, icon(ic))


def numbered_list(items):
    rows = "".join(numbered_item(i + 1, h, ic, t, d) for i, (h, ic, t, d) in enumerate(items))
    return '<div class="num-list">%s</div>' % rows


def stats_band(stats):
    cells = "".join(
        '<div class="stat reveal" data-delay="%d"><div class="sv">%s</div><div class="sl">%s</div></div>'
        % (i * 70, v, l) for i, (v, l) in enumerate(stats))
    return '<div class="stats">%s</div>' % cells


def trust_strip():
    items = [
        ("globe", "Nationwide Service"),
        ("layers", "All Construction Trades"),
        ("shield", "Human-Reviewed Estimates"),
        ("lock", "Confidential Project Files"),
        ("refresh", "Per-Project or Monthly"),
    ]
    chips = "".join('<span class="chip">%s %s</span>' % (icon(ic), t) for ic, t in items)
    return '''<section class="section-tight band-alt">
  <div class="container"><div class="trust-strip reveal">%s</div></div>
</section>''' % chips


def comparison_table():
    rows = [
        ("Recruitment required", "Yes", "Varies", "No"),
        ("Payroll and benefits", "Yes", "No", "No"),
        ("Ability to scale during overflow", "Varies", "Varies", "Included"),
        ("Per-project option", "No", "Available", "Available"),
        ("Monthly support", "—", "Varies", "Available"),
        ("Multi-trade capacity", "Varies", "Varies", "Included"),
        ("Standardized quality control", "Varies", "Varies", "Included"),
        ("Saved company workflows", "Yes", "Varies", "Included"),
        ("Flexible service level", "No", "Varies", "Included"),
        ("Coverage when one person is unavailable", "No", "No", "Included"),
    ]

    def cell(v, mobi=False):
        pos = v in ("Yes", "Included", "Available")
        neg = v == "No"
        cls = "pos" if pos else ("neg" if neg else "neu")
        ic = icon("check") if pos else (icon("x-circle") if neg else icon("minus"))
        return '<td class="%s%s" data-label="">%s<span>%s</span></td>' % (
            cls, " mobi" if mobi else "", ic, v)

    body = ""
    for label, a, b, c in rows:
        body += ('<tr><th scope="row">%s</th>%s%s%s</tr>'
                 % (label, cell(a).replace('data-label=""', 'data-label="In-House Estimator"'),
                    cell(b).replace('data-label=""', 'data-label="Independent Freelancer"'),
                    cell(c, True).replace('data-label=""', 'data-label="Mobi Estimates"')))
    return '''<div class="table-wrap reveal">
  <table class="compare-table">
    <thead><tr><th scope="col">Capability</th><th scope="col">In-House Estimator</th><th scope="col">Independent Freelancer</th><th scope="col" class="mobi-col">Mobi Estimates</th></tr></thead>
    <tbody>%s</tbody>
  </table>
</div>
<p class="muted" style="font-size:.85rem;margin-top:14px">Labels are general guidance and vary by company, individual, and arrangement. Mobi is designed to complement your team, not to make blanket claims about every employee or freelancer.</p>''' % body


def deliverables_section():
    items = [
        "Detailed quantity takeoff", "Labor pricing", "Material pricing", "Equipment costs",
        "Trade breakdowns", "CSI division breakdowns", "Marked-up drawings", "Assumptions",
        "Exclusions", "Allowances", "Alternates", "Bid summary", "Excel workbook",
        "PDF estimate", "Revision support",
    ]
    return '''<section class="section band-dark">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow on-dark">What you receive</span>
      <h2 class="mt-2">Everything you need to submit a stronger bid</h2>
    </div>
    <div class="mt-8">%s</div>
  </div>
</section>''' % check_list(items, "cols-3")


def fit_section():
    good = ["Your estimating team is overloaded", "You are declining bidding opportunities",
            "You regularly miss bid deadlines", "You need temporary or ongoing estimating capacity",
            "You are not ready to add another employee", "Your workload changes from month to month",
            "You want to submit more bids consistently", "You need help across several trades or project types"]
    bad = ["You need stamped engineering or architectural design", "You require onsite project supervision",
           "The available project documents do not define the scope", "You expect guaranteed bid awards",
           "You expect unlimited estimates under a fixed subscription",
           "You need work outside the agreed service scope without adjusting capacity"]
    good_li = "".join('<li>%s<span>%s</span></li>' % (icon("check-circle"), g) for g in good)
    bad_li = "".join('<li>%s<span>%s</span></li>' % (icon("x-circle"), b) for b in bad)
    return '''<section class="section">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">Is Mobi a fit?</span>
      <h2 class="mt-2">Honest about where we help — and where we don't</h2>
    </div>
    <div class="grid cols-2 mt-8" style="gap:24px">
      <div class="card reveal">
        <h3 class="mb-3">Mobi is a strong fit when</h3>
        <ul class="check-list">%s</ul>
      </div>
      <div class="card reveal" data-delay="80">
        <h3 class="mb-3">Mobi may not be the right fit when</h3>
        <ul class="check-list neg-list">%s</ul>
      </div>
    </div>
  </div>
</section>''' % (good_li, bad_li)


def founder_section():
    trust = [
        ("lock", "Confidential file handling"), ("shield", "Human quality-control review"),
        ("doc-text", "Clear assumptions and exclusions"), ("clipboard-check", "Defined scope before work begins"),
        ("layers", "Professional deliverables"), ("dollar", "Transparent pricing"),
        ("refresh", "Flexible monthly service"), ("globe", "Nationwide support"),
    ]
    cards = "".join('<div class="trust-card reveal" data-delay="%d"><span class="ti">%s</span><span>%s</span></div>'
                    % (i * 40, icon(ic), t) for i, (ic, t) in enumerate(trust))
    # Founder identity block only if configured (avoid public placeholders)
    founder_block = ""
    if FOUNDER.get("name"):
        photo = ('<img src="assets/img/%s" alt="%s, founder of %s" style="width:96px;height:96px;border-radius:16px;object-fit:cover">'
                 % (FOUNDER["photo"], FOUNDER["name"], SITE_NAME)) if FOUNDER.get("photo") else ""
        bits = []
        for key, lab in [("construction_experience", ""), ("estimating_experience", ""),
                         ("software", "Software"), ("location", "")]:
            if FOUNDER.get(key):
                bits.append("<li>%s</li>" % FOUNDER[key])
        founder_block = '''<div class="card reveal" style="display:flex;gap:18px;align-items:flex-start">
          %s<div>%s<h3 style="margin-top:6px">%s</h3><p class="muted mt-2">%s</p>%s</div>
        </div>''' % (photo, "", FOUNDER["name"], FOUNDER.get("bio", ""),
                     ("<ul class='check-list mt-3'>" + "".join(bits) + "</ul>") if bits else "")
    else:
        founder_block = "<!-- FOUNDER NOT YET CONFIGURED: set FOUNDER fields in config.py (name, photo, bio, experience, software, location, linkedin) to publish a founder card here. -->"

    return '''<section class="section band-alt">
  <div class="container">
    <div class="grid" style="grid-template-columns:1fr 1fr;gap:40px;align-items:center">
      <div class="reveal">
        <span class="eyebrow">Why Mobi exists</span>
        <h2 class="mt-2 mb-3">Capacity when contractors need it</h2>
        <p class="lead">%s</p>
        %s
      </div>
      <div>
        <div class="trust-grid">%s</div>
      </div>
    </div>
  </div>
</section>''' % (FOUNDER_STATEMENT, founder_block, cards)


def qc_section():
    items = ["Scope coverage review", "Quantity checks", "Formula and calculation checks",
             "Drawing revision verification", "Addenda verification", "Assumption review",
             "Exclusion review", "Deliverable-formatting review"]
    return '''<section class="section">
  <div class="container">
    <div class="grid" style="grid-template-columns:.9fr 1.1fr;gap:48px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">Quality control</span>
        <h2 class="mt-2 mb-3">Every estimate goes through a quality-control review</h2>
        <p class="muted">Estimates are prepared using the plans, specifications, pricing inputs, and project information available at the time. Clients remain responsible for reviewing final estimates and confirming project requirements before submitting a bid or entering a contract.</p>
      </div>
      <div class="card reveal" data-delay="80">%s</div>
    </div>
  </div>
</section>''' % check_list(items, "cols-2")


# Form field helpers ------------------------------------------------------
def field(label, name, ftype="text", required=False, placeholder="", hint="", autocomplete=""):
    req = ' <span class="req">*</span>' if required else ""
    r = " required" if required else ""
    ac = ' autocomplete="%s"' % autocomplete if autocomplete else ""
    ph = ' placeholder="%s"' % placeholder if placeholder else ""
    h = '<span class="hint">%s</span>' % hint if hint else ""
    return ('<div class="field"><label for="%s">%s%s</label>'
            '<input id="%s" name="%s" type="%s"%s%s%s>'
            '<span class="err-msg">Please complete this field.</span>%s</div>'
            % (name, label, req, name, name, ftype, r, ac, ph, h))


def select_field(label, name, options, required=False, hint=""):
    req = ' <span class="req">*</span>' if required else ""
    r = " required" if required else ""
    opts = '<option value="">Select…</option>' + "".join("<option>%s</option>" % o for o in options)
    h = '<span class="hint">%s</span>' % hint if hint else ""
    return ('<div class="field"><label for="%s">%s%s</label>'
            '<select id="%s" name="%s"%s>%s</select>'
            '<span class="err-msg">Please choose an option.</span>%s</div>'
            % (name, label, req, name, name, r, opts, h))


def textarea_field(label, name, required=False, placeholder="", hint=""):
    req = ' <span class="req">*</span>' if required else ""
    r = " required" if required else ""
    ph = ' placeholder="%s"' % placeholder if placeholder else ""
    h = '<span class="hint">%s</span>' % hint if hint else ""
    return ('<div class="field"><label for="%s">%s%s</label>'
            '<textarea id="%s" name="%s"%s%s></textarea>'
            '<span class="err-msg">Please complete this field.</span>%s</div>'
            % (name, label, req, name, name, r, ph, h))


def dropzone(name="files"):
    return ('<div class="field"><label>Project files</label>'
            '<div class="dropzone"><input id="%s" type="file" name="%s" multiple hidden>'
            '<div style="display:grid;gap:6px;place-items:center">%s'
            '<strong class="dz-label">Drop plans, specs &amp; addenda here, or click to browse</strong>'
            '<span class="hint">Accepted: %s</span><span class="hint">%s</span></div></div>'
            '<p class="confidential">%s Your plans and project information will be used only to review, quote, and complete the requested estimating services.</p></div>'
            % (name, name, icon("upload"), ACCEPTED_FILE_TYPES, MAX_FILE_NOTE, icon("lock")))


def form_success(heading, msg, cta_label="Back to home", cta_href="index.html"):
    return ('<div class="form-success"><div class="ok-ic">%s</div>'
            '<h3>%s</h3><p class="muted mt-2" style="max-width:54ch;margin-inline:auto">%s</p>'
            '<div class="mt-6">%s</div></div>'
            % (icon("check"), heading, msg, btn(cta_label, cta_href, "outline")))


# ==========================================================================
# HOME
# ==========================================================================
def home_offer_section():
    return '''<section class="section band-alt" id="free-estimate">
  <div class="container">
    <div class="grid cols-2" style="gap:32px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">First estimate free for new companies</span>
        <h2 class="mt-2">%s</h2>
        <p class="lead mt-3">%s</p>
        <p class="muted mt-3">%s</p>
        <p class="muted mt-2">%s</p>
        <div class="mt-5">%s</div>
      </div>
      <div class="card reveal" data-delay="80">
        <h3>Prefer email? Get updates and start when you are ready.</h3>
        <form data-lead-form novalidate style="margin-top:18px">
          <label class="field"><span>Work email</span><input type="email" name="email" autocomplete="email" maxlength="320" placeholder="you@yourcompany.com" required></label>
          <label aria-hidden="true" style="position:absolute;left:-10000px"><span>Company website</span><input name="company_website" tabindex="-1" autocomplete="off"></label>
          <button class="btn btn-primary btn-block" type="submit" style="margin-top:12px">Get Mobi updates</button>
          <p class="hint mt-3">By submitting, you agree Mobi may contact you about your estimate request and related services. You can unsubscribe at any time. <a href="privacy.html">Privacy policy</a>.</p>
          <p class="hint mt-2" data-lead-status role="status" aria-live="polite"></p>
        </form>
      </div>
    </div>
  </div>
</section>''' % (INTRO_OFFER_HEADLINE, INTRO_OFFER_SUMMARY, INTRO_OFFER_REVIEW,
                  INTRO_OFFER_AFTER,
                  btn(CTA_JOIN[0], CTA_JOIN[1], "primary", "arrow-right", data="offer_start"))


def home_progress_section():
    milestones = [
        ("1", "Submitted", "Your plans and bid date are recorded."),
        ("2", "Qualification & document review", "Mobi confirms the package and supported scope."),
        ("3", "Scope & takeoff", "The estimating team reviews scope and measures the plans."),
        ("4", "Pricing & quality review", "Rates, assumptions, and the workbook are checked."),
        ("5", "Ready after approval", "You are notified only after the human review gate is complete."),
    ]
    cards = "".join(
        '<div class="card reveal" data-delay="%d"><span class="eyebrow">Step %s</span><h3 class="mt-2">%s</h3><p>%s</p></div>'
        % (i * 50, n, title, desc) for i, (n, title, desc) in enumerate(milestones)
    )
    return '''<section class="section">
  <div class="container">
    <div class="center reveal" style="max-width:760px;margin-inline:auto">
      <span class="eyebrow">Customer dashboard</span>
      <h2 class="mt-2">See where your estimate stands</h2>
      <p class="lead mt-3">Track customer-safe milestones and your bid due date without seeing internal AI, provider, or review details.</p>
    </div>
    <div class="grid cols-3 mt-8">%s</div>
  </div>
</section>''' % cards


def home_followup_section():
    return '''<section class="section band-dark">
  <div class="container">
    <div class="grid cols-2" style="gap:36px;align-items:center">
      <div class="reveal">
        <span class="eyebrow on-dark">After the estimate</span>
        <h2 class="mt-2">Stay organized through bid follow-up</h2>
        <p class="lead mt-3" style="color:#cdddf7">Mobi helps track bid due dates, record pending/won/lost outcomes, and organize the next follow-up step after your estimate is prepared.</p>
      </div>
      <div class="card reveal" data-delay="80">
        <h3>More consistent follow-up—not a guaranteed award</h3>
        <p class="mt-3">Competition, qualifications, relationships, schedule, and pricing all affect bid results. Mobi helps keep follow-up work visible and organized; it does not promise that a bid will be won.</p>
      </div>
    </div>
  </div>
</section>'''


def build_home():
    # Services (8) — numbered list with outcome-focused descriptions
    services = numbered_list([
        ("quantity-takeoffs.html", "doc-search", "Quantity Takeoffs",
         "Measured quantities straight from your drawings — so subs and GCs can price faster and bid more."),
        ("construction-cost-estimating.html", "calculator", "Construction Cost Estimates",
         "Labor, material and equipment pricing for builders and remodelers who need a number they can stand behind."),
        ("upload-plans.html", "clipboard-check", "Bid Preparation",
         "Proposal-ready summaries, inclusions and exclusions — submit organized, competitive bids on time."),
        ("general-contractor-estimating.html", "building2", "GC &amp; Multi-Trade Estimates",
         "Full-project, multi-trade estimates for GCs bidding commercial, multifamily, civil and institutional work."),
        ("services.html", "scale", "Bid Leveling &amp; Scope Review",
         "Catch scope gaps and compare sub bids before they cost you — for GCs protecting margin."),
        ("overflow-estimating.html", "refresh", "Monthly Overflow Estimating",
         "Reserved capacity for overloaded teams — handle the estimates your team can't get to."),
        ("services.html", "doc-text", "Change Orders &amp; Revisions",
         "Priced change-order support and revisions that keep moving projects accurate and defensible."),
        ("construction-cost-estimating.html", "cube", "Material, Labor &amp; Equipment Breakdowns",
         "Organized cost breakdowns for purchasing, planning and field coordination."),
    ])

    pain_cards = "".join([
        pain_card("doc-text", "Bid invitations are piling up — more opportunities than your current estimating capacity can handle.", 0),
        pain_card("briefcase", "Project managers are estimating after hours — pulling them away from active jobs and other work.", 60),
        pain_card("calendar", "Hiring creates fixed overhead — recruiting, salary, payroll, software, training, and slow periods.", 120),
    ])

    outcomes = [
        ("chart", "Submit more bids each month"),
        ("refresh", "Respond to more invitations to bid"),
        ("clock", "Reduce missed deadlines"),
        ("briefcase", "Keep project managers focused on active projects"),
        ("layers", "Scale capacity when bid volume increases"),
        ("clipboard-check", "Maintain a consistent estimating process"),
        ("users", "Avoid depending on one estimator's availability"),
        ("puzzle", "Turn estimating into a repeatable business system"),
    ]
    outcome_cards = "".join(feature_item(ic, t, "", i * 40) for i, (ic, t) in enumerate(outcomes))

    body = '''
<section class="hero">
  <div class="blueprint"></div><div class="glow a"></div><div class="glow b"></div>
  <div class="container section" style="padding-block:clamp(48px,7vw,88px)">
    <div class="hero-top stagger">
      <div>
        <span class="eyebrow on-dark">First qualifying estimate free for new companies</span>
        <h1 style="margin-top:22px">Bid more projects <span class="serif-accent" style="color:#cddcef">without hiring</span> another estimator.</h1>
      </div>
      <div>
        <p class="lead" style="color:#cdddf7;max-width:52ch">
          Start with one qualifying estimate free, then keep bidding with AI-assisted, human-reviewed estimating support as your workload grows.</p>
        <div class="flex gap-3 wrap" style="margin-top:24px">
          %s
          %s
        </div>
        <p class="reassure" style="margin-top:16px">%s No card required &nbsp;•&nbsp; One qualifying estimate per new company</p>
        <p style="margin-top:10px;max-width:54ch;font-size:.84rem;color:#aebfd5">Supported scope and project complexity are reviewed before acceptance. Turnaround is confirmed after complete documents are received and reviewed.</p>
      </div>
    </div>
    <div class="hero-figure reveal-scale">
      <div class="framed">
        <img class="hero-doc" src="assets/img/bid-estimate.png" alt="Sample Mobi Estimates construction bid: a branded bid summary showing the total bid amount and a division-by-division cost breakdown, alongside a detailed Division 03 concrete estimate" width="1535" height="1024" fetchpriority="high">
      </div>
    </div>
  </div>
</section>

%s

%s

%s

%s

<section class="section">
  <div class="container">
    <div class="center reveal" style="max-width:760px;margin-inline:auto">
      <span class="eyebrow">The bottleneck</span>
      <h2 style="margin-top:14px">Too many bids. <span class="serif-accent">Not enough</span> estimating capacity.</h2>
      <p class="lead mt-3">Construction companies lose opportunities when bid invitations pile up faster than their teams can process them. Mobi gives contractors additional estimating capacity without the recruiting, onboarding, software, and management burden of adding another employee.</p>
    </div>
    <div class="grid cols-3 mt-8">%s</div>
    <div class="center mt-6">
      <p class="lead" style="max-width:60ch;margin:0 auto 22px">Mobi plugs into your existing workflow and handles the estimates your team cannot get to.</p>
      %s
    </div>
  </div>
</section>

<section class="section band-alt">
  <div class="container">
    <div class="center reveal" style="max-width:720px;margin-inline:auto">
      <span class="eyebrow">Business outcomes</span>
      <h2 class="mt-2">More estimating capacity means more opportunities to win</h2>
      <p class="muted mt-3">More capacity helps you pursue more work. Bid results still depend on competition, pricing strategy, and many factors outside any estimator's control.</p>
    </div>
    <div class="grid cols-4 mt-8">%s</div>
  </div>
</section>

<section class="section">
  <div class="container">
    <div class="flex items-center wrap reveal" style="justify-content:space-between;gap:18px">
      <div style="max-width:560px">
        <span class="eyebrow">What we do</span>
        <h2 style="margin-top:14px">Estimating services for <span class="serif-accent">every stage</span> of the bid</h2>
      </div>
      %s
    </div>
    <div class="mt-8">%s</div>
  </div>
</section>

%s

<section class="section">
  <div class="container">
    <div class="center reveal" style="max-width:700px;margin-inline:auto">
      <span class="eyebrow">Simple process</span>
      <h2 style="margin-top:14px">From plans to a bid-ready estimate in three simple steps</h2>
    </div>
    <div class="grid cols-3 mt-8">
      %s
    </div>
    <div class="center mt-6">%s</div>
  </div>
</section>

%s

%s

%s

%s

%s

%s
''' % (
        btn(CTA_JOIN[0], CTA_JOIN[1], "primary", "arrow-right", "lg", data="hero_join"),
        btn("View Sample Estimate", "sample-estimate.html", "ghost", "arrow-right", "lg", data="hero_sample"),
        icon("check"),
        trust_strip(),
        home_offer_section(),
        home_progress_section(),
        home_followup_section(),
        pain_cards,
        btn(CTA_JOIN[0], CTA_JOIN[1], "primary", "arrow-right", data="pain_cta"),
        outcome_cards,
        btn("View all services", "services.html", "outline", "arrow-right"),
        services,
        home_pricing_preview(),
        home_process_steps(),
        btn(CTA_JOIN[0], CTA_JOIN[1], "primary", "arrow-right", data="process_join"),
        project_vs_monthly(),
        deliverables_section(),
        fit_section(),
        founder_section(),
        qc_section(),
        cta_band(primary=(CTA_JOIN[0], CTA_JOIN[1], "arrow-right"),
                 secondary=("View Sample Estimate", "sample-estimate.html")),
    )
    page("index.html",
         "Mobi Estimates | Construction Estimating and Takeoff Services",
         "Bid more construction projects without hiring another estimator. Mobi Estimates provides quantity takeoffs, cost estimates, bid preparation, and monthly estimating support nationwide.",
         body, active="")


def home_bars():
    rows = [("Sitework & Concrete", 62), ("Structure & Framing", 78), ("Finishes", 45), ("MEP", 88)]
    return "".join(
        '<div class="ec-row"><span>%s %s</span><div class="bar"><i style="width:%d%%"></i></div></div>'
        % (icon("cube"), name, pct) for name, pct in rows)


def home_process_steps():
    steps = [
        ("Submit Your Plans", "Send drawings, specifications, addenda, scope notes, and the bid due date."),
        ("Track Review Progress", "Follow customer-safe milestones while Mobi reviews scope, takeoff, pricing, and quality."),
        ("Review Your Estimate", "A human-reviewed estimate becomes available only after the approval gate is complete."),
    ]
    return "".join(
        '<div class="step reveal" data-delay="%d"><div class="num">%d</div><h3>%s</h3><p>%s</p></div>'
        % (i * 70, i + 1, t, d) for i, (t, d) in enumerate(steps))


def home_pricing_preview():
    cards = [
        ("Monthly estimating plans", "From $995/mo", "Ongoing estimating capacity at the regular monthly price.", "pricing.html#monthly"),
        ("Growth (Most Popular)", "$1,995/mo", "Our most popular monthly plan for bidding more consistently.", "pricing.html#monthly"),
        ("Pay Per Project", "$599 one-time", "One professional estimate — not a subscription.", "pricing.html#one-time"),
    ]
    cells = "".join(
        '<a class="card card-hover reveal price-preview" data-delay="%d" href="%s"><div class="pp-name">%s</div><div class="pp-price">%s</div><p>%s</p><span class="tag" style="margin-top:14px">See details %s</span></a>'
        % (i * 70, h, n, p, d, icon("arrow-ur")) for i, (n, p, d, h) in enumerate(cards))
    return '''<section class="section band-alt">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">Transparent pricing</span>
      <h2 class="mt-2">Per-project or monthly — your choice</h2>
    </div>
    <div class="grid cols-3 mt-8">%s</div>
    <div class="center mt-6">%s</div>
  </div>
</section>''' % (cells, btn(CTA_COMPARE[0], CTA_COMPARE[1], "primary", "arrow-right", data="home_compare_options"))


def project_vs_monthly():
    proj = ["The customer needs occasional estimating help", "You have one urgent project",
            "Bid volume changes significantly", "You want to test Mobi",
            "You do not need reserved monthly capacity"]
    mon = ["Bid invitations arrive consistently", "Your internal team is overloaded",
           "You want predictable estimating expenses", "You need repeatable workflows",
           "You want priority capacity", "You want to bid more consistently",
           "Mobi will be a primary or ongoing estimating resource"]
    return '''<section class="section">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">Which model fits?</span>
      <h2 class="mt-2">Choose the estimating model that fits your workload</h2>
    </div>
    <div class="grid cols-2 mt-8" style="gap:24px">
      <div class="card reveal"><h3 class="mb-3">Project-based is best when</h3><ul class="check-list">%s</ul></div>
      <div class="card reveal" data-delay="80"><h3 class="mb-3">Monthly support is best when</h3><ul class="check-list">%s</ul></div>
    </div>
    <div class="center mt-6">%s</div>
  </div>
</section>''' % ("".join('<li>%s<span>%s</span></li>' % (icon("check-circle"), x) for x in proj),
                 "".join('<li>%s<span>%s</span></li>' % (icon("check-circle"), x) for x in mon),
                 btn("Help Me Choose", "capacity-plan.html", "primary", "arrow-right", data="help_me_choose"))


# ==========================================================================
# PRICING
# ==========================================================================
def build_pricing():
    mon_cards = "".join(monthly_card(p, i * 70) for i, p in enumerate(MONTHLY_PLANS))
    ppp_card = project_card(PROJECT_PLANS[0])

    intro = '''<div class="promo-banner reveal">
  <p class="promo-head">%s</p>
  <p class="promo-note">%s %s %s</p>
  <div style="margin-top:14px">%s</div>
</div>''' % (INTRO_OFFER_HEADLINE, INTRO_OFFER_SUMMARY, INTRO_OFFER_REVIEW,
             INTRO_OFFER_AFTER,
             btn(CTA_JOIN[0], CTA_JOIN[1], "primary", "arrow-right", data="pricing_offer"))

    body = page_hero(
        "Pricing",
        "Choose the estimating support that fits your business",
        "Get fast, professional, human-reviewed construction estimates without immediately adding another full-time estimator to your payroll. Choose a monthly plan or order one estimate for a one-time price.",
        [("Pricing", None)]
    ) + '''
<section class="section" id="monthly">
  <div class="container">
    %s
    <div class="center reveal mt-8" style="max-width:720px;margin-inline:auto">
      <span class="eyebrow">Monthly estimating subscriptions</span>
      <h2 class="mt-2">Three monthly plans at regular monthly pricing</h2>
    </div>
    <div class="grid cols-3 mt-8 pkg-grid">%s</div>
    <p class="muted center mt-6" style="max-width:80ch;margin-inline:auto;font-size:.9rem">%s</p>
  </div>
</section>

<section class="section band-alt" id="one-time">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">One-time option</span>
      <h2 class="mt-2">Pay Per Project</h2>
      <p class="muted mt-3">After your qualifying free estimate, order another estimate for $599 or choose a monthly plan for ongoing capacity.</p>
    </div>
    <div class="grid mt-8 pkg-grid" style="max-width:520px;margin-inline:auto">%s</div>
  </div>
</section>

<section class="section">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">Less fixed overhead</span>
      <h2 class="mt-2">Add capacity without the burden of another hire</h2>
      <p class="muted mt-3">Mobi can reduce the fixed operational burden tied to recruiting, onboarding, training, software, payroll, benefits, management, employee downtime, and fluctuating bid volume. We don't claim to always be cheaper than hiring — we help you scale capacity with your bid volume.</p>
    </div>
    <div class="mt-8">%s</div>
  </div>
</section>

<section class="section band-alt">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">In-house vs. freelancer vs. Mobi</span>
      <h2 class="mt-2">A clear way to compare your options</h2>
    </div>
    <div class="mt-8">%s</div>
  </div>
</section>

%s
''' % (intro, mon_cards, MONTHLY_CAPACITY_NOTE, ppp_card,
       check_list(["Recruiting", "Onboarding", "Training", "Software", "Payroll", "Benefits",
                   "Management", "Employee downtime", "Fluctuating bid volume"], "cols-3"),
       comparison_table(),
       cta_band("Choose the plan that fits your business",
                "Pick a monthly plan for ongoing estimating support, or order one estimate for a one-time $599 price.",
                ("Choose a Monthly Plan", "#monthly"),
                ("Order One Estimate", CHECKOUT_BASE + "/start?plan=pay_per_project")))
    page("pricing.html",
         "Pricing | Monthly Estimating Plans & Pay Per Project | Mobi Estimates",
         "Start with one qualifying estimate free per new company. Afterward, choose Starter $995, Growth $1,995, Estimating Department $2,995, or a one-time $599 Pay Per Project estimate.",
         body, active="pricing")


# ==========================================================================
# SAMPLE ESTIMATE
# ==========================================================================
def build_sample_estimate():
    previews = [
        ("doc-text", "Executive estimate summary", "Project overview, total, and key assumptions on one page."),
        ("doc-search", "Quantity takeoff", "Measured quantities by trade with units and references."),
        ("users", "Labor breakdown", "Crew/production-based labor pricing by scope."),
        ("cube", "Material breakdown", "Material quantities, waste factors, and pricing."),
        ("truck", "Equipment costs", "Owned or rented equipment where applicable."),
        ("layers", "CSI divisions", "Costs organized by CSI MasterFormat division."),
        ("ruler", "Marked-up drawings", "Color-coded plans showing what was measured."),
        ("clipboard-check", "Assumptions & exclusions", "Clear scope boundaries to protect your bid."),
        ("adjust", "Alternates & allowances", "Optional pricing and allowance lines where needed."),
        ("check-circle", "Bid-ready summary", "A clean, proposal-ready output in PDF and Excel."),
    ]
    cards = "".join(feature_item(ic, t, d, i * 40) for i, (ic, t, d) in enumerate(previews))

    if SAMPLE_PDF_URL:
        download_cta = btn("Send Me the Sample Estimate", SAMPLE_PDF_URL, "primary", "doc-text", cls="btn-block", data="sample_download")
        form_note = "Enter your details and we'll email you the sample estimate."
    else:
        download_cta = btn("Send Me the Sample Estimate", "#", "primary", "doc-text", cls="btn-block", data="sample_form_submit", attrs='data-submit')
        form_note = "Enter your details and we'll send the sample estimate to your inbox."

    form = '''<form class="form-card" id="sampleForm" data-form data-analytics-form="sample" novalidate>
  <div class="form-grid">%s%s</div>
  %s
  %s
  %s
  <p class="hint center mt-3">No spam. We only use your details to send the sample and follow up about your project.</p>
</form>%s''' % (
        field("First name", "first_name", required=True, autocomplete="given-name"),
        field("Last name", "last_name", required=True, autocomplete="family-name"),
        field("Company", "company", required=True, autocomplete="organization"),
        field("Email", "email", "email", required=True, autocomplete="email"),
        field("Phone (optional)", "phone", "tel", autocomplete="tel"),
        "")
    form = form.replace(download_cta, download_cta)  # noop guard
    form = form[:form.rfind("</form>")] + download_cta + "</form>" + form_success(
        "Thanks — your sample is on the way",
        "We've recorded your request. The Mobi team will send the sample estimate to your email shortly.")

    demo_note = ('<div class="card reveal" style="background:var(--bg-alt);border:none;margin-top:18px">'
                 '<p class="muted" style="margin:0;font-size:.9rem">%s This page shows a labeled demonstration of our deliverables. '
                 'A downloadable sample PDF can be attached here once provided — no broken links are shown.</p></div>' % icon("doc-text"))

    body = page_hero(
        "Sample Estimate",
        "See exactly what you receive",
        "Mobi delivers organized, professional, bid-ready estimating documents. Preview the sections below, then request the full sample.",
        [("Sample Estimate", None)]
    ) + '''
<section class="section">
  <div class="container">
    <div class="grid" style="grid-template-columns:1.05fr .95fr;gap:48px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">Inside a Mobi estimate</span>
        <h2 class="mt-2 mb-4">Demonstration preview</h2>
        <div class="grid cols-2">%s</div>
        %s
      </div>
      <div class="reveal" data-delay="80">
        <div style="position:sticky;top:96px">
          <h3 class="mb-2">%s</h3>
          <p class="muted mb-3" style="font-size:.95rem">%s</p>
          %s
        </div>
      </div>
    </div>
  </div>
</section>
%s''' % (cards, demo_note, "Get the sample estimate", form_note, form, cta_band())
    page("sample-estimate.html",
         "Sample Construction Estimate | See Our Deliverables | Mobi Estimates",
         "See exactly what you receive from Mobi Estimates — executive summary, quantity takeoff, labor/material/equipment breakdowns, CSI divisions, marked-up drawings, and a bid-ready summary.",
         body, active="sample")


# ==========================================================================
# CAPACITY PLAN (monthly qualification form)
# ==========================================================================
def build_capacity_plan():
    contractor_types = ["General contractor", "Subcontractor", "Home builder", "Developer",
                        "Remodeler", "Construction manager", "Other"]
    project_types = ["Residential", "Commercial", "Multifamily", "Industrial", "Civil",
                     "Institutional", "Renovation", "New construction", "Tenant improvement", "Mixed"]
    plans = ["Starter Estimating Support — $995/month", "Growth Bid Support — $1,995/month",
             "Outsourced Estimating Department — $2,995/month", "Not sure — help me choose"]

    form = '''<form class="form-card" id="capacityForm" data-form data-analytics-form="capacity" novalidate>
  <div class="form-grid">%s%s</div>
  %s
  <div class="form-grid">%s%s</div>
  <div class="form-grid">%s%s</div>
  <div class="form-grid">%s%s</div>
  <div class="form-grid">%s%s</div>
  <div class="form-grid">%s%s</div>
  %s
  %s
  %s
  %s
  <p class="hint center mt-3">We use this to recommend the right plan. No obligation.</p>
</form>%s''' % (
        field("First name", "first_name", required=True, autocomplete="given-name"),
        field("Last name", "last_name", required=True, autocomplete="family-name"),
        field("Company name", "company", required=True, autocomplete="organization"),
        field("Email", "email", "email", required=True, autocomplete="email"),
        field("Phone", "phone", "tel", autocomplete="tel"),
        select_field("Contractor type", "contractor_type", contractor_types),
        field("Primary trades", "trades", placeholder="e.g. concrete, framing, MEP"),
        select_field("Typical project types", "project_types", project_types),
        field("Typical project size", "project_size", placeholder="e.g. $2M commercial TI"),
        field("Average bids submitted / month", "bids_now", "number"),
        field("Desired bids / month", "bids_target", "number"),
        field("Internal estimators", "estimators", "number"),
        field("Current estimating bottleneck", "bottleneck", placeholder="What's slowing bids down?"),
        select_field("Preferred subscription plan", "plan", plans),
        field("Desired start date", "start_date", "date"),
        textarea_field("Additional notes", "notes", placeholder="Anything else we should know?"),
        btn("Request My Capacity Plan", "#", "primary", "arrow-right", "lg", cls="btn-block", data="capacity_submit", attrs="data-submit"),
        form_success("Thank you — we'll map your capacity plan",
                     "The Mobi team will review your details and follow up with a recommended plan and reserved estimating capacity for your bid volume."))

    body = page_hero(
        "Monthly Capacity Plan",
        "Let's build the right estimating capacity for your company",
        "Tell us about your bid volume and bottlenecks. We'll recommend a plan that fits — Starter, Growth, or an Outsourced Estimating Department — with no obligation.",
        [("Pricing", "pricing.html"), ("Capacity Plan", None)]
    ) + '''
<section class="section">
  <div class="container">
    <div class="grid" style="grid-template-columns:.8fr 1.2fr;gap:48px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">Outsourced estimating</span>
        <h2 class="mt-2 mb-3">Capacity, not hours</h2>
        <p class="muted mb-4">Monthly plans reserve estimating capacity and workflow support — bid more consistently without recruiting, training, and managing another employee.</p>
        %s
        <div class="mt-6">%s</div>
      </div>
      <div class="reveal" data-delay="80">%s</div>
    </div>
  </div>
</section>''' % (
        check_list(["Ongoing monthly estimating support", "Your templates, pricing & markups",
                    "AI-assisted and human-reviewed", "Month-to-month — cancel anytime"]),
        btn("View plans & pricing", "pricing.html", "outline", "arrow-right", cls="btn-block", data="capacity_pricing"),
        form)
    page("capacity-plan.html",
         "Request a Monthly Estimating Capacity Plan | Mobi Estimates",
         "Tell us your bid volume and we'll recommend the right monthly estimating plan — Starter, Growth, or an Outsourced Estimating Department. No obligation, month-to-month.",
         body, active="pricing")


# ==========================================================================
# UPLOAD PLANS (2-step quote + file upload)
# ==========================================================================
def build_upload_plans():
    services = ["Quantity takeoff", "Full estimate", "GC or multi-trade estimate", "Project-based estimating",
                "Monthly estimating support", "Bid leveling or scope review", "Not sure"]
    contact_methods = ["Email", "Phone", "Either"]

    step1 = '''<div class="form-step" data-step="1">
  <div class="form-grid">%s%s</div>
  %s
  <div class="form-grid">%s%s</div>
  <div class="form-grid">%s%s</div>
  <div class="form-grid">%s%s</div>
  <div class="step-actions"><button type="button" class="btn btn-primary btn-lg" data-next data-analytics="quote_step1_next">Continue to files %s</button></div>
</div>''' % (
        field("First name", "first_name", required=True, autocomplete="given-name"),
        field("Last name", "last_name", required=True, autocomplete="family-name"),
        field("Company name", "company", required=True, autocomplete="organization"),
        field("Email", "email", "email", required=True, autocomplete="email"),
        field("Phone", "phone", "tel", autocomplete="tel"),
        field("Project name", "project_name"),
        field("Project location", "project_location", placeholder="City, State"),
        field("Bid due date", "bid_due", "date"),
        select_field("Service needed", "service", services, required=True),
        icon("arrow-right"))

    step2 = '''<div class="form-step" data-step="2" hidden>
  %s
  %s
  <div class="form-grid">%s%s</div>
  %s
  <div class="step-actions">
    <button type="button" class="btn btn-outline" data-back>Back</button>
    <button type="submit" class="btn btn-primary btn-lg" data-analytics="quote_submit">Submit Project for Review</button>
  </div>
</div>''' % (
        dropzone(),
        textarea_field("Trades or scope requested", "scope", placeholder="Which trades / scope should we price?"),
        select_field("Preferred contact method", "contact_method", contact_methods),
        field("Optional special instructions", "instructions"),
        textarea_field("Brief project notes", "notes", placeholder="Deadline, addenda, anything we should know"))

    form = '''<form class="form-card" id="quoteForm" data-form data-multistep data-analytics-form="quote" novalidate>
  <div class="form-progress" aria-hidden="true">
    <div class="fp-track"><span class="fp-fill" style="width:50%%"></span></div>
    <span class="fp-label">Step <b class="fp-current">1</b> of 2</span>
  </div>
  %s
  %s
</form>%s''' % (step1, step2,
                form_success("Your project has been submitted",
                             "The Mobi team will review your files and contact you with the next steps — recommended service, exact price, deliverables, and expected turnaround."))

    body = page_hero(
        "Upload Plans",
        "Upload your plans for a free scope review",
        "We will review your project and confirm the exact price, recommended service, deliverables, and expected turnaround before work begins.",
        [("Upload Plans", None)]
    ) + '''
<section class="section">
  <div class="container">
    <div class="grid" style="grid-template-columns:.8fr 1.2fr;gap:48px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">Free plan &amp; scope review</span>
        <h2 class="mt-2 mb-3">No obligation, no contract</h2>
        <p class="muted mb-4">Upload your plans and bidding documents. Mobi reviews the project and provides an exact price, recommended service, and expected delivery schedule before work begins.</p>
        %s
        <div class="card mt-6" style="background:var(--bg-alt);border:none">
          <div class="flex items-center gap-2 mb-2" style="color:var(--brand-700);font-weight:600">%s Confidential</div>
          <p class="muted" style="font-size:.92rem">Your plans and project information will be used only to review, quote, and complete the requested estimating services.</p>
        </div>
      </div>
      <div class="reveal" data-delay="80">%s</div>
    </div>
  </div>
</section>''' % (
        check_list(["Plans, specs & addenda", "Bid forms & instructions", "Scope notes & deadline",
                    "Your labor rates & markups (optional)"]),
        icon("lock"), form)
    page("upload-plans.html",
         "Upload Plans for a Free Estimating Quote | Mobi Estimates",
         "Upload your construction plans for a free scope review. Mobi confirms the exact price, recommended service, deliverables, and turnaround before work begins. Nationwide.",
         body, active="")


def redirect_stub(filename, target):
    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="robots" content="noindex,follow">'
            '<link rel="canonical" href="%s/%s">'
            '<meta http-equiv="refresh" content="0; url=%s">'
            '<title>Redirecting…</title></head><body>'
            '<p>This page has moved. <a href="%s">Continue to Upload Plans</a>.</p>'
            '<script>location.replace("%s");</script></body></html>'
            % (CANONICAL_BASE, target, target, target, target))
    with open(os.path.join(OUT, filename), "w", encoding="utf-8") as f:
        f.write(html)


# ==========================================================================
# SERVICES (overview)
# ==========================================================================
def build_services():
    groups = [
        ("Core estimating", [
            ("construction-cost-estimating.html", "calculator", "Construction Cost Estimates",
             "Labor, material, equipment and subcontractor costs from your plans and specs — a number you can bid with confidence."),
            ("quantity-takeoffs.html", "doc-search", "Quantity Takeoffs",
             "Measured quantities from your drawings — linear feet, SF, CY, counts and schedules, by trade."),
            ("general-contractor-estimating.html", "building2", "GC & Multi-Trade Estimates",
             "Full-project, multi-trade estimates and bid-ready packages built for general contractors."),
            ("subcontractor-estimating.html", "wrench", "Subcontractor Estimating",
             "Trade-specific takeoffs and pricing so subs can bid faster and more competitively."),
        ]),
        ("Bid & budget support", [
            ("upload-plans.html", "clipboard-check", "Bid Preparation",
             "Bid summary, scope breakdown, inclusions, exclusions, assumptions, alternates and a proposal-ready estimate."),
            ("construction-cost-estimating.html", "chart", "Budget & Conceptual Estimates",
             "Early-stage budgets, cost-per-SF and feasibility numbers before complete documents exist."),
            ("services.html#review", "scale", "Bid Leveling & Scope Review",
             "Scope-gap analysis, bid leveling, subcontractor comparison and quantity verification."),
            ("services.html#ve", "adjust", "Value Engineering",
             "Cost-saving alternatives and substitutions that maintain project intent."),
        ]),
        ("Ongoing & specialized", [
            ("overflow-estimating.html", "refresh", "Monthly Overflow Estimating",
             "Reserved capacity and priority intake when bids pile up — without hiring in-house."),
            ("services.html#change-order", "doc-text", "Change Orders & Revisions",
             "Priced change-order support and revisions that keep projects accurate and defensible."),
            ("construction-cost-estimating.html", "cube", "Material Lists",
             "Organized material quantity reports for purchasing, supplier pricing and field coordination."),
            ("services.html#scope-sheets", "list-check", "Subcontractor Scope Sheets",
             "Scope-of-work documents to request and compare subcontractor bids."),
        ]),
    ]
    sections = ""
    counter = 0
    for gi, (label, items) in enumerate(groups):
        rows = ""
        for (h, ic, t, d) in items:
            counter += 1
            rows += numbered_item(counter, h, ic, t, d)
        sections += ('<div class="reveal" style="margin-top:%dpx;margin-bottom:18px"><span class="eyebrow">%s</span></div>'
                     '<div class="num-list">%s</div>' % (0 if gi == 0 else 52, label, rows))

    detail = '''<section class="section band-alt">
  <div class="container">
    <div class="grid cols-2" style="gap:40px">
      <div class="reveal" id="review"><span class="eyebrow">Review &amp; comparison</span><h3 class="mt-2">Catch missing scope before it costs you</h3><p class="muted mt-2 mb-3">Independent review of estimates and subcontractor bids.</p>%s</div>
      <div class="reveal" id="ve" data-delay="80"><span class="eyebrow">Value engineering</span><h3 class="mt-2">Reduce cost while protecting intent</h3><p class="muted mt-2 mb-3">Practical alternatives with constructability in mind.</p>%s</div>
      <div class="reveal" id="change-order"><span class="eyebrow">Change orders</span><h3 class="mt-2">Priced, documented changes</h3><p class="muted mt-2 mb-3">Support for added or deleted scope during a project.</p>%s</div>
      <div class="reveal" id="scope-sheets" data-delay="80"><span class="eyebrow">Scope sheets</span><h3 class="mt-2">Compare sub bids fairly</h3><p class="muted mt-2 mb-3">Clear inclusions and exclusions for each trade.</p>%s</div>
    </div>
    <p class="muted mt-6" style="font-size:.86rem;max-width:72ch">Value engineering suggestions are not architectural or engineering design and do not replace work performed by a properly licensed professional.</p>
  </div>
</section>''' % (
        check_list(["Scope-gap analysis", "Bid leveling", "Subcontractor comparison", "Quantity verification", "Missing/duplicate-cost checks", "Risk review"]),
        check_list(["Alternative materials & assemblies", "Cost-saving options", "Substitutions", "Constructability suggestions", "Budget alignment"]),
        check_list(["Added/deleted scope", "Labor & material impacts", "Equipment costs", "Change-order backup", "Cost comparison"]),
        check_list(["Scope description", "Included / excluded work", "Required alternates", "Allowances", "Bid requirements"]))

    body = page_hero(
        "Services",
        "Construction estimating services for the entire bid",
        "From quantity takeoffs and detailed cost estimates to bid preparation, bid leveling, change orders and ongoing overflow support — across all trades and project types.",
        [("Services", None)]
    ) + ('<section class="section"><div class="container">%s</div></section>%s%s'
         % (sections, detail, cta_band()))
    page("services.html",
         "Construction Estimating Services | Takeoffs, Cost Estimates & Bid Prep | Mobi Estimates",
         "Construction cost estimating, quantity takeoffs, bid preparation, bid leveling, change orders and monthly overflow estimating — all trades, all project types, nationwide.",
         body, active="services")


# ==========================================================================
# Generic service-detail page builder
# ==========================================================================
def service_detail(filename, title_seo, eyebrow, h1, intro, included, deliverables,
                   meta_desc, who="", outcome="", extra_section=""):
    helps = ('<div class="card mt-6" style="background:var(--bg-alt);border:none"><p class="muted" style="margin:0;font-size:.95rem"><b>Who it helps:</b> %s<br><b>The outcome:</b> %s</p></div>'
             % (who, outcome)) if who else ""
    body = page_hero(eyebrow, h1, intro, [("Services", "services.html"), (eyebrow, None)])
    body += '''
<section class="section">
  <div class="container">
    <div class="grid" style="grid-template-columns:1.05fr .95fr;gap:48px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">What's included</span>
        <h2 class="mt-2 mb-4">Detailed, organized and bid-ready</h2>
        %s
        %s
      </div>
      <div class="reveal" data-delay="80">
        <div class="card" style="position:sticky;top:96px">
          <h3>Typical deliverables</h3>
          <p class="muted mt-2 mb-3" style="font-size:.95rem">What you can expect to receive.</p>
          %s
          <div class="mt-6 grid" style="gap:10px">%s%s</div>
        </div>
      </div>
    </div>
  </div>
</section>
%s
%s''' % (check_list(included, "cols-2"), helps, check_list(deliverables),
         btn(CTA_PRIMARY[0], CTA_PRIMARY[1], "primary", "upload", cls="btn-block", data="svc_upload_%s" % filename.replace(".html", "")),
         btn(CTA_PRICING[0], CTA_PRICING[1], "outline", cls="btn-block", data="svc_pricing"),
         extra_section, cta_band())
    page(filename, title_seo, meta_desc, body, active="services")


def build_service_details():
    service_detail(
        "quantity-takeoffs.html",
        "Quantity Takeoff Services | Construction Takeoffs | Mobi Estimates",
        "Quantity Takeoffs", "Accurate quantity takeoffs from your construction drawings",
        "Measured quantities pulled straight from your plans — organized by trade and ready to price or hand to suppliers and subs.",
        ["Linear feet", "Square footage", "Cubic yards", "Material counts", "Fixture counts",
         "Equipment counts", "Door & window schedules", "Room-by-room quantities",
         "Area & volume calculations", "Trade-specific takeoff reports", "Marked-up plans when applicable"],
        ["Trade-specific takeoff reports", "Marked-up drawings", "Material counts & schedules",
         "Excel and PDF delivery", "One revision round"],
        "Professional construction quantity takeoff services — linear feet, SF, CY, counts, schedules and marked-up plans, organized by trade, nationwide.",
        who="Subcontractors and GCs who need to price fast.",
        outcome="Bid more trades in less time with measured, defensible quantities.")

    service_detail(
        "construction-cost-estimating.html",
        "Construction Cost Estimating Services | Mobi Estimates",
        "Construction Cost Estimates", "Detailed construction cost estimates you can bid with confidence",
        "Labor, material, equipment and subcontractor costs prepared from your plans and specs — reviewed before delivery.",
        ["Labor costs", "Material costs", "Equipment costs", "Subcontractor costs", "Waste factors",
         "Production rates", "Overhead", "Profit markup", "Taxes & freight", "General conditions",
         "Allowances", "Alternates", "Contingencies"],
        ["Detailed construction estimate", "Trade-by-trade cost summary", "Labor & material breakdown",
         "Assumptions & exclusions", "Excel and PDF estimate package"],
        "Detailed construction cost estimating — labor, material, equipment and subcontractor costs, overhead, markup and contingencies — prepared from your plans and reviewed before delivery.",
        who="Builders, remodelers and GCs who need a number they can stand behind.",
        outcome="Submit competitive, defensible bids with every cost accounted for.")

    service_detail(
        "general-contractor-estimating.html",
        "General Contractor & Multi-Trade Estimating | Mobi Estimates",
        "GC & Multi-Trade Estimating", "Full-project estimating for general contractors",
        "Multi-trade estimates and bid-ready packages that help GCs pursue more projects without expanding their in-house estimating department.",
        ["Full-project, multi-trade takeoffs", "Detailed cost estimates", "General conditions & requirements",
         "Subcontractor cost organization", "Bid summary & scope breakdown", "Inclusions, exclusions & assumptions",
         "Alternates & allowances", "Scope-gap review", "Bid leveling", "Proposal-ready estimate package"],
        ["Trade-by-trade cost summary", "Bid summary & scope breakdown", "Marked-up drawings",
         "Subcontractor comparison", "CSI division breakdown", "Excel and PDF package"],
        "Full-project general contractor and multi-trade estimating — multi-trade takeoffs, detailed costs, general conditions, bid leveling and proposal-ready packages, nationwide.",
        who="General contractors bidding commercial, multifamily, civil and institutional work.",
        outcome="Pursue more full-project bids without adding estimating headcount.")

    service_detail(
        "subcontractor-estimating.html",
        "Subcontractor Estimating Services | Mobi Estimates",
        "Subcontractor Estimating", "Trade-specific estimating for subcontractors",
        "Fast, detailed takeoffs and pricing for your trade so you can bid more work, more competitively — without slowing down the field.",
        ["Trade-specific quantity takeoffs", "Material counts & schedules", "Labor & production rates",
         "Equipment costs", "Waste factors", "Marked-up plans", "Scope-of-work summary",
         "Inclusions & exclusions", "Alternates & allowances", "Proposal-ready pricing"],
        ["Trade-specific takeoff report", "Material list", "Labor & material breakdown",
         "Marked-up drawings", "Excel and PDF package"],
        "Subcontractor estimating and trade-specific takeoffs across all CSI divisions — concrete, masonry, metals, MEP, finishes and more. Bid faster and more competitively.",
        who="Specialty and trade subcontractors.",
        outcome="Turn around more trade bids and keep your crews focused on work.")

    service_detail(
        "monthly-estimating-support.html",
        "Monthly Estimating Support | Outsourced Estimating | Mobi Estimates",
        "Monthly Estimating Support", "Ongoing estimating support, month after month",
        "Reserved estimating capacity for contractors with recurring needs — takeoffs, cost estimates, bid prep and revisions, set up around how your company bids.",
        ["Reserved monthly bid capacity", "Priority scheduling", "Quantity takeoffs", "Cost estimates",
         "Bid preparation", "Scope review", "Addenda support", "Revision support",
         "Client-specific templates", "Client-specific labor rates & markups", "Bid-pipeline review"],
        ["Recurring takeoffs & estimates", "Bid preparation", "Estimate revisions",
         "Custom templates", "Bid-status tracking"],
        "Monthly construction estimating support — reserved capacity, priority intake, recurring takeoffs and estimates, your pricing and templates, plus bid-pipeline review. Scale without hiring.",
        who="Contractors with consistent bid volume or overloaded teams.",
        outcome="Bid more consistently without recruiting, training and managing another hire.",
        extra_section='''<section class="section band-alt"><div class="container">
          <div class="center reveal" style="max-width:680px;margin-inline:auto"><span class="eyebrow">Plans</span><h2 class="mt-2">Monthly plans built on capacity</h2><p class="muted mt-3">%s</p></div>
          <div class="center mt-6">%s</div></div></section>''' % (
            MONTHLY_CAPACITY_NOTE,
            btn("See monthly pricing", "pricing.html#monthly", "primary", "arrow-right", data="msupport_pricing")))


# ==========================================================================
# Landing pages (SEO) — reusable template, distinct content each
# ==========================================================================
def landing(filename, eyebrow, h1, intro, meta_title, meta_desc, bullets, trades, who, outcome):
    body = page_hero(eyebrow, h1, intro, [("Services", "services.html"), (eyebrow, None)])
    trade_chips = "".join('<span class="tag">%s %s</span>' % (icon("check"), t) for t in trades)
    body += '''
<section class="section">
  <div class="container">
    <div class="grid" style="grid-template-columns:1.05fr .95fr;gap:48px;align-items:start">
      <div class="reveal">
        <h2 class="mb-4">What's included</h2>
        %s
        <div class="card mt-6" style="background:var(--bg-alt);border:none"><p class="muted" style="margin:0"><b>Who it helps:</b> %s<br><b>The outcome:</b> %s</p></div>
      </div>
      <div class="reveal" data-delay="80">
        <div class="card" style="position:sticky;top:96px">
          <h3 class="mb-3">Trades &amp; scopes</h3>
          <div class="flex wrap gap-2">%s</div>
          <div class="mt-6 grid" style="gap:10px">%s%s</div>
        </div>
      </div>
    </div>
  </div>
</section>
%s''' % (check_list(bullets, "cols-2"), who, outcome, trade_chips,
         btn(CTA_PRIMARY[0], CTA_PRIMARY[1], "primary", "upload", cls="btn-block", data="landing_upload"),
         btn(CTA_PRICING[0], CTA_PRICING[1], "outline", cls="btn-block"),
         cta_band())
    page(filename, meta_title, meta_desc, body, active="services")


def build_landing_pages():
    landing("overflow-estimating.html", "Overflow Estimating",
            "Overflow estimating capacity when bids pile up",
            "When invitations arrive faster than your team can process them, Mobi handles the overflow — so you stop turning down profitable work.",
            "Overflow Estimating Services for Contractors | Mobi Estimates",
            "Overflow construction estimating for overloaded teams. Reserved capacity and priority intake to handle the bids your estimators can't get to. Per-project or monthly.",
            ["Reserved estimating capacity", "Priority intake during busy periods", "Quantity takeoffs",
             "Cost estimates", "Bid preparation", "Your templates, pricing & markups", "Fast turnaround options"],
            ["All CSI divisions", "Single-trade", "Multi-trade", "GC packages"],
            "Contractors whose internal estimators are overloaded.",
            "Keep bidding through busy periods without missing deadlines or hiring.")

    landing("construction-estimating-services.html", "Construction Estimating",
            "Outsourced construction estimating services, nationwide",
            "Quantity takeoffs, cost estimates, bid preparation and overflow support for contractors across the United States — per-project or monthly.",
            "Construction Estimating Services Nationwide | Mobi Estimates",
            "Outsourced construction estimating services nationwide — quantity takeoffs, cost estimates, bid preparation and monthly support for GCs and subs across all trades.",
            ["Quantity takeoffs", "Cost estimates", "Bid preparation", "Bid leveling & scope review",
             "Change orders & revisions", "CSI division breakdowns", "Marked-up drawings", "Excel & PDF deliverables"],
            ["Residential", "Commercial", "Multifamily", "Industrial", "Civil", "Institutional"],
            "General contractors and subcontractors nationwide.",
            "A scalable estimating partner that grows with your bid volume.")

    landing("residential-estimating.html", "Residential Estimating",
            "Residential construction estimating for builders & remodelers",
            "Takeoffs and cost estimates for single-family, custom homes, additions and renovations — organized and bid-ready.",
            "Residential Construction Estimating Services | Mobi Estimates",
            "Residential construction estimating — single-family, custom homes, additions and remodels. Quantity takeoffs, labor and material pricing, marked-up plans. Nationwide.",
            ["Quantity takeoffs", "Labor & material pricing", "Marked-up drawings", "Allowances & alternates",
             "Assumptions & exclusions", "Excel & PDF deliverables"],
            ["New homes", "Additions", "Remodels", "Renovations", "Tenant improvements"],
            "Home builders and remodelers.",
            "Price more residential bids without after-hours takeoffs.")

    landing("commercial-estimating.html", "Commercial Estimating",
            "Commercial construction estimating for GCs & subs",
            "Multi-trade estimates, bid leveling and proposal-ready packages for commercial build-outs and ground-up projects.",
            "Commercial Construction Estimating Services | Mobi Estimates",
            "Commercial construction estimating — multi-trade estimates, CSI breakdowns, bid leveling and proposal-ready packages for GCs and subcontractors. Nationwide.",
            ["Multi-trade estimates", "CSI division breakdown", "Bid leveling", "Scope-gap review",
             "Alternates & allowances", "Bid-form support"],
            ["Office", "Retail", "Build-outs", "Ground-up", "Tenant improvements"],
            "Commercial general contractors and subcontractors.",
            "Pursue more commercial bids with organized, defensible numbers.")

    landing("multifamily-estimating.html", "Multifamily Estimating",
            "Multifamily construction estimating for developers & GCs",
            "Full-project, multi-trade estimating for apartments, condos and mixed-use developments.",
            "Multifamily Construction Estimating Services | Mobi Estimates",
            "Multifamily construction estimating — apartments, condos and mixed-use. Multi-trade takeoffs, CSI breakdowns, bid leveling and proposal-ready packages. Nationwide.",
            ["Full-project takeoffs", "Multi-trade estimates", "CSI division breakdown", "General conditions",
             "Alternates & allowances", "Bid leveling"],
            ["Apartments", "Condos", "Mixed-use", "Podium", "Wrap"],
            "Developers and general contractors bidding multifamily.",
            "Bid larger multifamily packages without expanding your team.")

    landing("civil-estimating.html", "Civil & Site Estimating",
            "Civil and site-development estimating",
            "Earthwork, utilities, paving and site-improvement takeoffs and estimates for civil contractors.",
            "Civil & Site Development Estimating Services | Mobi Estimates",
            "Civil and site-development estimating — earthwork, utilities, storm/sanitary, paving, curbs and site improvements. Quantity takeoffs and cost estimates. Nationwide.",
            ["Earthwork & grading", "Utilities (storm/sanitary/water)", "Asphalt & concrete paving",
             "Curbs & sidewalks", "Site improvements", "Quantity takeoffs & pricing"],
            ["Sitework", "Excavation", "Utilities", "Paving", "Landscaping"],
            "Civil and site-development contractors.",
            "Turn around more site bids with measured earthwork and utility quantities.")

    landing("multi-trade-estimating.html", "Multi-Trade Estimating",
            "Multi-trade estimating across every division",
            "Coordinated estimates spanning multiple trades and CSI divisions — organized into one bid-ready package.",
            "Multi-Trade Construction Estimating Services | Mobi Estimates",
            "Multi-trade construction estimating across all CSI divisions — coordinated takeoffs and pricing organized into one proposal-ready package for GCs. Nationwide.",
            ["Coordinated multi-trade takeoffs", "Labor, material & equipment pricing", "CSI division breakdown",
             "General conditions", "Bid leveling", "Proposal-ready summary"],
            ["Concrete", "Metals", "Carpentry", "Finishes", "MEP", "Sitework"],
            "General contractors managing several trades per bid.",
            "Hand off the whole package and get back one organized estimate.")


# ==========================================================================
# INDUSTRIES
# ==========================================================================
def build_industries():
    inds = [
        ("home", "Residential", "residential-estimating.html"),
        ("building", "Commercial", "commercial-estimating.html"),
        ("building2", "Multifamily", "multifamily-estimating.html"),
        ("truck", "Industrial", "construction-estimating-services.html"),
        ("layers", "Civil & Site", "civil-estimating.html"),
        ("cap", "Institutional", "construction-estimating-services.html"),
        ("refresh", "Renovation", "residential-estimating.html"),
        ("hammer", "New Construction", "construction-estimating-services.html"),
        ("wrench", "Tenant Improvement", "commercial-estimating.html"),
    ]
    cards = "".join(
        '<a class="card card-hover reveal" data-delay="%d" href="%s"><div class="icon-box">%s</div><h3>%s</h3><span class="tag" style="margin-top:14px">View %s</span></a>'
        % (i * 40, h, icon(ic), t, icon("arrow-ur")) for i, (ic, t, h) in enumerate(inds))
    body = page_hero(
        "Industries & project types",
        "Estimating for every sector of construction",
        "Mobi provides remote estimating support to contractors and construction companies throughout the United States — whatever you're bidding.",
        [("Industries", None)]
    ) + ('<section class="section"><div class="container"><div class="grid cols-3">%s</div></div></section>%s'
         % (cards, cta_band()))
    page("industries.html", "Industries & Project Types | Mobi Estimates",
         "Construction estimating across residential, commercial, multifamily, industrial, civil, institutional, renovation and new construction. Nationwide.",
         body, active="services")


# ==========================================================================
# HOW IT WORKS
# ==========================================================================
def build_how():
    steps = [
        ("Submit project files", "Upload your drawings, specifications, addenda, bid forms, scope, and deadline through the secure form.", "upload"),
        ("Scope review", "We review the documents, confirm the required services, and identify any missing information.", "doc-search"),
        ("Quote & schedule approval", "We confirm the exact price, deliverables, and turnaround — and you approve before any work begins.", "clipboard-check"),
        ("Estimate production", "We prepare quantities, labor, materials, equipment, and the requested bid breakdown.", "calculator"),
        ("Quality-control review", "Every estimate is checked for scope coverage, quantities, calculations, revisions, assumptions, and exclusions.", "shield"),
        ("Delivery & revision support", "You receive organized PDF and Excel deliverables, with revision support per your service or plan.", "check-circle"),
    ]
    big = "".join(
        '<div class="grid reveal" data-delay="%d" style="grid-template-columns:auto 1fr;gap:22px;align-items:start;padding:26px 0;border-bottom:1px solid var(--line)"><div class="num" style="font-family:Fraunces,serif;width:54px;height:54px;border-radius:14px;background:var(--navy-900);color:#fff;display:grid;place-items:center;font-size:1.2rem">%d</div><div><div class="flex items-center gap-2 mb-2"><span style="color:var(--brand-600)">%s</span><h3>%s</h3></div><p class="muted">%s</p></div></div>'
        % (i * 50, i + 1, icon(ic), t, d) for i, (t, d, ic) in enumerate(steps))
    body = page_hero(
        "How It Works",
        "From plans to a bid-ready estimate",
        "A simple, organized process with human quality control built in — and your price and schedule approved before any work begins.",
        [("How It Works", None)]
    ) + ('<section class="section"><div class="container" style="max-width:860px">%s</div></section>'
         '<section class="section band-alt"><div class="container"><div class="grid cols-3">%s</div></div></section>%s'
         % (big,
            "".join(feature_item(ic, t, d) for ic, t, d in [
                ("clock", "Fast turnaround", TURNAROUND_NOTE),
                ("shield", "Reviewed before delivery", "Every estimate goes through a structured quality-control review before it reaches you."),
                ("lock", "Confidential intake", "Your plans are used only to review, quote, and complete the requested estimating services."),
            ]),
            cta_band()))
    page("how-it-works.html", "How It Works | The Mobi Estimates Process",
         "How Mobi Estimates works: submit files, scope review, quote & schedule approval, estimate production, quality-control review, and delivery with revision support.",
         body, active="how")


# ==========================================================================
# ABOUT
# ==========================================================================
def build_about():
    body = page_hero(
        "About Mobi Estimates",
        "Estimating capacity built for growing contractors",
        "Mobi helps construction companies handle more bidding opportunities with a faster, more organized estimating process — without the burden of another hire.",
        [("About", None)]
    ) + '''
<section class="section">
  <div class="container">
    <div class="grid" style="grid-template-columns:1.1fr .9fr;gap:48px;align-items:center">
      <div class="reveal">
        <span class="eyebrow">Our approach</span>
        <h2 class="mt-2 mb-3">An estimating department you can scale</h2>
        <div class="stack" style="color:var(--slate-600)">
          <p>Contractors lose opportunities when bid invitations pile up faster than their teams can process them. Mobi was created to give construction companies dependable estimating capacity exactly when they need it.</p>
          <p>We combine estimating technology, standardized workflows, construction cost information, client-specific pricing, and human quality control to deliver professional estimates contractors can actually use.</p>
          <p>Use Mobi as an extension of your internal team or as your primary outsourced estimating resource — per project, or month to month.</p>
        </div>
      </div>
      <div class="reveal" data-delay="100"><div class="card"><h3 class="mb-3">What sets us apart</h3>%s</div></div>
    </div>
  </div>
</section>
%s
%s
%s''' % (
        check_list(["Capacity, not hourly labor", "Human-reviewed estimates", "Your pricing, markups & templates",
                    "Confidential file handling", "Per-project or monthly", "Nationwide coverage"]),
        founder_section(), qc_section(),
        cta_band("Let's talk about your bidding pipeline",
                 "Tell us how you bid today and we'll recommend the right estimating capacity.",
                 (CTA_PRIMARY[0], CTA_PRIMARY[1], "upload"), (CTA_CAPACITY[0], CTA_CAPACITY[1])))
    page("about.html", "About | Mobi Estimates",
         "Mobi Estimates provides outsourced construction estimating built for growing contractors — estimating technology, standardized workflows and human quality control. Nationwide.",
         body, active="about")


# ==========================================================================
# FAQ
# ==========================================================================
def build_faq():
    faqs = [
        ("Is there a free estimate for new companies?",
         "Yes. One qualifying estimate is free per genuinely new company, with no card required. Supported scope and project complexity are reviewed before acceptance."),
        ("How much does an estimate cost after the introductory offer?",
         "Regular options are Starter $995/month, Growth $1,995/month, Estimating Department $2,995/month, or Pay Per Project at $599 for one estimate."),
        ("What happens after the free qualifying estimate?",
         "Choose regular Pay Per Project or monthly pricing if you want Mobi to continue supporting your estimating workload. The introductory offer does not stack with another discount."),
        ("Can I purchase only one estimate?",
         "Yes. After the introductory offer, Pay Per Project is a one-time payment of $599 for one estimate and does not create a monthly subscription."),
        ("Where does Start Your Free Estimate take me?",
         "It takes you to the secure Mobi customer portal to create an account and submit a project for qualification review."),
        ("What is included in an estimate?",
         "Construction takeoffs with labor and material pricing, prepared with AI assistance and reviewed by people, delivered as contractor-ready Excel and PDF files."),
        ("What is the difference between monthly plans and Pay Per Project?",
         "Monthly plans provide ongoing estimating support billed month-to-month (cancel anytime). Pay Per Project is a single $599 one-time estimate with no subscription."),
        ("How is turnaround determined?",
         TURNAROUND_NOTE),
        ("Do you work with all construction trades?",
         "Yes. Mobi supports all major CSI divisions and construction trades — sitework, concrete, masonry, metals, carpentry, thermal and moisture, openings, finishes, MEP, and more."),
        ("What types of projects do you estimate?",
         "Residential, commercial, multifamily, industrial, civil, institutional, renovation, tenant-improvement, and ground-up new construction."),
        ("Can Mobi replace our internal estimator?",
         "Mobi can serve as your primary estimating resource or extend the capacity of your internal team. The right fit depends on your bid volume and goals — we'll help you decide."),
        ("Can Mobi use our labor rates and markups?",
         "Yes. We can use your client-provided labor rates, material prices, supplier quotes, production rates, overhead, and markup preferences."),
        ("What files should we upload?",
         "Plans, specifications, addenda, bid forms, scope notes, site information, and any supplier or subcontractor pricing. Accepted file types: " + ACCEPTED_FILE_TYPES + "."),
        ("Can monthly service be canceled?",
         CANCELLATION_POLICY),
        ("How are project documents protected?",
         "Your plans and project information are used only to review, quote, and complete the requested estimating services. We handle files confidentially and do not sell your project documents."),
        ("Do you guarantee that we will win the bid?",
         "No estimating company can guarantee that a contractor will win a project. Bid results depend on competition, qualifications, schedule, relationships, pricing strategy, project requirements, and other factors. Mobi provides organized, carefully reviewed estimates designed to help contractors submit bids efficiently and confidently."),
        ("Do you guarantee estimate accuracy?",
         "Every estimate is reviewed for scope coverage, quantities, calculations, drawing revisions, assumptions, exclusions, and formatting. Estimates are based on the plans, specifications, project information, and pricing inputs available at the time."),
    ]

    items_html = "".join(
        '<div class="faq-item reveal"><button class="faq-q" type="button" aria-expanded="false">%s<span class="chev">%s</span></button><div class="faq-a"><div class="inner">%s</div></div></div>'
        % (q, icon("chevron-down"), a) for q, a in faqs)
    body = page_hero(
        "Frequently asked questions",
        "Answers for contractors and construction teams",
        "Offer eligibility, regular pricing, scheduling, file handling, and how Mobi fits your workflow.",
        [("FAQ", None)]
    ) + ('<section class="section"><div class="container" style="max-width:820px">%s</div></section>%s'
         % (items_html,
            cta_band("Still have questions?",
                     "Compare the monthly plans and the one-time Pay Per Project option on the pricing page, then choose what fits.",
                     (CTA_PRIMARY[0], CTA_PRIMARY[1], "arrow-right"), (CTA_PRICING[0], CTA_PRICING[1]))))
    page("faq.html", "FAQ | Construction Estimating Questions | Mobi Estimates",
         "Answers about Mobi Estimates offer eligibility, regular pricing, scheduling, monthly capacity, file handling, revisions, and guarantees.",
         body, active="faq", schema_extra=faq_schema(faqs))


# ==========================================================================
# CONTACT
# ==========================================================================
def build_contact():
    info = [
        '<div class="card reveal"><div class="icon-box">%s</div><h3>Email</h3><p class="mt-2"><a href="mailto:%s" style="color:var(--brand-700);font-weight:600" data-analytics="email_click">%s</a></p></div>' % (icon("mail"), EMAIL, EMAIL),
        '<div class="card reveal" data-delay="80"><div class="icon-box">%s</div><h3>Service area</h3><p class="mt-2 muted">Remote estimating nationwide, across the United States.</p></div>' % icon("globe"),
        '<div class="card reveal" data-delay="160"><div class="icon-box">%s</div><h3>Upload plans</h3><p class="mt-2 muted">The fastest way to start — get a free scope review and exact quote.</p></div>' % icon("upload"),
    ]
    if SCHEDULING_URL:
        info.append('<div class="card reveal" data-delay="240"><div class="icon-box">%s</div><h3>Book a call</h3><p class="mt-2"><a href="%s" style="color:var(--brand-700);font-weight:600" data-analytics="schedule_click">Schedule a capacity call</a></p></div>' % (icon("calendar"), SCHEDULING_URL))
    cols = "cols-4" if SCHEDULING_URL else "cols-3"

    form = '''<form class="form-card" id="contactForm" data-form data-analytics-form="contact" novalidate>
  <div class="form-grid">%s%s</div>
  <div class="form-grid">%s%s</div>
  %s
  %s
  %s
</form>%s''' % (
        field("First name", "first_name", required=True, autocomplete="given-name"),
        field("Last name", "last_name", required=True, autocomplete="family-name"),
        field("Company", "company", autocomplete="organization"),
        field("Email", "email", "email", required=True, autocomplete="email"),
        field("Phone (optional)", "phone", "tel", autocomplete="tel"),
        textarea_field("How can we help?", "message", required=True, placeholder="Tell us about your project or estimating needs."),
        btn("Send Message", "#", "primary", "arrow-right", "lg", cls="btn-block", data="contact_submit", attrs="data-submit"),
        form_success("Thanks — we'll be in touch",
                     "The Mobi team will review your message and respond about scope, turnaround, and pricing."))

    body = page_hero(
        "Contact",
        "Let's talk about your next bid",
        "Send a message, or upload your plans for a free scope review. We'll get back to you about scope, turnaround, and pricing.",
        [("Contact", None)]
    ) + '''
<section class="section">
  <div class="container">
    <div class="grid %s mb-6">%s</div>
    <div class="grid" style="grid-template-columns:.8fr 1.2fr;gap:48px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">Fastest way to start</span>
        <h2 class="mt-2 mb-3">Upload your plans</h2>
        <p class="muted mb-4">Ready to send a project now? Upload your plans and we'll take it from there.</p>
        <div class="grid" style="gap:10px">%s%s</div>
      </div>
      <div class="reveal" data-delay="80">%s</div>
    </div>
  </div>
</section>''' % (cols, "".join(info),
                 btn(CTA_UPLOAD[0], "upload-plans.html", "primary", "upload", cls="btn-block", data="contact_upload"),
                 btn(CTA_PRICING[0], CTA_PRICING[1], "outline", cls="btn-block"),
                 form)
    page("contact.html", "Contact | Mobi Estimates",
         "Contact Mobi Estimates. Send a message or upload your plans for a free construction estimating scope review and exact quote. Remote estimating nationwide.",
         body, active="contact")


# ==========================================================================
# LEGAL
# ==========================================================================
def legal_page(filename, eyebrow, h1, intro, sections, seo_title, seo_desc, review_note=True):
    inner = ""
    for heading, paras in sections:
        inner += "<h2>%s</h2>" % heading
        for p in paras:
            if isinstance(p, list):
                inner += "<ul>" + "".join("<li>%s</li>" % li for li in p) + "</ul>"
            else:
                inner += "<p>%s</p>" % p
    note = ('<div class="card mt-8" style="background:var(--bg-alt);border:none"><p class="muted" style="margin:0;font-size:.92rem">This page is provided for general information and is not legal advice. It should be reviewed by a qualified attorney before relying on it. It has not been attorney-reviewed.</p></div>') if review_note else ""
    body = page_hero(eyebrow, h1, intro, [(h1, None)]) + (
        '<section class="section"><div class="container"><div class="prose reveal">'
        '<p class="muted" style="font-size:.9rem">Last updated: June 2026</p>%s%s</div></div></section>'
        % (inner, note))
    page(filename, seo_title, seo_desc, body, robots="index, follow")


def build_legal():
    legal_page(
        "privacy.html", "Legal", "Privacy Policy",
        "How Mobi Estimates collects, uses and protects the information and documents you share with us.",
        [
            ("Information we collect", ["Work-email offer captures, contact-form data (name, company, email, phone), marketing attribution fields, quote-request details, and the project documents you upload (plans, specs, addenda, bid forms, and related materials).",
                                        "Limited technical/usage data may be collected automatically to operate and improve the website."]),
            ("How we use information", ["To respond to estimate requests, review introductory-offer eligibility and scope, support portal onboarding, communicate about projects and related Mobi services, and improve our services."]),
            ("Uploaded project documents", ["Your documents are used only to review, quote, and complete the requested estimating services. We do not sell your project documents."]),
            ("File handling", ["Files are handled confidentially and retained only as long as needed to deliver and support your estimate, unless a longer period is required by law or agreement."]),
            ("Analytics", ["We may use privacy-respecting analytics to understand site usage. No analytics tag is loaded unless configured."]),
            ("Communications", ["If you submit a work email or service request, we may contact you about that request, your project, your account, and related Mobi services. You can unsubscribe from non-essential communications at any time."]),
            ("Data retention", ["We retain personal data and documents only as long as necessary for the purposes described here or as required by law."]),
            ("Third-party service providers", ["We may use service providers for website and portal hosting, database and file storage, and approved communications. They process data on our behalf under appropriate confidentiality obligations."]),
            ("Security limitations", ["We use reasonable safeguards, but no method of transmission or storage is completely secure, and we cannot guarantee absolute security."]),
            ("Your requests", ["You may request access to, correction of, or deletion of your personal information by emailing %s." % EMAIL]),
            ("Contact", ["Questions about this policy? Email %s." % EMAIL]),
        ],
        "Privacy Policy | Mobi Estimates",
        "How Mobi Estimates collects, uses, retains and protects your information and uploaded project documents.")

    legal_page(
        "terms.html", "Legal", "Terms of Service",
        "The terms that govern your use of the Mobi Estimates website and services.",
        [
            ("Acceptance of terms", ["By using this website or our services, you agree to these Terms. If you do not agree, please do not use the website or services."]),
            ("Estimates are based on supplied documents", ["Estimates are prepared using the plans, specifications, project information, and pricing inputs available at the time. The quality and completeness of the documents you provide directly affect the estimate."]),
            ("Customer review responsibility", ["You are responsible for reviewing each estimate and confirming project requirements before submitting a bid or entering a contract."]),
            ("Market prices may change", ["Material, labor, and equipment prices fluctuate. Estimates reflect available pricing inputs at the time of preparation."]),
            ("Scope changes", ["Changes to scope, drawings, addenda, or deliverables may affect price and delivery schedule."]),
            ("Revisions", ["Project-based estimates include one revision round. Monthly plans include revision support per the selected plan."]),
            ("Monthly plan capacity & standard bids", ["Monthly subscriptions reserve estimating capacity and workflow support; they are not unlimited-use plans.", STANDARD_BID_DEF, "Larger or more complex projects may use additional capacity, confirmed during onboarding and project review."]),
            ("No guaranteed bid awards", ["We do not guarantee bid awards or that an estimate eliminates all project risk. Bid results depend on factors outside our control."]),
            ("Payment terms", ["Project-based work is quoted and approved before work begins. Monthly plans are billed in advance, month to month. [Owner to confirm payment processor and terms.]"]),
            ("Cancellation", [CANCELLATION_POLICY]),
            ("Confidentiality", ["We handle your project documents confidentially and use them only to deliver the requested services."]),
            ("Intellectual property", ["Website content is owned by Mobi Estimates or its licensors. Deliverables prepared for you may be used for your project and bidding purposes as agreed."]),
            ("Limitation of liability", ["To the maximum extent permitted by law, Mobi Estimates is not liable for indirect, incidental, or consequential damages arising from use of the website, services, or deliverables."]),
            ("Disputes & governing law", ["These terms are governed by the laws of %s. [Dispute-resolution terms to be finalized by the owner with legal counsel.]" % GOVERNING_LAW]),
            ("Changes", ["We may update these terms; continued use constitutes acceptance of the updated terms."]),
            ("Contact", ["Questions? Email %s." % EMAIL]),
        ],
        "Terms of Service | Mobi Estimates",
        "Terms governing use of the Mobi Estimates website and construction estimating services, including estimate basis, revisions, monthly capacity, and guarantees.")

    legal_page(
        "disclaimer.html", "Legal", "Estimating Disclaimer",
        "Important information about the nature and limitations of our estimates.",
        [
            ("Nature of our estimates", ["Estimates are prepared using available construction documents, project information, client-provided pricing, cost data, and professional estimating procedures. Every estimate is reviewed before delivery."]),
            ("No guarantees", ["We do not represent that estimates are 100% accurate, error-free, or guaranteed. We do not guarantee bid awards, the lowest price, savings, revenue, or that an estimate will match final actual costs.",
                               ["Estimates depend on the quality and completeness of documents provided", "Market conditions and pricing change over time", "Final costs depend on factors outside the estimator's control"]]),
            ("Not professional design services", ["Mobi provides construction estimating and takeoff services only. We do not provide architectural, engineering, legal, or other licensed professional services, and our deliverables do not replace work performed by a licensed professional."]),
            ("Value engineering", ["Value-engineering suggestions identify potential cost-saving options. They are not architectural or engineering design and should be reviewed and approved by appropriate licensed professionals before implementation."]),
            ("Your responsibility", ["You are responsible for reviewing each estimate, verifying scope and quantities for your project, and making your own pricing and bidding decisions."]),
            ("Contact", ["Questions about this disclaimer? Email %s." % EMAIL]),
        ],
        "Estimating Disclaimer | Mobi Estimates",
        "The nature, scope, and limitations of Mobi Estimates construction estimates and takeoff deliverables.")


# ==========================================================================
# Sitemap + robots
# ==========================================================================
def write_sitemap(pages):
    urls = ""
    for p in pages:
        loc = CANONICAL_BASE + "/" + ("" if p == "index.html" else p)
        urls += "  <url><loc>%s</loc></url>\n" % loc
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</urlset>\n' % urls)
    with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(xml)


def write_robots():
    txt = "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % CANONICAL_BASE
    with open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(txt)


# ==========================================================================
# BUILD ALL
# ==========================================================================
def main():
    build_home()
    build_services()
    build_service_details()
    build_landing_pages()
    build_pricing()
    build_sample_estimate()
    build_capacity_plan()
    build_upload_plans()
    build_industries()
    build_how()
    build_about()
    build_faq()
    build_contact()
    build_legal()

    # Redirect old quote/upload URLs to the new upload-plans page
    redirect_stub("request-a-quote.html", "upload-plans.html")
    redirect_stub("upload-project.html", "upload-plans.html")

    # Remove the unfinished client login page if present
    login = os.path.join(OUT, "login.html")
    if os.path.exists(login):
        os.remove(login)

    indexable = [f for f in sorted(os.listdir(OUT))
                 if f.endswith(".html") and f not in ("request-a-quote.html", "upload-project.html")]
    write_sitemap(indexable)
    write_robots()

    html_files = [f for f in sorted(os.listdir(OUT)) if f.endswith(".html")]
    print("Generated %d HTML pages + sitemap.xml + robots.txt" % len(html_files))
    for f in html_files:
        print("  -", f)


if __name__ == "__main__":
    main()
