#!/usr/bin/env python3
"""Page content + site build for FleetBuilt Partners. Run: python3 generate.py"""
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
        ("truck", "You supply the trucks"),
        ("cap", "Internal training path"),
        ("shield", "You remain the provider"),
        ("flag", SCOPE_LINE),
        ("clipboard-check", "Launch support only"),
    ]
    chips = "".join('<span class="chip">%s %s</span>' % (icon(ic), t) for ic, t in items)
    return '''<section class="section-tight band-alt">
  <div class="container"><div class="trust-strip reveal">%s</div></div>
</section>''' % chips


def video_media():
    """Return the inner media for the explainer video block.

    Blank EXPLAINER_VIDEO_URL -> clearly-marked TEMPORARY branded placeholder.
    A configured URL -> native <video> (for file paths) or a lazy responsive
    iframe (for YouTube/Vimeo/Wistia embeds). One field controls all of this.
    """
    url = (EXPLAINER_VIDEO_URL or "").strip()
    if not url:
        return '''<div class="video-frame video-placeholder" role="img"
     aria-label="FleetBuilt explainer video — final version arrives soon">
  <span class="vp-badge">Temporary preview · final explainer video coming soon</span>
  <div class="vp-center">
    <span class="video-play vp-static" aria-hidden="true"><i class="vp-tri"></i></span>
    <img class="vp-logo" src="%s" alt="" aria-hidden="true" width="220" height="72">
    <p class="vp-caption">A short walkthrough of Blueprint-to-implementation launch support.</p>
  </div>
</div>''' % LOGO_HORIZONTAL

    lower = url.lower()
    if lower.endswith((".mp4", ".webm", ".ogg", ".mov")):
        poster = ' poster="%s"' % EXPLAINER_VIDEO_POSTER if EXPLAINER_VIDEO_POSTER else ""
        return ('<div class="video-frame">'
                '<video class="video-embed" controls preload="none"%s '
                'playsinline aria-label="%s">'
                '<source src="%s"></video></div>') % (poster, EXPLAINER_VIDEO_HEADING, url)

    embed = url
    if "youtube.com/watch?v=" in lower:
        embed = "https://www.youtube-nocookie.com/embed/" + url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in lower:
        embed = "https://www.youtube-nocookie.com/embed/" + url.rsplit("/", 1)[1].split("?")[0]
    elif "vimeo.com/" in lower and "player.vimeo" not in lower:
        embed = "https://player.vimeo.com/video/" + url.rstrip("/").rsplit("/", 1)[1]
    return ('<div class="video-frame"><iframe class="video-embed" src="%s" '
            'title="%s" loading="lazy" frameborder="0" '
            'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
            'allowfullscreen></iframe></div>') % (embed, EXPLAINER_VIDEO_HEADING)


def video_section():
    return '''<section class="section band-alt" id="explainer-video">
  <div class="container">
    <div class="center reveal" style="max-width:760px;margin-inline:auto">
      <span class="eyebrow">Explainer overview</span>
      <h2 class="mt-2">%s</h2>
      <p class="lead mt-3">%s</p>
    </div>
    <div class="video-wrap reveal-scale mt-8">%s</div>
  </div>
</section>''' % (EXPLAINER_VIDEO_HEADING, EXPLAINER_VIDEO_SUBHEAD, video_media())


def comparison_table():
    rows = [
        ("You remain the training provider", "Varies", "Yes", "Yes"),
        ("Maps an internal build path", "No", "Varies", "Included"),
        ("Scoped to one site / class", "Varies", "Varies", "Included"),
        ("Launch-support engagement", "No", "Varies", "Included"),
        ("Operates the school for you", "Sometimes", "No", "No"),
        ("Promises approval or hiring results", "Varies", "Varies", "No"),
        ("Written Blueprint first", "No", "Varies", "Included"),
        ("Founding implementation option", "No", "Varies", "Available"),
        ("Third-party costs called out", "Varies", "Varies", "Included"),
        ("Credit Blueprint toward founding", "No", "No", "Available"),
    ]

    def cell(v, brand=False):
        pos = v in ("Yes", "Included", "Available")
        neg = v == "No"
        cls = "pos" if pos else ("neg" if neg else "neu")
        ic = icon("check") if pos else (icon("x-circle") if neg else icon("minus"))
        return '<td class="%s%s" data-label="">%s<span>%s</span></td>' % (
            cls, " brand" if brand else "", ic, v)

    body = ""
    for label, a, b, c in rows:
        body += ('<tr><th scope="row">%s</th>%s%s%s</tr>'
                 % (label, cell(a).replace('data-label=""', 'data-label="External CDL school"'),
                    cell(b).replace('data-label=""', 'data-label="Recruit-only path"'),
                    cell(c, True).replace('data-label=""', 'data-label="FleetBuilt Partners"')))
    return '''<div class="table-wrap reveal">
  <table class="compare-table">
    <thead><tr><th scope="col">Capability</th><th scope="col">External CDL school</th><th scope="col">Recruit-only path</th><th scope="col" class="brand-col">FleetBuilt Partners</th></tr></thead>
    <tbody>%s</tbody>
  </table>
</div>
<p class="muted" style="font-size:.85rem;margin-top:14px">Labels are general guidance. FleetBuilt is launch support for an employer-owned path — not a claim about every school, recruiter, or fleet.</p>''' % body


def deliverables_section():
    items = [
        "Feasibility snapshot", "Decision memo", "Gap list", "Role outline",
        "Record-keeping checklist", "Third-party cost categories", "Site/class scope lock",
        "Recommended sequence", "Working-session notes", "Implementation milestones",
        "Owner-decision log", "What you must still own",
    ]
    return '''<section class="section band-dark">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow on-dark">What you receive</span>
      <h2 class="mt-2">Organized deliverables for a scoped launch-support engagement</h2>
    </div>
    <div class="mt-8">%s</div>
  </div>
</section>''' % check_list(items, "cols-3")


def fit_section():
    good = ["You already have trucks and a hiring need", "External school calendars keep slipping",
            "Retention suffers after you finally find a licensed driver",
            "You want a path to train people inside the operation",
            "You can own the regulated provider role", "You want a written build path first",
            "You can stay inside one site and one CDL class for founding work",
            "You want launch support — not someone else to run the school"]
    bad = ["You want us to operate the CDL school for you", "You need guaranteed approval or a published opening date",
           "You expect hiring results, pass rates, or ROI promises",
           "You need multi-state or multi-class founding work in one fee",
           "You want a vendor-owned school we run for you",
           "You need us to market that we train your hire"]
    good_li = "".join('<li>%s<span>%s</span></li>' % (icon("check-circle"), g) for g in good)
    bad_li = "".join('<li>%s<span>%s</span></li>' % (icon("x-circle"), b) for b in bad)
    return '''<section class="section">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">Is FleetBuilt a fit?</span>
      <h2 class="mt-2">Honest about where we help — and where we don't</h2>
    </div>
    <div class="grid cols-2 mt-8" style="gap:24px">
      <div class="card reveal">
        <h3 class="mb-3">FleetBuilt is a strong fit when</h3>
        <ul class="check-list">%s</ul>
      </div>
      <div class="card reveal" data-delay="80">
        <h3 class="mb-3">FleetBuilt may not be the right fit when</h3>
        <ul class="check-list neg-list">%s</ul>
      </div>
    </div>
  </div>
</section>''' % (good_li, bad_li)


def founder_section():
    trust = [
        ("shield", "You remain the provider"), ("clipboard-check", "Scoped before work begins"),
        ("doc-text", "Written Blueprint first"), ("lock", "Confidential operating notes"),
        ("layers", "Clear what you still own"), ("dollar", "Locked $2,500 / $15,000 fees"),
        ("flag", "One site, one class"), ("globe", "Nationwide conversation"),
    ]
    cards = "".join('<div class="trust-card reveal" data-delay="%d"><span class="ti">%s</span><span>%s</span></div>'
                    % (i * 40, icon(ic), t) for i, (ic, t) in enumerate(trust))
    founder_block = ""
    if FOUNDER.get("name"):
        photo = ('<img src="assets/img/%s" alt="%s, founder of %s" style="width:96px;height:96px;border-radius:16px;object-fit:cover">'
                 % (FOUNDER["photo"], FOUNDER["name"], SITE_NAME)) if FOUNDER.get("photo") else ""
        bits = []
        for key in ("construction_experience", "estimating_experience", "software", "location"):
            if FOUNDER.get(key):
                bits.append("<li>%s</li>" % FOUNDER[key])
        founder_block = '''<div class="card reveal" style="display:flex;gap:18px;align-items:flex-start">
          %s<div>%s<h3 style="margin-top:6px">%s</h3><p class="muted mt-2">%s</p>%s</div>
        </div>''' % (photo, "", FOUNDER["name"], FOUNDER.get("bio", ""),
                     ("<ul class='check-list mt-3'>" + "".join(bits) + "</ul>") if bits else "")
    else:
        founder_block = "<!-- FOUNDER NOT YET CONFIGURED: set FOUNDER fields in config.py to publish a founder card here. -->"

    return '''<section class="section band-alt">
  <div class="container">
    <div class="grid" style="grid-template-columns:1fr 1fr;gap:40px;align-items:center">
      <div class="reveal">
        <span class="eyebrow">Why FleetBuilt exists</span>
        <h2 class="mt-2 mb-3">A build path when hiring stays expensive</h2>
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
    items = ["Scope lock (employer / site / state / class)", "What you must still own",
             "Third-party cost categories", "Gap list completeness",
             "Decision memo review", "Milestone wording check",
             "No approval or hiring-result claims", "Deliverable-formatting review"]
    return '''<section class="section">
  <div class="container">
    <div class="grid" style="grid-template-columns:.9fr 1.1fr;gap:48px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">Quality control</span>
        <h2 class="mt-2 mb-3">Every package is reviewed before it reaches you</h2>
        <p class="muted">Deliverables are prepared from the information you share. You remain responsible for regulatory filings, instructor qualifications, and the training operation itself. FleetBuilt does not certify, approve, or operate your school.</p>
      </div>
      <div class="card reveal" data-delay="80">%s</div>
    </div>
  </div>
</section>''' % check_list(items, "cols-2")


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
    return ('<div class="field"><label>Optional background files</label>'
            '<div class="dropzone"><input id="%s" type="file" name="%s" multiple hidden>'
            '<div style="display:grid;gap:6px;place-items:center">%s'
            '<strong class="dz-label">Drop notes or org documents here, or click to browse</strong>'
            '<span class="hint">Accepted: %s</span><span class="hint">%s</span></div></div>'
            '<p class="confidential">%s Files are used only to understand your operation and prepare launch-support work. They are not a filing we submit for you.</p></div>'
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
    return '''<section class="section band-alt" id="blueprint">
  <div class="container">
    <div class="grid cols-2" style="gap:32px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">Feasibility Blueprint · $2,500</span>
        <h2 class="mt-2">%s</h2>
        <p class="lead mt-3">%s</p>
        <p class="muted mt-3">%s</p>
        <p class="muted mt-2">%s</p>
        <div class="mt-5">%s</div>
      </div>
      <div class="card reveal" data-delay="80">
        <h3>Prefer email? Reach Moses directly.</h3>
        <form data-lead-form novalidate style="margin-top:18px">
          <label class="field"><span>Work email</span><input type="email" name="email" autocomplete="email" maxlength="320" placeholder="you@yourfleet.com" required></label>
          <label aria-hidden="true" style="position:absolute;left:-10000px"><span>Company website</span><input name="company_website" tabindex="-1" autocomplete="off"></label>
          <button class="btn btn-primary btn-block" type="submit" style="margin-top:12px">Request a Blueprint conversation</button>
          <p class="hint mt-3">By submitting, you agree FleetBuilt Partners may contact you about Blueprint or founding-implementation support. You can unsubscribe at any time. <a href="privacy.html">Privacy policy</a>.</p>
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
        ("1", "Conversation", "We confirm employer, site, state, and CDL class."),
        ("2", "Blueprint", "A written feasibility package for that locked scope."),
        ("3", "Your decision", "You decide whether founding work is worth contracting."),
        ("4", "Implementation", "Milestone-based launch support if you proceed."),
        ("5", "You operate", "You remain the regulated training provider."),
    ]
    cards = "".join(
        '<div class="card reveal" data-delay="%d"><span class="eyebrow">Step %s</span><h3 class="mt-2">%s</h3><p>%s</p></div>'
        % (i * 50, n, title, desc) for i, (n, title, desc) in enumerate(milestones)
    )
    return '''<section class="section">
  <div class="container">
    <div class="center reveal" style="max-width:760px;margin-inline:auto">
      <span class="eyebrow">How the work moves</span>
      <h2 class="mt-2">A visible sequence — no opening-date promise</h2>
      <p class="lead mt-3">Customer-safe milestones only. Timing depends on your decisions and on work that stays yours.</p>
    </div>
    <div class="grid cols-3 mt-8">%s</div>
  </div>
</section>''' % cards


def home_followup_section():
    return '''<section class="section band-alt">
  <div class="container">
    <div class="grid cols-2" style="gap:36px;align-items:center">
      <div class="reveal">
        <span class="eyebrow">After the Blueprint</span>
        <h2 class="mt-2">A credit if you move to founding work</h2>
        <p class="lead mt-3">%s</p>
      </div>
      <div class="card reveal" data-delay="80">
        <h3>Support — not a result we can promise</h3>
        <p class="mt-3">%s</p>
      </div>
    </div>
  </div>
</section>''' % (CREDIT_NOTE, COMPLIANCE_NOTE)


def home_collaboration_section():
    cards = [
        ("Lock the scope in writing", "One employer, one site, one state, and one CDL class stay visible so founding work does not quietly expand."),
        ("Keep decisions attached to the project", "Your choices about people, space, and third parties stay in the working notes."),
        ("You stay the operator", "Launch support organizes the path. You remain the regulated training provider."),
    ]
    items = "".join(
        '<div class="card card-hover reveal" data-delay="%d"><span class="eyebrow">0%d</span><h3 class="mt-3">%s</h3><p>%s</p></div>'
        % (i * 70, i + 1, title, body) for i, (title, body) in enumerate(cards)
    )
    return '''<section class="section" id="collaboration">
  <div class="container">
    <div class="center reveal" style="max-width:760px;margin-inline:auto">
      <span class="eyebrow">Employer-controlled collaboration</span>
      <h2 class="mt-2">Your operation stays yours</h2>
      <p class="lead mt-3">FleetBuilt helps you organize a build path. We do not take over as the school, and we do not market that we train your hire.</p>
    </div>
    <div class="grid cols-3 mt-8">%s</div>
  </div>
</section>''' % items


def home_multitrade_section():
    pains = [
        "CDL hiring stays expensive", "External school lag", "Idle trucks waiting on a license",
        "Retention after you finally hire", "Unclear build path", "No internal training sequence",
    ]
    return '''<section class="section band-dark" id="problems">
  <div class="container">
    <div class="grid cols-2" style="gap:48px;align-items:center">
      <div class="reveal">
        <span class="eyebrow on-dark">What fleets run into</span>
        <h2 class="mt-2">The cost is not only an empty seat</h2>
        <p class="lead mt-3" style="color:#cdddf7">Searching the market for licensed drivers, waiting on an outside school, and watching trucks sit are familiar pressures. FleetBuilt helps you map an inside path — without promising that hiring gets easier overnight.</p>
      </div>
      <div class="card reveal" data-delay="80">%s</div>
    </div>
  </div>
</section>''' % check_list(pains, "cols-2")


def home_hiring_comparison_section():
    return '''<section class="section band-alt" id="compare-hiring">
  <div class="container">
    <div class="center reveal" style="max-width:760px;margin-inline:auto">
      <span class="eyebrow">A path besides search-and-wait</span>
      <h2 class="mt-2">Develop training capacity without handing the school to someone else</h2>
      <p class="lead mt-3">FleetBuilt is launch support for an employer-owned academy — not a replacement for your regulatory responsibilities.</p>
    </div>
    <div class="grid cols-2 mt-8">
      <div class="card reveal"><h3>Keep searching the market</h3>%s</div>
      <div class="card reveal" data-delay="80"><h3>Map an internal path</h3>%s</div>
    </div>
  </div>
</section>''' % (
        check_list(["External school calendars you do not control", "Recruiting cost with no training path", "Idle equipment while you wait", "Unclear next step after you decide to build"]),
        check_list(["Written Blueprint for one scoped site", "Founding implementation if you proceed", "You remain the training provider", "Third-party costs called out as additional"]),
    )


def home_faq_section():
    items = [
        ("What does the Blueprint cost?", INTRO_OFFER_SUMMARY + " " + CREDIT_NOTE),
        ("Do you operate the CDL school?", "No. You remain the regulated training provider. FleetBuilt provides launch support only. " + LOGO_NOTE),
        ("Do you promise approval or hiring results?", "No. We do not promise approval, ROI, opening dates, pass rates, or hiring results."),
        ("What is the founding scope?", INTRO_OFFER_REVIEW),
        ("How do I start?", "Email moses@fleetbuiltpartners.com or use the contact form. There is no live self-serve checkout yet."),
    ]
    rows = "".join('<details class="faq-item reveal"><summary>%s</summary><div class="faq-answer"><p>%s</p></div></details>' % item for item in items)
    return '''<section class="section" id="faq">
  <div class="container" style="max-width:900px">
    <div class="center reveal"><span class="eyebrow">Common questions</span><h2 class="mt-2">What employers should know before starting</h2></div>
    <div class="mt-8">%s</div>
  </div>
</section>''' % rows


def logo_strip():
    if not CUSTOMER_LOGOS:
        return "<!-- credibility/customer-logo strip: structure ready; hidden until real, verifiable logos are added to CUSTOMER_LOGOS in config.py -->"
    items = "".join(
        '<img class="cl-logo" src="%s" alt="%s" loading="lazy">' % (l["src"], l["alt"])
        for l in CUSTOMER_LOGOS)
    return '''<section class="section-tight logo-strip-section">
  <div class="container">
    <p class="logo-strip-label">Employers building an internal training path</p>
    <div class="logo-strip">%s</div>
  </div>
</section>''' % items


def testimonials_section():
    if not TESTIMONIALS:
        return "<!-- testimonials: structure ready; hidden until real, attributable customer testimonials are added to TESTIMONIALS in config.py -->"
    cards = "".join(
        '<figure class="quote-card reveal" data-delay="%d"><blockquote>%s</blockquote>'
        '<figcaption class="who"><span class="avatar">%s</span><span><strong>%s</strong>'
        '<span>%s%s</span></span></figcaption></figure>'
        % (i * 70, t["quote"], (t.get("name") or "")[:1], t.get("name", ""),
           t.get("role", ""), (" · " + t["company"]) if t.get("company") else "")
        for i, t in enumerate(TESTIMONIALS))
    return '''<section class="section band-alt">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">In their words</span>
      <h2 class="mt-2">What employers say about working with FleetBuilt</h2>
    </div>
    <div class="grid cols-3 mt-8">%s</div>
  </div>
</section>''' % cards


def home_value_capability():
    caps = [
        ("doc-search", "Feasibility Blueprint", "A written snapshot for one employer, one site, one state, and one CDL class."),
        ("clipboard-check", "Founding implementation", "Milestone-based launch support after you decide the path is worth building."),
        ("flag", "Locked scope", "Founding work does not quietly expand into a second site or class."),
        ("shield", "You remain the provider", "We organize launch support. We do not operate your CDL school."),
        ("layers", "What you still own", "Filings, instructors, range time, and day-to-day training stay with you."),
        ("dollar", "Locked fees", "$2,500 Blueprint. $15,000 founding implementation. Third-party costs additional."),
    ]
    cap_html = "".join(feature_item(ic, t, d, i * 40) for i, (ic, t, d) in enumerate(caps))
    return '''<section class="section">
  <div class="container">
    <div class="vp-grid">
      <div class="reveal">
        <span class="eyebrow">What you get</span>
        <h2 class="mt-2">A Blueprint, then founding implementation if you proceed</h2>
        <p class="lead mt-3">FleetBuilt Partners helps you map and stand up an internal CDL training operation. We provide launch support only — not a school we run, and not a promise of approval or hiring results.</p>
        <div class="mt-5">%s</div>
      </div>
      <figure class="product-frame reveal-scale">
        <img src="%s" alt="FleetBuilt Partners mark: an isometric truck with a green graduation cap, and the FleetBuilt Partners wordmark" width="1152" height="864" loading="lazy">
      </figure>
    </div>
    <div class="grid cols-3 mt-8 capability-grid">%s</div>
  </div>
</section>''' % (btn(CTA_JOIN[0], CTA_JOIN[1], "primary", data="value_join"), LOGO_STACKED, cap_html)


def home_final_cta():
    return '''<section class="section final-cta">
  <div class="container">
    <div class="final-cta-inner reveal">
      <span class="eyebrow">Get started</span>
      <h2 class="mt-2">Discuss a Feasibility Blueprint</h2>
      <p class="lead mt-3">%s %s</p>''' % (INTRO_OFFER_SUMMARY, INTRO_OFFER_REVIEW) + '''
      <div class="final-cta-actions mt-5">%s</div>
      <form class="final-lead" data-lead-form novalidate>
        <p class="final-lead-label">Prefer email? Send a note and we will follow up.</p>
        <div class="final-lead-row">
          <label class="sr-only" for="finalLeadEmail">Work email</label>
          <input id="finalLeadEmail" type="email" name="email" autocomplete="email" maxlength="320" placeholder="you@yourfleet.com" required>
          <label aria-hidden="true" class="hp-field"><span>Company website</span><input name="company_website" tabindex="-1" autocomplete="off"></label>
          <button class="btn btn-primary" type="submit">Request a conversation</button>
        </div>
        <p class="hint mt-3">By submitting, you agree FleetBuilt Partners may contact you about Blueprint or founding-implementation support. You can unsubscribe at any time. <a href="privacy.html">Privacy policy</a>.</p>
        <p class="hint mt-2" data-lead-status role="status" aria-live="polite"></p>
      </form>
    </div>
  </div>
</section>''' % btn(CTA_JOIN[0], CTA_JOIN[1], "primary", data="final_join")


def build_home():
    body = '''
<section class="hero">
  <div class="hero-bg" aria-hidden="true"></div>
  <div class="container hero-inner">
    <div class="hero-text reveal">
      <span class="eyebrow on-dark">CDL academy launch support</span>
      <h1 class="hero-title">You supply the trucks. We help you build the training operation.</h1>
      <p class="hero-lead">Stop searching for CDL drivers. Start developing a path to train them inside your operation. FleetBuilt Partners provides launch support for an employer-owned academy — you remain the regulated training provider.</p>
      <div class="hero-actions">
        %s
        <a class="hero-secondary" href="#explainer-video" data-analytics="hero_how">See how FleetBuilt works %s</a>
      </div>
      <p class="hero-note">Feasibility Blueprint $2,500&nbsp; ·&nbsp; Founding implementation $15,000&nbsp; ·&nbsp; %s</p>
      <p class="hero-fineprint">%s %s</p>
    </div>
    <figure class="hero-media reveal-scale" id="explainer-video">
      <h2 class="sr-only">%s</h2>
      <p class="sr-only">%s</p>
      %s
    </figure>
  </div>
</section>

%s

%s

%s

%s

%s
''' % (
        btn(CTA_JOIN[0], CTA_JOIN[1], "primary", data="hero_join"),
        icon("arrow-right"),
        SCOPE_LINE,
        COMPLIANCE_NOTE,
        LOGO_NOTE,
        EXPLAINER_VIDEO_HEADING,
        EXPLAINER_VIDEO_SUBHEAD,
        video_media(),
        logo_strip(),
        home_value_capability(),
        testimonials_section(),
        home_multitrade_section(),
        home_final_cta(),
    )
    page("index.html",
         "FleetBuilt Partners | Internal CDL academy launch support",
         "You supply the trucks. We help you build the training operation. Feasibility Blueprint $2,500. Founding implementation $15,000. You remain the regulated training provider.",
         body, active="")


def home_bars():
    rows = [("Hiring cost", 62), ("School lag", 78), ("Idle trucks", 45), ("Unclear path", 88)]
    return "".join(
        '<div class="ec-row"><span>%s %s</span><div class="bar"><i style="width:%d%%"></i></div></div>'
        % (icon("truck"), name, pct) for name, pct in rows)


def home_process_steps():
    steps = [
        ("Share how you operate today", "Tell us the employer, site, state, CDL class, and where hiring breaks down."),
        ("Receive the Blueprint", "A written feasibility package for that locked scope — not an approval."),
        ("Decide on founding work", "If you contract the same scoped project within 60 days, the Blueprint fee is credited."),
    ]
    return "".join(
        '<div class="step reveal" data-delay="%d"><div class="num">%d</div><h3>%s</h3><p>%s</p></div>'
        % (i * 70, i + 1, t, d) for i, (t, d) in enumerate(steps))


def home_pricing_preview():
    cards = [
        ("Feasibility Blueprint", "$2,500", "A written path for one scoped internal academy.", "pricing.html#blueprint"),
        ("Founding implementation", "$15,000 total", "Launch support after you decide to build.", "pricing.html#founding"),
        ("60-day Blueprint credit", "Same scoped project", "Credited toward founding if contracted within 60 days of delivery.", "pricing.html"),
    ]
    cells = "".join(
        '<a class="card card-hover reveal price-preview" data-delay="%d" href="%s"><div class="pp-name">%s</div><div class="pp-price">%s</div><p>%s</p><span class="tag" style="margin-top:14px">See details %s</span></a>'
        % (i * 70, h, n, p, d, icon("arrow-ur")) for i, (n, p, d, h) in enumerate(cards))
    return '''<section class="section band-alt">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">Transparent pricing</span>
      <h2 class="mt-2">Two locked fees — no live checkout yet</h2>
    </div>
    <div class="grid cols-3 mt-8">%s</div>
    <div class="center mt-6">%s</div>
  </div>
</section>''' % (cells, btn(CTA_COMPARE[0], CTA_COMPARE[1], "primary", "arrow-right", data="home_compare_options"))


def project_vs_monthly():
    proj = ["You need a written build path first", "You are not ready to fund founding work",
            "You want the 60-day credit option", "Scope still needs to be locked",
            "You want to see gaps before you commit $15,000"]
    mon = ["The Blueprint path is decided", "You can stay inside one site and one class",
           "You can own the provider role", "You want milestone-based launch support",
           "Third-party vendors will still be yours to hire",
           "You understand we do not operate the school"]
    return '''<section class="section">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">Which model fits?</span>
      <h2 class="mt-2">Blueprint first, founding work if you proceed</h2>
    </div>
    <div class="grid cols-2 mt-8" style="gap:24px">
      <div class="card reveal"><h3 class="mb-3">Blueprint is best when</h3><ul class="check-list">%s</ul></div>
      <div class="card reveal" data-delay="80"><h3 class="mb-3">Founding implementation is best when</h3><ul class="check-list">%s</ul></div>
    </div>
    <div class="center mt-6">%s</div>
  </div>
</section>''' % ("".join('<li>%s<span>%s</span></li>' % (icon("check-circle"), x) for x in proj),
                 "".join('<li>%s<span>%s</span></li>' % (icon("check-circle"), x) for x in mon),
                 btn("Discuss founding scope", "capacity-plan.html", "primary", "arrow-right", data="help_me_choose"))


# ==========================================================================
# PRICING
# ==========================================================================
def build_pricing():
    founding_card = monthly_card(MONTHLY_PLANS[0])
    blueprint_card = project_card(PROJECT_PLANS[0])

    intro = '''<div class="promo-banner reveal">
  <p class="promo-head">%s</p>
  <p class="promo-note">%s %s %s</p>
  <div style="margin-top:14px">%s</div>
</div>''' % (INTRO_OFFER_HEADLINE, INTRO_OFFER_SUMMARY, INTRO_OFFER_REVIEW,
             INTRO_OFFER_AFTER,
             btn(CTA_JOIN[0], CTA_JOIN[1], "primary", "arrow-right", data="pricing_offer"))

    body = page_hero(
        "Pricing",
        "Two locked fees. Contact to begin.",
        "Feasibility Blueprint is $2,500. Founding internal-academy implementation is $15,000 total. There is no live self-serve payment link yet — discuss the work with Moses, then invoice when you are ready.",
        [("Pricing", None)]
    ) + '''
<section class="section" id="founding">
  <div class="container">
    %s
    <div class="center reveal mt-8" style="max-width:720px;margin-inline:auto">
      <span class="eyebrow">Founding implementation</span>
      <h2 class="mt-2">$15,000 total for one scoped project</h2>
    </div>
    <div class="grid mt-8 pkg-grid" style="max-width:520px;margin-inline:auto">%s</div>
    <p class="muted center mt-6" style="max-width:80ch;margin-inline:auto;font-size:.9rem">%s</p>
  </div>
</section>

<section class="section band-alt" id="blueprint">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">Start here</span>
      <h2 class="mt-2">Feasibility Blueprint</h2>
      <p class="muted mt-3">%s</p>
    </div>
    <div class="grid mt-8 pkg-grid" style="max-width:520px;margin-inline:auto">%s</div>
  </div>
</section>

<section class="section">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">What the fees do not include</span>
      <h2 class="mt-2">Third-party and operating costs stay yours</h2>
      <p class="muted mt-3">%s</p>
    </div>
    <div class="mt-8">%s</div>
  </div>
</section>

<section class="section band-alt">
  <div class="container">
    <div class="center reveal" style="max-width:680px;margin-inline:auto">
      <span class="eyebrow">School vs. recruit-only vs. FleetBuilt</span>
      <h2 class="mt-2">A clear way to compare your options</h2>
    </div>
    <div class="mt-8">%s</div>
  </div>
</section>

%s
''' % (intro, founding_card, MONTHLY_CAPACITY_NOTE, CREDIT_NOTE, blueprint_card,
       PROJECT_PRICING_DISCLAIMER,
       check_list(["Instructor payroll", "Range or classroom leases", "Insurance", "Software you choose",
                   "State or federal filings you submit", "Vehicle operating cost",
                   "Third-party vendors", "Multi-site or second-class work"], "cols-3"),
       comparison_table(),
       cta_band("Discuss the offer with Moses",
                "Email moses@fleetbuiltpartners.com. Payment is arranged after scope is confirmed — no leftover checkout links.",
                ("Discuss the Blueprint", "contact.html"),
                ("Email Moses", "mailto:moses@fleetbuiltpartners.com")))
    page("pricing.html",
         "Pricing | Feasibility Blueprint $2,500 · Founding $15,000 | FleetBuilt Partners",
         "Feasibility Blueprint $2,500. Founding internal-academy implementation $15,000 total. Blueprint credited toward founding if the same scoped project is contracted within 60 days of delivery.",
         body, active="pricing")


# ==========================================================================
# SAMPLE / WHAT YOU GET
# ==========================================================================
def build_sample_estimate():
    previews = [
        ("doc-text", "Feasibility snapshot", "Whether an internal path is worth pursuing at this site and class."),
        ("doc-search", "Decision memo", "What you must own versus what launch support can prepare."),
        ("users", "Role outline", "Who inside the operation typically has to carry the provider duties."),
        ("cube", "Gap list", "People, space, equipment, records, and third-party categories still open."),
        ("truck", "Asset note", "You supply the trucks — we do not inventory or operate them."),
        ("layers", "Scope lock", "One employer, one site, one state, one CDL class."),
        ("clipboard-check", "Recommended sequence", "An order of work — not an opening date."),
        ("shield", "Compliance boundary", "You remain the regulated training provider."),
        ("adjust", "Founding milestones", "What implementation would cover if you proceed."),
        ("check-circle", "Credit terms", "60-day Blueprint credit language, in writing."),
    ]
    cards = "".join(feature_item(ic, t, d, i * 40) for i, (ic, t, d) in enumerate(previews))

    download_cta = btn("Email me about the Blueprint", "mailto:moses@fleetbuiltpartners.com", "primary", "mail", cls="btn-block", data="sample_email")
    form_note = "Or send a short note and we will follow up about Blueprint deliverables."

    form = '''<form class="form-card" id="sampleForm" data-form data-analytics-form="sample" novalidate>
  <div class="form-grid">%s%s</div>
  %s
  %s
  %s
  <p class="hint center mt-3">We only use your details to follow up about Blueprint or founding-implementation support.</p>
</form>%s''' % (
        field("First name", "first_name", required=True, autocomplete="given-name"),
        field("Last name", "last_name", required=True, autocomplete="family-name"),
        field("Company", "company", required=True, autocomplete="organization"),
        field("Email", "email", "email", required=True, autocomplete="email"),
        field("Phone (optional)", "phone", "tel", autocomplete="tel"),
        "")
    form = form[:form.rfind("</form>")] + download_cta + "</form>" + form_success(
        "Thanks — we will follow up",
        "FleetBuilt Partners will reply at the email you provided about Blueprint deliverables and next steps.")

    demo_note = ('<div class="card reveal" style="background:var(--bg-alt);border:none;margin-top:18px">'
                 '<p class="muted" style="margin:0;font-size:.9rem">%s This page lists typical Blueprint and founding-support sections. '
                 'It is not a sample approval packet, and it is not a promise of hiring results.</p></div>' % icon("doc-text"))

    body = page_hero(
        "What you get",
        "See what a Blueprint covers",
        "FleetBuilt delivers organized launch-support documents. Preview the sections below, then email Moses to discuss a scoped project.",
        [("What You Get", None)]
    ) + '''
<section class="section">
  <div class="container">
    <div class="grid" style="grid-template-columns:1.05fr .95fr;gap:48px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">Inside a FleetBuilt Blueprint</span>
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
%s''' % (cards, demo_note, "Discuss the Blueprint", form_note, form, cta_band())
    page("sample-estimate.html",
         "What You Get | Feasibility Blueprint deliverables | FleetBuilt Partners",
         "See what a FleetBuilt Feasibility Blueprint covers — decision memo, gap list, scope lock, recommended sequence, and founding-implementation milestones.",
         body, active="sample")


# ==========================================================================
# CAPACITY PLAN (founding-scope form)
# ==========================================================================
def build_capacity_plan():
    employer_types = ["Private fleet", "For-hire carrier", "Construction / vocational fleet",
                      "Public or municipal fleet", "Other employer"]
    classes = ["Class A", "Class B", "Not sure yet"]
    plans = ["Feasibility Blueprint — $2,500", "Founding implementation — $15,000",
             "Not sure — start with a conversation"]

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
  <p class="hint center mt-3">We use this to understand founding scope. No obligation, no checkout.</p>
</form>%s''' % (
        field("First name", "first_name", required=True, autocomplete="given-name"),
        field("Last name", "last_name", required=True, autocomplete="family-name"),
        field("Company name", "company", required=True, autocomplete="organization"),
        field("Email", "email", "email", required=True, autocomplete="email"),
        field("Phone", "phone", "tel", autocomplete="tel"),
        select_field("Employer type", "employer_type", employer_types),
        field("Primary site city / state", "site", placeholder="e.g. Wichita, KS"),
        select_field("CDL class for founding work", "cdl_class", classes),
        field("Approximate power units at this site", "trucks", placeholder="You supply the trucks"),
        field("Current hiring bottleneck", "bottleneck", placeholder="School lag, retention, idle trucks…"),
        field("Open driver seats (optional)", "seats", "number"),
        field("Who would own the provider role", "owner_role", placeholder="Title / team"),
        select_field("What you want to discuss", "plan", plans),
        field("Target conversation date", "start_date", "date"),
        textarea_field("Additional notes", "notes", placeholder="Anything else we should know?"),
        btn("Request a scope conversation", "#", "primary", "arrow-right", "lg", cls="btn-block", data="capacity_submit", attrs="data-submit"),
        form_success("Thank you — we will map the conversation",
                     "FleetBuilt Partners will review your notes and follow up about Blueprint or founding-implementation scope."))

    body = page_hero(
        "Founding scope",
        "Tell us about the one site you would build first",
        "Founding work is one employer, one site, one state, and one CDL class. Share a few facts and we will recommend whether to start with the Blueprint.",
        [("Pricing", "pricing.html"), ("Founding scope", None)]
    ) + '''
<section class="section">
  <div class="container">
    <div class="grid" style="grid-template-columns:.8fr 1.2fr;gap:48px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">Launch support</span>
        <h2 class="mt-2 mb-3">Scope first, then fees</h2>
        <p class="muted mb-4">We do not take payment on this page. After scope is clear, Moses invoices for the Blueprint or founding work.</p>
        %s
        <div class="mt-6">%s</div>
      </div>
      <div class="reveal" data-delay="80">%s</div>
    </div>
  </div>
</section>''' % (
        check_list(["One employer / one site / one state / one class", "You remain the training provider",
                    "Third-party costs stay additional", "No approval or hiring-result promise"]),
        btn("View locked pricing", "pricing.html", "outline", "arrow-right", cls="btn-block", data="capacity_pricing"),
        form)
    page("capacity-plan.html",
         "Discuss Founding Scope | FleetBuilt Partners",
         "Share employer type, site, and CDL class. FleetBuilt will follow up about a $2,500 Blueprint or $15,000 founding implementation. No live checkout.",
         body, active="pricing")


# ==========================================================================
# UPLOAD / CONVERSATION INTAKE
# ==========================================================================
def build_upload_plans():
    services = ["Feasibility Blueprint", "Founding implementation", "Not sure — start with a conversation"]
    contact_methods = ["Email", "Phone", "Either"]

    step1 = '''<div class="form-step" data-step="1">
  <div class="form-grid">%s%s</div>
  %s
  <div class="form-grid">%s%s</div>
  <div class="form-grid">%s%s</div>
  <div class="form-grid">%s%s</div>
  <div class="step-actions"><button type="button" class="btn btn-primary btn-lg" data-next data-analytics="quote_step1_next">Continue %s</button></div>
</div>''' % (
        field("First name", "first_name", required=True, autocomplete="given-name"),
        field("Last name", "last_name", required=True, autocomplete="family-name"),
        field("Company name", "company", required=True, autocomplete="organization"),
        field("Email", "email", "email", required=True, autocomplete="email"),
        field("Phone", "phone", "tel", autocomplete="tel"),
        field("Site name", "project_name", placeholder="Yard or terminal name"),
        field("Site location", "project_location", placeholder="City, State"),
        field("Preferred conversation date", "bid_due", "date"),
        select_field("What you want to discuss", "service", services, required=True),
        icon("arrow-right"))

    step2 = '''<div class="form-step" data-step="2" hidden>
  %s
  %s
  <div class="form-grid">%s%s</div>
  %s
  <div class="step-actions">
    <button type="button" class="btn btn-outline" data-back>Back</button>
    <button type="submit" class="btn btn-primary btn-lg" data-analytics="quote_submit">Send conversation request</button>
  </div>
</div>''' % (
        dropzone(),
        textarea_field("Hiring or training notes", "scope", placeholder="Where does the current path break down?"),
        select_field("Preferred contact method", "contact_method", contact_methods),
        field("CDL class for founding work", "instructions", placeholder="Class A or Class B"),
        textarea_field("Anything else", "notes", placeholder="Idle trucks, school lag, retention, unclear build path…"))

    form = '''<form class="form-card" id="quoteForm" data-form data-multistep data-analytics-form="quote" novalidate>
  <div class="form-progress" aria-hidden="true">
    <div class="fp-track"><span class="fp-fill" style="width:50%%"></span></div>
    <span class="fp-label">Step <b class="fp-current">1</b> of 2</span>
  </div>
  %s
  %s
</form>%s''' % (step1, step2,
                form_success("Your request has been recorded",
                             "FleetBuilt Partners will review your notes and follow up about Blueprint or founding-implementation next steps."))

    body = page_hero(
        "Start a conversation",
        "Tell us about the operation you want to build",
        "Share the employer, site, state, and CDL class. We confirm scope before any Blueprint work begins. This is not a payment page.",
        [("Start a conversation", None)]
    ) + '''
<section class="section">
  <div class="container">
    <div class="grid" style="grid-template-columns:.8fr 1.2fr;gap:48px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">No obligation</span>
        <h2 class="mt-2 mb-3">A conversation, not a checkout</h2>
        <p class="muted mb-4">There is no live FleetBuilt payment link on this site. Moses will confirm scope, then invoice the locked Blueprint or founding fee if you want to proceed.</p>
        %s
        <div class="card mt-6" style="background:var(--bg-alt);border:none">
          <div class="flex items-center gap-2 mb-2" style="color:var(--brand-700);font-weight:600">%s Confidential</div>
          <p class="muted" style="font-size:.92rem">Operating notes are used only to review scope and prepare launch-support work.</p>
        </div>
      </div>
      <div class="reveal" data-delay="80">%s</div>
    </div>
  </div>
</section>''' % (
        check_list(["Employer and site", "State and CDL class", "Where hiring currently breaks down",
                    "Optional background files"]),
        icon("lock"), form)
    page("upload-plans.html",
         "Start a Blueprint Conversation | FleetBuilt Partners",
         "Share employer, site, state, and CDL class. FleetBuilt confirms scope before Blueprint work. No live checkout.",
         body, active="")


def redirect_stub(filename, target):
    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="robots" content="noindex,follow">'
            '<link rel="canonical" href="%s/%s">'
            '<meta http-equiv="refresh" content="0; url=%s">'
            '<title>Redirecting…</title></head><body>'
            '<p>This page has moved. <a href="%s">Continue</a>.</p>'
            '<script>location.replace("%s");</script></body></html>'
            % (CANONICAL_BASE, target, target, target, target))
    with open(os.path.join(OUT, filename), "w", encoding="utf-8") as f:
        f.write(html)


# ==========================================================================
# SERVICES (overview)
# ==========================================================================
def build_services():
    groups = [
        ("Core launch support", [
            ("quantity-takeoffs.html", "doc-search", "Feasibility Blueprint",
             "A $2,500 written path for one employer, one site, one state, and one CDL class."),
            ("construction-cost-estimating.html", "clipboard-check", "Founding implementation",
             "A $15,000 engagement to help you stand up that same scoped internal academy."),
            ("general-contractor-estimating.html", "flag", "One-site scope lock",
             "Founding work stays inside one site and one class so the project does not silently expand."),
            ("subcontractor-estimating.html", "shield", "Launch support only",
             "You remain the regulated training provider. We do not operate the school."),
        ]),
        ("Pressures we help you organize", [
            ("overflow-estimating.html", "truck", "Hiring-path pressure",
             "When searching the market and waiting on an outside school keep costing you time."),
            ("monthly-estimating-support.html", "layers", "Implementation milestones",
             "A visible sequence for founding work after the Blueprint."),
            ("sample-estimate.html", "doc-text", "What you receive",
             "Decision memo, gap list, recommended sequence, and credit terms."),
            ("how-it-works.html", "list-check", "How the work moves",
             "Conversation → Blueprint → your decision → optional founding support."),
        ]),
        ("Who typically reaches out", [
            ("residential-estimating.html", "home", "Private fleets",
             "Employers who already have trucks and need an inside training path."),
            ("commercial-estimating.html", "building", "For-hire carriers",
             "Carriers tired of recruiting licensed drivers with no internal pipeline."),
            ("civil-estimating.html", "wrench", "Vocational / construction fleets",
             "Operations that need a Class A or Class B path at one yard."),
            ("industries.html", "users", "First internal academy",
             "Employers standing up a first site — not a multi-state school brand."),
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
      <div class="reveal" id="review"><span class="eyebrow">Scope review</span><h3 class="mt-2">Lock the founding box first</h3><p class="muted mt-2 mb-3">Employer, site, state, and CDL class — written before fees are invoiced.</p>%s</div>
      <div class="reveal" id="ve" data-delay="80"><span class="eyebrow">What we will not do</span><h3 class="mt-2">Boundaries that stay visible</h3><p class="muted mt-2 mb-3">Launch support is not a school we operate.</p>%s</div>
      <div class="reveal" id="change-order"><span class="eyebrow">If scope changes</span><h3 class="mt-2">A second site is a new project</h3><p class="muted mt-2 mb-3">Expanding class, state, or location is scoped again.</p>%s</div>
      <div class="reveal" id="scope-sheets" data-delay="80"><span class="eyebrow">Your ownership</span><h3 class="mt-2">You still carry the provider role</h3><p class="muted mt-2 mb-3">Filings, instructors, and daily training stay with you.</p>%s</div>
    </div>
    <p class="muted mt-6" style="font-size:.86rem;max-width:72ch">%s %s</p>
  </div>
</section>''' % (
        check_list(["One employer", "One site", "One state", "One CDL class", "Written scope lock", "No silent expansion"]),
        check_list(["Operate your school", "Promise approval", "Promise hiring results", "Promise pass rates", "Publish opening dates", "Market that we train your hire"]),
        check_list(["New site", "New state", "Second CDL class", "Additional employer", "Separate founding fee"]),
        check_list(["Regulatory filings you submit", "Instructor hiring you do", "Range and classroom you arrange", "Records you keep", "Third-party vendors you choose"]),
        COMPLIANCE_NOTE, LOGO_NOTE)

    body = page_hero(
        "Services",
        "Launch support for an employer-owned CDL academy",
        "Blueprint and founding implementation for one scoped site. Documents, people, and operating facts are reviewed before work is accepted. We do not operate your school.",
        [("Services", None)]
    ) + ('<section class="section"><div class="container">%s</div></section>%s%s'
         % (sections, detail, cta_band()))
    page("services.html",
         "Services | Blueprint & founding implementation | FleetBuilt Partners",
         "Feasibility Blueprint and founding internal-academy implementation. One employer, one site, one state, one CDL class. Launch support only.",
         body, active="services")


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
        <h2 class="mt-2 mb-4">Organized launch support — not a school we run</h2>
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
         btn(CTA_PRIMARY[0], CTA_PRIMARY[1], "primary", "mail", cls="btn-block", data="svc_upload_%s" % filename.replace(".html", "")),
         btn(CTA_PRICING[0], CTA_PRICING[1], "outline", cls="btn-block", data="svc_pricing"),
         extra_section, cta_band())
    page(filename, title_seo, meta_desc, body, active="services")


def build_service_details():
    service_detail(
        "quantity-takeoffs.html",
        "Feasibility Blueprint | $2,500 | FleetBuilt Partners",
        "Feasibility Blueprint", "A written path before you fund founding work",
        "A $2,500 Blueprint for one employer, one site, one state, and one CDL class. It organizes the build path. It is not an approval, and it is not a school we operate.",
        ["Scope lock in writing", "Feasibility snapshot", "Decision memo", "Gap list",
         "Role outline for the provider duties", "Third-party cost categories",
         "Recommended sequence", "What you must still own",
         "Credit terms toward founding work", "Conversation notes"],
        ["Decision memo", "Gap list", "Scope lock", "Recommended sequence", "60-day credit language"],
        "Feasibility Blueprint for an employer-owned CDL training path — $2,500, credited toward founding implementation if the same scoped project is contracted within 60 days.",
        who="Fleets that have trucks and a hiring problem, but no written internal-academy path.",
        outcome="A document you can decide from — not a promised opening date.")

    service_detail(
        "construction-cost-estimating.html",
        "Founding Implementation | $15,000 | FleetBuilt Partners",
        "Founding implementation", "Launch support after you decide to build",
        "A $15,000 founding engagement for the same scoped project. Milestone-based support while you remain the regulated training provider.",
        ["Kickoff scope confirmation", "Working sessions", "Milestone notes", "Role and record checklists",
         "Third-party coordination notes", "Owner-decision log",
         "What is still yours to file or hire", "Handoff of working documents"],
        ["Milestone plan", "Working-session notes", "Checklists", "Owner-decision log", "Handoff package"],
        "Founding internal-academy implementation — $15,000 total for one employer, one site, one state, and one CDL class. Launch support only.",
        who="Employers who have a Blueprint (or an equivalent locked scope) and want hands-on implementation support.",
        outcome="Organized founding work. You still operate the training path.")

    service_detail(
        "general-contractor-estimating.html",
        "One-Site Scope | FleetBuilt Partners",
        "One-site scope", "One employer, one site, one state, one CDL class",
        "Founding work is deliberately narrow. A second yard, state, or class is a new scoped project — not an add-on hidden in the same fee.",
        ["Written scope lock", "Site identified", "State identified", "CDL class identified",
         "Employer of record identified", "Change-of-scope rule",
         "No multi-site founding in one fee", "No multi-class founding in one fee"],
        ["Scope lock page", "Change-of-scope note", "Fee boundary"],
        "FleetBuilt founding work is scoped to one employer, one site, one state, and one CDL class.",
        who="Employers who want a first internal academy at a single yard.",
        outcome="A founding box that stays honest.")

    service_detail(
        "subcontractor-estimating.html",
        "Launch Support Only | FleetBuilt Partners",
        "Launch support only", "You remain the regulated training provider",
        "FleetBuilt organizes launch support. We do not become your school, we do not file as your provider, and we do not market that we train your hire.",
        ["Clear provider-boundary language", "What launch support may prepare", "What you must still own",
         "No school-operation offer", "No approval promise", "No hiring-result promise",
         "Logo explained as a training-path mark", "Third-party vendors stay yours"],
        ["Boundary memo", "Ownership checklist", "Logo / positioning note"],
        "FleetBuilt Partners provides CDL academy launch support only. The client remains the regulated training provider.",
        who="Employers who want help building a path without handing the school to a vendor.",
        outcome="Support that stays on the correct side of the provider line.")

    service_detail(
        "monthly-estimating-support.html",
        "Implementation Milestones | FleetBuilt Partners",
        "Implementation milestones", "A visible sequence after the Blueprint",
        "Founding implementation uses written milestones. Timing still depends on your decisions and on work that remains yours.",
        ["Milestone list", "Working-session cadence", "Owner-decision checkpoints",
         "Document handoff points", "Scope-change pause rule", "No published opening date"],
        ["Milestone plan", "Checkpoint notes", "Handoff list"],
        "Founding implementation milestones for an employer-owned CDL academy. Launch support only — no opening-date promise.",
        who="Employers moving from Blueprint to founding work.",
        outcome="A sequence you can follow without confusing support for approval.",
        extra_section='''<section class="section band-alt"><div class="container">
          <div class="center reveal" style="max-width:680px;margin-inline:auto"><span class="eyebrow">Fees</span><h2 class="mt-2">Founding work is $15,000 total</h2><p class="muted mt-3">%s</p></div>
          <div class="center mt-6">%s</div></div></section>''' % (
            MONTHLY_CAPACITY_NOTE,
            btn("See locked pricing", "pricing.html#founding", "primary", "arrow-right", data="msupport_pricing")))


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
          <h3 class="mb-3">Typical focus</h3>
          <div class="flex wrap gap-2">%s</div>
          <div class="mt-6 grid" style="gap:10px">%s%s</div>
        </div>
      </div>
    </div>
  </div>
</section>
%s''' % (check_list(bullets, "cols-2"), who, outcome, trade_chips,
         btn(CTA_PRIMARY[0], CTA_PRIMARY[1], "primary", "mail", cls="btn-block", data="landing_upload"),
         btn(CTA_PRICING[0], CTA_PRICING[1], "outline", cls="btn-block"),
         cta_band())
    page(filename, meta_title, meta_desc, body, active="services")


def build_landing_pages():
    landing("overflow-estimating.html", "Hiring-path pressure",
            "When searching the market keeps costing you time",
            "External school calendars, idle trucks, and retention after you finally hire are familiar pressures. FleetBuilt helps you organize an inside path — without promising the seats fill on a date we name.",
            "Hiring-Path Pressure | FleetBuilt Partners",
            "Launch support when CDL hiring, external school lag, and idle trucks pile up. Blueprint first. You remain the training provider.",
            ["Name the hiring bottleneck", "Separate school-lag from retention", "Lock one site and one class",
             "Write the next sequence", "Call out third-party costs", "Keep the provider role with you"],
            ["School lag", "Idle trucks", "Retention", "Unclear build path"],
            "Fleets paying for empty seats while they wait on an outside calendar.",
            "A written path you can decide from.")

    landing("construction-estimating-services.html", "Launch support",
            "Help building an employer-owned CDL training path",
            "Blueprint and founding implementation for one scoped site. Nationwide conversation. You remain the regulated training provider.",
            "CDL Academy Launch Support | FleetBuilt Partners",
            "FleetBuilt Partners provides CDL academy launch support — Feasibility Blueprint $2,500 and founding implementation $15,000. You remain the provider.",
            ["Feasibility Blueprint", "Founding implementation", "Scope lock", "Gap list",
             "Milestone notes", "Ownership checklist"],
            ["Private fleets", "For-hire carriers", "Vocational fleets", "First internal academy"],
            "Employers who already have trucks.",
            "Launch support for a path you will own.")

    landing("residential-estimating.html", "Private fleets",
            "An internal path for a private fleet yard",
            "Private fleets often have equipment and a hiring need, but no written academy sequence. We help you map one site and one class.",
            "Private Fleet Academy Path | FleetBuilt Partners",
            "Launch support for private fleets standing up an internal CDL training path at one site.",
            ["Site and class lock", "Provider-role outline", "Gap list", "Third-party categories",
             "Blueprint decision memo", "Optional founding milestones"],
            ["Private fleet", "One yard", "Class A or B"],
            "Private-fleet employers.",
            "A first-site build path, written down.")

    landing("commercial-estimating.html", "For-hire carriers",
            "A training path besides recruit-and-wait",
            "For-hire carriers often stay in a search loop. FleetBuilt helps you examine an internal academy at one terminal — without taking over as the school.",
            "For-Hire Carrier Academy Path | FleetBuilt Partners",
            "Launch support for for-hire carriers considering an internal CDL training path at one site.",
            ["Terminal scope lock", "Hiring-bottleneck notes", "Blueprint", "Founding option",
             "Provider boundary", "Credit terms"],
            ["For-hire", "One terminal", "One class"],
            "For-hire carriers.",
            "An organized decision, not a promised hiring result.")

    landing("multifamily-estimating.html", "Multi-location employers",
            "Founding work still starts at one site",
            "If you operate more than one yard, founding implementation still locks to a single site and class. Additional locations are separate scoped projects.",
            "Multi-Location Employers | FleetBuilt Partners",
            "FleetBuilt founding work starts at one site even if you operate a larger network. Additional sites are new projects.",
            ["Choose the first site", "Lock class and state", "Write the Blueprint there",
             "Do not fold a second yard into the same $15,000", "Re-scope later locations"],
            ["First site", "Later sites separately"],
            "Employers with more than one location.",
            "An honest first-site founding box.")

    landing("civil-estimating.html", "Vocational fleets",
            "Construction and vocational operations",
            "Vocational fleets often already have trucks and a Class A or Class B need. We help you map an internal path at one yard.",
            "Vocational Fleet Academy Path | FleetBuilt Partners",
            "Launch support for construction and vocational fleets considering an internal CDL training path.",
            ["Class lock", "Yard lock", "Gap list", "Provider outline", "Blueprint", "Founding option"],
            ["Vocational", "Construction-adjacent", "One yard"],
            "Vocational and construction-adjacent fleets.",
            "A written first-site path.")

    landing("multi-trade-estimating.html", "Class scope",
            "One CDL class per founding engagement",
            "Class A and Class B are different founding boxes. Pick one class for the Blueprint and founding fee. A second class is a new scoped project.",
            "One CDL Class Per Engagement | FleetBuilt Partners",
            "FleetBuilt founding work covers one CDL class. A second class is scoped separately.",
            ["Choose Class A or Class B", "Keep the class visible in the scope lock",
             "Do not treat a second class as included", "Re-scope if you add a class later"],
            ["Class A", "Class B", "One per founding fee"],
            "Employers deciding which class to stand up first.",
            "A class lock that matches the fee.")


# ==========================================================================
# INDUSTRIES
# ==========================================================================
def build_industries():
    inds = [
        ("home", "Private fleets", "residential-estimating.html"),
        ("building", "For-hire carriers", "commercial-estimating.html"),
        ("truck", "Vocational / construction fleets", "civil-estimating.html"),
        ("building2", "Multi-location employers", "multifamily-estimating.html"),
        ("cap", "First internal academy", "construction-estimating-services.html"),
        ("flag", "One-site founding", "general-contractor-estimating.html"),
        ("layers", "Class A or Class B", "multi-trade-estimating.html"),
        ("refresh", "Hiring-path pressure", "overflow-estimating.html"),
        ("shield", "Launch support only", "subcontractor-estimating.html"),
    ]
    cards = "".join(
        '<a class="card card-hover reveal" data-delay="%d" href="%s"><div class="icon-box">%s</div><h3>%s</h3><span class="tag" style="margin-top:14px">View %s</span></a>'
        % (i * 40, h, icon(ic), t, icon("arrow-ur")) for i, (ic, t, h) in enumerate(inds))
    body = page_hero(
        "Who we work with",
        "Employers who already have trucks",
        "FleetBuilt Partners talks with fleets that want an internal training path. Founding work still locks to one site and one class. We do not operate your school.",
        [("Who we work with", None)]
    ) + ('<section class="section"><div class="container"><div class="grid cols-3">%s</div></div></section>%s'
         % (cards, cta_band()))
    page("industries.html", "Who We Work With | FleetBuilt Partners",
         "Private fleets, for-hire carriers, and vocational operations considering an internal CDL academy at one site. Launch support only.",
         body, active="services")


# ==========================================================================
# HOW IT WORKS
# ==========================================================================
def build_how():
    steps = [
        ("Share the operation", "Tell us the employer, site, state, CDL class, and where the hiring path breaks down.", "upload"),
        ("Scope review", "We confirm the founding box and identify missing facts before any Blueprint work is invoiced.", "doc-search"),
        ("Blueprint", "You receive a written feasibility package for that locked scope.", "clipboard-check"),
        ("Your decision", "You decide whether founding implementation is worth contracting. The Blueprint fee credits for 60 days on the same scoped project.", "adjust"),
        ("Founding milestones", "If you proceed, we work milestone-based launch support. You remain the provider.", "layers"),
        ("You operate", "Filings, instructors, and daily training stay with you. We do not operate the school.", "shield"),
    ]
    big = "".join(
        '<div class="grid reveal" data-delay="%d" style="grid-template-columns:auto 1fr;gap:22px;align-items:start;padding:26px 0;border-bottom:1px solid var(--line)"><div class="num" style="font-family:Poppins,sans-serif;width:54px;height:54px;border-radius:14px;background:var(--navy-900);color:#fff;display:grid;place-items:center;font-size:1.2rem">%d</div><div><div class="flex items-center gap-2 mb-2"><span style="color:var(--brand-600)">%s</span><h3>%s</h3></div><p class="muted">%s</p></div></div>'
        % (i * 50, i + 1, icon(ic), t, d) for i, (t, d, ic) in enumerate(steps))
    body = page_hero(
        "How It Works",
        "From a conversation to a written path",
        "A simple sequence with the provider role left on your side — and no opening date attached to the work.",
        [("How It Works", None)]
    ) + ('<section class="section"><div class="container" style="max-width:860px">%s</div></section>'
         '<section class="section band-alt"><div class="container"><div class="grid cols-3">%s</div></div></section>%s'
         % (big,
            "".join(feature_item(ic, t, d) for ic, t, d in [
                ("clock", "Schedule confirmed after a conversation", TURNAROUND_NOTE),
                ("shield", "Reviewed before delivery", "Every package is checked for scope lock, ownership boundaries, and claim language before it reaches you."),
                ("lock", "Confidential intake", "Operating notes are used only to review scope and prepare launch-support work."),
            ]),
            cta_band()))
    page("how-it-works.html", "How It Works | The FleetBuilt Partners process",
         "How FleetBuilt Partners works: conversation, scope review, Feasibility Blueprint, your decision, optional founding implementation, and you operate the training path.",
         body, active="how")


# ==========================================================================
# ABOUT
# ==========================================================================
def build_about():
    body = page_hero(
        "About FleetBuilt Partners",
        "Launch support for an employer-owned training path",
        "FleetBuilt Partners helps fleets map and stand up an internal CDL academy. You supply the trucks. You remain the regulated training provider.",
        [("About", None)]
    ) + '''
<section class="section">
  <div class="container">
    <div class="grid" style="grid-template-columns:1.1fr .9fr;gap:48px;align-items:center">
      <div class="reveal">
        <span class="eyebrow">Our approach</span>
        <h2 class="mt-2 mb-3">A build path when hiring stays expensive</h2>
        <div class="stack" style="color:var(--slate-600)">
          <p>Fleets already know the cost of an empty seat, an outside school calendar, and a truck that sits. Searching the market is one option. Building an inside path is another.</p>
          <p>FleetBuilt Partners provides launch support — a Feasibility Blueprint, then founding implementation if you decide the same scoped project is worth contracting. We do not operate your CDL school.</p>
          <p>%s</p>
        </div>
      </div>
      <div class="reveal" data-delay="100"><div class="card"><h3 class="mb-3">What we hold to</h3>%s</div></div>
    </div>
  </div>
</section>
%s
%s
%s''' % (
        LOGO_NOTE,
        check_list(["You remain the provider", "One site and one class for founding work", "Locked $2,500 / $15,000 fees",
                    "Blueprint credit within 60 days", "Third-party costs additional", "No approval or hiring-result promises"]),
        founder_section(), qc_section(),
        cta_band("Talk with Moses about the Blueprint",
                 "Email moses@fleetbuiltpartners.com or send a short note on the contact page.",
                 (CTA_PRIMARY[0], CTA_PRIMARY[1], "mail"), (CTA_CAPACITY[0], CTA_CAPACITY[1])))
    page("about.html", "About | FleetBuilt Partners",
         "FleetBuilt Partners provides CDL academy launch support. You supply the trucks. You remain the regulated training provider. Domain fleetbuiltpartners.com.",
         body, active="about")


# ==========================================================================
# FAQ
# ==========================================================================
def build_faq():
    faqs = [
        ("What does FleetBuilt Partners do?",
         "We provide launch support for an employer-owned CDL training operation. You supply the trucks. You remain the regulated training provider."),
        ("What is the Feasibility Blueprint?",
         "A $2,500 written package for one employer, one site, one state, and one CDL class. It organizes the build path. It is not an approval."),
        ("What is founding implementation?",
         "A $15,000 total engagement for the same scoped project. Milestone-based launch support after you decide to build."),
        ("Is the Blueprint credited toward founding work?",
         CREDIT_NOTE),
        ("Do you operate the CDL school?",
         "No. " + COMPLIANCE_NOTE + " " + LOGO_NOTE),
        ("Do you promise approval, pass rates, or hiring results?",
         "No. We do not promise approval, ROI, opening dates, pass rates, or hiring results."),
        ("Can I pay on this website?",
         "Not yet. There is no live FleetBuilt Stripe checkout. Email moses@fleetbuiltpartners.com. Payment is invoiced after scope is confirmed."),
        ("What is included in the founding scope?",
         INTRO_OFFER_REVIEW + " " + THIRD_PARTY_NOTE),
        ("What if we have more than one yard?",
         "Founding work still starts at one site. Additional locations are separate scoped projects."),
        ("What if we need Class A and Class B?",
         "Pick one class for the founding fee. A second class is a new scoped project."),
        ("Will Moses train our hire?",
         "No. We do not market that Moses trains your hire. Training delivery stays with the provider — you."),
        ("Are you FMCSA certified or approved?",
         "No. FleetBuilt Partners is not an FMCSA-certified or FMCSA-approved training provider, and we do not sell that claim."),
        ("How do we start?",
         "Email moses@fleetbuiltpartners.com or use the contact form. We confirm scope before any Blueprint invoice."),
        ("How is timing determined?",
         TURNAROUND_NOTE),
        ("How are operating notes protected?",
         "Notes and files are used only to review scope and prepare launch-support work. We do not sell your operating documents."),
        ("Can founding work be canceled?",
         CANCELLATION_POLICY),
        ("Where are you based?",
         "Conversations are nationwide. Contact: moses@fleetbuiltpartners.com · https://fleetbuiltpartners.com"),
    ]

    items_html = "".join(
        '<div class="faq-item reveal"><button class="faq-q" type="button" aria-expanded="false">%s<span class="chev">%s</span></button><div class="faq-a"><div class="inner">%s</div></div></div>'
        % (q, icon("chevron-down"), a) for q, a in faqs)
    body = page_hero(
        "Frequently asked questions",
        "Answers for fleets considering an internal academy",
        "Fees, scope, provider boundaries, and how to start a conversation.",
        [("FAQ", None)]
    ) + ('<section class="section"><div class="container" style="max-width:820px">%s</div></section>%s'
         % (items_html,
            cta_band("Still have questions?",
                     "Email Moses or review the locked $2,500 / $15,000 offer on the pricing page.",
                     (CTA_PRIMARY[0], CTA_PRIMARY[1], "arrow-right"), (CTA_PRICING[0], CTA_PRICING[1]))))
    page("faq.html", "FAQ | Internal CDL academy questions | FleetBuilt Partners",
         "Answers about FleetBuilt Partners Blueprint pricing, founding scope, provider boundaries, and how to start.",
         body, active="faq", schema_extra=faq_schema(faqs))


# ==========================================================================
# CONTACT
# ==========================================================================
def build_contact():
    info = [
        '<div class="card reveal"><div class="icon-box">%s</div><h3>Email</h3><p class="mt-2"><a href="mailto:%s" style="color:var(--brand-700);font-weight:600" data-analytics="email_click">%s</a></p></div>' % (icon("mail"), EMAIL, EMAIL),
        '<div class="card reveal" data-delay="80"><div class="icon-box">%s</div><h3>Service area</h3><p class="mt-2 muted">Conversations nationwide across the United States.</p></div>' % icon("globe"),
        '<div class="card reveal" data-delay="160"><div class="icon-box">%s</div><h3>Start</h3><p class="mt-2 muted">Discuss a Feasibility Blueprint — no live checkout on this site.</p></div>' % icon("clipboard-check"),
    ]
    if SCHEDULING_URL:
        info.append('<div class="card reveal" data-delay="240"><div class="icon-box">%s</div><h3>Book a call</h3><p class="mt-2"><a href="%s" style="color:var(--brand-700);font-weight:600" data-analytics="schedule_click">Schedule a conversation</a></p></div>' % (icon("calendar"), SCHEDULING_URL))
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
        textarea_field("How can we help?", "message", required=True, placeholder="Site, state, CDL class, and where the hiring path breaks down."),
        btn("Send Message", "#", "primary", "arrow-right", "lg", cls="btn-block", data="contact_submit", attrs="data-submit"),
        form_success("Thanks — we will be in touch",
                     "FleetBuilt Partners will review your message and follow up about Blueprint or founding-implementation scope."))

    body = page_hero(
        "Contact",
        "Discuss the Blueprint with Moses",
        "Email moses@fleetbuiltpartners.com or send a short note. We confirm scope before any invoice.",
        [("Contact", None)]
    ) + '''
<section class="section">
  <div class="container">
    <div class="grid %s mb-6">%s</div>
    <div class="grid" style="grid-template-columns:.8fr 1.2fr;gap:48px;align-items:start">
      <div class="reveal">
        <span class="eyebrow">Fastest way to start</span>
        <h2 class="mt-2 mb-3">Email is enough</h2>
        <p class="muted mb-4">There is no live payment link. If you already know the site and class, say so in the first note.</p>
        <div class="grid" style="gap:10px">%s%s</div>
      </div>
      <div class="reveal" data-delay="80">%s</div>
    </div>
  </div>
</section>''' % (cols, "".join(info),
                 btn("Email Moses", "mailto:moses@fleetbuiltpartners.com", "primary", "mail", cls="btn-block", data="contact_email"),
                 btn(CTA_PRICING[0], CTA_PRICING[1], "outline", cls="btn-block"),
                 form)
    page("contact.html", "Contact | FleetBuilt Partners",
         "Contact FleetBuilt Partners at moses@fleetbuiltpartners.com to discuss a Feasibility Blueprint or founding implementation.",
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
        '<p class="muted" style="font-size:.9rem">Last updated: September 2026</p>%s%s</div></div></section>'
        % (inner, note))
    page(filename, seo_title, seo_desc, body, robots="index, follow")


def build_legal():
    legal_page(
        "privacy.html", "Legal", "Privacy Policy",
        "How FleetBuilt Partners collects, uses and protects the information you share with us.",
        [
            ("Information we collect", ["Contact-form data (name, company, email, phone), marketing attribution fields, conversation-request details, and optional operating notes or files you choose to send.",
                                        "Limited technical/usage data may be collected automatically to operate and improve the website."]),
            ("How we use information", ["To respond to Blueprint and founding-implementation inquiries, confirm scope, communicate about related FleetBuilt services, and improve our services."]),
            ("Uploaded or emailed documents", ["Your documents are used only to review scope and prepare launch-support work. We do not sell your operating documents."]),
            ("File handling", ["Files are handled confidentially and retained only as long as needed to deliver and support the engagement, unless a longer period is required by law or agreement."]),
            ("Analytics", ["We may use privacy-respecting analytics to understand site usage. No analytics tag is loaded unless configured."]),
            ("Communications", ["If you submit a work email or service request, we may contact you about that request and related FleetBuilt services. You can unsubscribe from non-essential communications at any time."]),
            ("Data retention", ["We retain personal data and documents only as long as necessary for the purposes described here or as required by law."]),
            ("Third-party service providers", ["We may use service providers for website hosting and approved communications. They process data on our behalf under appropriate confidentiality obligations."]),
            ("Security limitations", ["We use reasonable safeguards, but no method of transmission or storage is completely secure, and we cannot guarantee absolute security."]),
            ("Your requests", ["You may request access to, correction of, or deletion of your personal information by emailing %s." % EMAIL]),
            ("Contact", ["Questions about this policy? Email %s." % EMAIL]),
        ],
        "Privacy Policy | FleetBuilt Partners",
        "How FleetBuilt Partners collects, uses, retains and protects your information and operating notes.")

    legal_page(
        "terms.html", "Legal", "Terms of Service",
        "The terms that govern your use of the FleetBuilt Partners website and launch-support services.",
        [
            ("Acceptance of terms", ["By using this website or our services, you agree to these Terms. If you do not agree, please do not use the website or services."]),
            ("Launch support only", [COMPLIANCE_NOTE]),
            ("Client remains the provider", ["You are responsible for regulatory filings, instructor qualifications, training delivery, and the operation of any CDL school or training program."]),
            ("Scope", [INTRO_OFFER_REVIEW, STANDARD_BID_DEF]),
            ("Fees", [INTRO_OFFER_SUMMARY, CREDIT_NOTE, THIRD_PARTY_NOTE, "There is no live self-serve checkout on this website until a FleetBuilt payment account is connected."]),
            ("No promised results", ["We do not promise approval, ROI, opening dates, pass rates, or hiring results."]),
            ("Cancellation", [CANCELLATION_POLICY]),
            ("Confidentiality", ["We handle your operating notes confidentially and use them only to deliver the requested services."]),
            ("Intellectual property", ["Website content is owned by FleetBuilt Partners or its licensors. Deliverables prepared for you may be used for your internal academy planning as agreed."]),
            ("Limitation of liability", ["To the maximum extent permitted by law, FleetBuilt Partners is not liable for indirect, incidental, or consequential damages arising from use of the website, services, or deliverables."]),
            ("Disputes & governing law", ["These terms are governed by the laws of %s. [Dispute-resolution terms to be finalized by the owner with legal counsel.]" % GOVERNING_LAW]),
            ("Changes", ["We may update these terms; continued use constitutes acceptance of the updated terms."]),
            ("Contact", ["Questions? Email %s." % EMAIL]),
        ],
        "Terms of Service | FleetBuilt Partners",
        "Terms governing use of the FleetBuilt Partners website and CDL academy launch-support services.")

    legal_page(
        "disclaimer.html", "Legal", "Launch-Support Disclaimer",
        "Important information about the nature and limitations of our work.",
        [
            ("Nature of our work", ["FleetBuilt Partners provides launch support for employer-owned CDL training operations. Deliverables are prepared from the information you share and are reviewed before delivery."]),
            ("You remain the provider", [COMPLIANCE_NOTE, LOGO_NOTE]),
            ("No guarantees", ["We do not represent that a training operation will be approved, open on a date, produce a pass rate, fill seats, or return a stated ROI.",
                               ["Results depend on facts you control as the provider", "Third parties you hire are outside our control", "Regulators make their own determinations"]]),
            ("Not a school we operate", ["We do not operate your CDL school, file as your training provider, or market that we train your hire."]),
            ("Not professional licensure services", ["We do not provide legal, engineering, or other licensed professional services, and our deliverables do not replace work performed by a licensed professional or a qualified training provider."]),
            ("Your responsibility", ["You are responsible for reviewing each deliverable and making your own operating, hiring, and filing decisions."]),
            ("Contact", ["Questions about this disclaimer? Email %s." % EMAIL]),
        ],
        "Launch-Support Disclaimer | FleetBuilt Partners",
        "The nature, scope, and limitations of FleetBuilt Partners CDL academy launch-support work.")


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

    redirect_stub("request-a-quote.html", "contact.html")
    redirect_stub("upload-project.html", "contact.html")

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
