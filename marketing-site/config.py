#!/usr/bin/env python3
"""Centralized site configuration for Mobi Estimates.

Single source of truth for company info, contact details, pricing, CTAs,
SEO, and deployment paths. Edit values here — pages pull from this module.
Empty strings are treated as "not configured" and are hidden in the UI.
"""

# --------------------------------------------------------------------------
# Company / brand
# --------------------------------------------------------------------------
SITE_NAME = "Mobi Estimates"
TAGLINE = "Bid more projects without hiring another estimator."
LEGAL_NAME = "Mobi Estimates"          # update with registered legal entity name
BUSINESS_LOCATION = "United States"     # service area (nationwide / remote)
GOVERNING_LAW = "[State/Country — owner to supply]"  # for Terms

# --------------------------------------------------------------------------
# Contact — leave blank to hide from the public UI until verified
# --------------------------------------------------------------------------
EMAIL = "estimates@mobiestimates.com"  # preferred; already in use on the site
PHONE = ""                              # NO verified number yet -> hidden everywhere
PHONE_HREF = ""                         # e.g. "+18005551234" once verified
SCHEDULING_URL = ""                     # e.g. Calendly link; falls back to contact page

# Social links (blank = hidden)
SOCIAL = {
    "linkedin": "",
    "instagram": "",
    "facebook": "",
}

# --------------------------------------------------------------------------
# Deployment / domain
# --------------------------------------------------------------------------
# The live public website. No "www" — the canonical origin is
# https://mobiestimates.com. CANONICAL_BASE is used for <link rel=canonical>,
# Open Graph URLs, the sitemap, and robots.txt. Internal links are relative, so
# they work regardless of where the site is served.
CANONICAL_BASE = "https://mobiestimates.com"
PORTAL_BASE = "https://portal.mobiestimates.com"
# Paid-plan CTAs and the introductory offer hand off to the authenticated portal.
CHECKOUT_BASE = PORTAL_BASE
INTRO_OFFER_URL = PORTAL_BASE + "/signup?offer=first_estimate_free"
INTRO_OFFER_HEADLINE = "Your first qualifying estimate is free"
INTRO_OFFER_SUMMARY = "One qualifying estimate per new company. No card required."
INTRO_OFFER_REVIEW = ("Supported scope and project complexity are reviewed before acceptance. "
                      "Turnaround is confirmed after complete documents are received and reviewed.")
INTRO_OFFER_AFTER = "After your qualifying estimate, regular per-project or monthly pricing applies."

# --------------------------------------------------------------------------
# Analytics — blank = no tag emitted (never commit a real secret/key here)
# --------------------------------------------------------------------------
ANALYTICS_ID = ""   # e.g. "G-XXXXXXX"; loaded only if set

# --------------------------------------------------------------------------
# Forms — endpoint for real submissions. Blank = front-end demo mode
# (validates + shows success, no network call). Wire to Formspree/Netlify/
# your backend by setting FORM_ENDPOINT.
# --------------------------------------------------------------------------
FORM_ENDPOINT = ""
LEAD_CAPTURE_ENDPOINT = PORTAL_BASE + "/api/leads"
ACCEPTED_FILE_TYPES = ".pdf, .dwg, .dwf, .png, .jpg, .jpeg, .xlsx, .xls, .csv, .zip"
MAX_FILE_NOTE = "Up to 25 MB per file. Large plan sets: send a .zip or a shared link in the notes."

# --------------------------------------------------------------------------
# Sample estimate download — blank = lead-capture only (no broken link)
# --------------------------------------------------------------------------
SAMPLE_PDF_URL = ""

# --------------------------------------------------------------------------
# Turnaround language
# --------------------------------------------------------------------------
TURNAROUND_SINGLE = "Schedule confirmed after review"
TURNAROUND_FULL = "Schedule confirmed after review"
TURNAROUND_NOTE = ("Turnaround is confirmed after complete documents are received and Mobi reviews "
                   "project size, scope, drawing quality, trade count, complexity, and deliverables.")

# --------------------------------------------------------------------------
# Pricing — project-based
# --------------------------------------------------------------------------
# Exactly ONE one-time paid option: Pay Per Project at $599. It is available
# after the introductory offer and is not a subscription. The CTA hands off to
# the authenticated portal while preserving the selected plan.
PROJECT_PLANS = [
    {
        "id": "pay-per-project",
        "name": "One Project Estimate",
        "price": "$599",
        "period": "one-time",
        "best_for": "For contractors who need one professional construction estimate without a monthly subscription.",
        "features": [
            "One purchased estimate",
            "Construction takeoff with labor and material pricing",
            "AI-assisted and human-reviewed",
            "Contractor-ready Excel and PDF delivery",
            "One-time payment — no subscription, no automatic renewal",
            "Another estimate requires a new purchase or a monthly plan",
        ],
        "cta": "Order One Estimate",
        "href": CHECKOUT_BASE + "/start?plan=pay_per_project",
        "featured": False,
    },
]

PROJECT_PRICING_DISCLAIMER = (
    "Final pricing depends on project size, scope, drawing quality, trade count, complexity, "
    "deliverables, and required turnaround. Your exact price and delivery schedule will be "
    "approved before work begins.")

# --------------------------------------------------------------------------
# Pricing — monthly subscriptions (capacity-based, NOT hours)
# --------------------------------------------------------------------------
# Three monthly subscription plans at the approved regular prices. These remain
# available after the introductory offer. Capacities and differentiators are the
# authoritative values—do not invent additional ones.
MONTHLY_PLANS = [
    {
        "id": "starter",
        "name": "Starter",
        "price": "$995",

        "period": "per month",
        "capacity": "Up to 2 estimates per month",
        "active": "1 active estimate at a time",
        "best_for": "Add estimating capacity without hiring another full-time estimator.",
        "features": [
            "Up to 2 estimates per month",
            "1 active estimate at a time",
            "Construction takeoffs with labor & material pricing",
            "AI-assisted and human-reviewed",
            "Standard scheduling",
            "Month-to-month — cancel anytime",
        ],
        "cta": "Choose Starter",
        "href": CHECKOUT_BASE + "/start?plan=starter",
        "featured": False,
    },
    {
        "id": "growth",
        "name": "Growth",
        "price": "$1,995",

        "period": "per month",
        "capacity": "Up to 5 estimates per month",
        "active": "2 active estimates at a time",
        "best_for": "More monthly estimating capacity so you can submit more bids.",
        "features": [
            "Up to 5 estimates per month",
            "2 active estimates at a time",
            "Construction takeoffs with labor & material pricing",
            "AI-assisted and human-reviewed",
            "Saved company rates & markups",
            "Priority scheduling",
            "Month-to-month — cancel anytime",
        ],
        "cta": "Choose Growth",
        "href": CHECKOUT_BASE + "/start?plan=growth",
        "featured": True,
        "badge": "Most Popular",
    },
    {
        "id": "estimating_department",
        "name": "Estimating Department",
        "price": "$2,995",

        "period": "per month",
        "capacity": "Up to 8 estimates per month",
        "active": "3 active estimates at a time",
        "best_for": "Your outsourced estimating department for steady monthly bid volume.",
        "features": [
            "Up to 8 estimates per month",
            "3 active estimates at a time",
            "Construction takeoffs with labor & material pricing",
            "AI-assisted and human-reviewed",
            "Saved company rates & markups",
            "Priority scheduling",
            "Addenda & revision handling",
            "Month-to-month — cancel anytime",
        ],
        "cta": "Choose Estimating Department",
        "href": CHECKOUT_BASE + "/start?plan=estimating_department",
        "featured": False,
    },
]


MONTHLY_CAPACITY_NOTE = (
    "Monthly subscriptions reserve ongoing estimating support and are billed month-to-month. "
    "They are not unlimited-use plans.")

STANDARD_BID_DEF = (
    "Every project is reviewed before work begins. Larger, multi-trade, or unusually complex "
    "projects may require a confirmed scope, price, and delivery timeline.")

# Owner-configurable policy answers (kept out of public copy until confirmed).
# Set ROLLOVER_POLICY to a real answer to publish it in the FAQ.
ROLLOVER_POLICY = ""   # e.g. "Unused standard bids do not roll over." — OWNER TO CONFIRM
CANCELLATION_POLICY = "Month-to-month. You can cancel before your next billing cycle."

# --------------------------------------------------------------------------
# Founder / company trust — leave blank to hide individual fields
# --------------------------------------------------------------------------
FOUNDER = {
    "name": "",
    "photo": "",            # path under assets/img/ once supplied
    "bio": "",
    "construction_experience": "",
    "estimating_experience": "",
    "software": "",
    "location": "",
    "linkedin": "",
    "phone": "",
    "email": "",
    "registration": "",
}

FOUNDER_STATEMENT = (
    "Construction companies should not have to turn down profitable bidding opportunities because their "
    "estimating team is overloaded. Mobi provides dependable estimating capacity when contractors need it — "
    "whether that means one project, monthly support, or a primary outsourced estimating resource.")

# --------------------------------------------------------------------------
# Primary / secondary CTAs (label -> destination)
# --------------------------------------------------------------------------
# The primary path is the owner-approved introductory offer. Paid plan selection
# remains available on the pricing page after visitors review regular options.
# "Book a Free Estimate" is the single most prominent CTA site-wide; it always
# hands off to the authenticated portal's free-estimate intake (INTRO_OFFER_URL).
CTA_PRIMARY = ("Book a Free Estimate", INTRO_OFFER_URL)
CTA_UPLOAD = ("View Plans & Pricing", "pricing.html")
CTA_PRICING = ("View Pricing", "pricing.html")
CTA_SAMPLE = ("Download Sample Estimate", "sample-estimate.html")
CTA_CAPACITY = ("View Plans & Pricing", "pricing.html")
CTA_COMPARE = ("Compare Plans", "pricing.html")

CTA_JOIN = ("Book a Free Estimate", INTRO_OFFER_URL)

# --------------------------------------------------------------------------
# Explainer video (homepage, immediately below the hero)
# --------------------------------------------------------------------------
# ▶ TO PUBLISH THE REAL VIDEO: set EXPLAINER_VIDEO_URL to the finished video's
#   URL, then rebuild (python3 generate.py) and bump ASSET_VER below.
#   - A self-hosted file (e.g. "assets/video/mobi-explainer.mp4") renders a
#     native <video> player with the poster image below.
#   - A YouTube/Vimeo/Wistia URL renders a lazy-loaded responsive iframe.
#   While EXPLAINER_VIDEO_URL is blank, a clearly-marked TEMPORARY branded
#   placeholder is shown (no stock footage). This is the ONLY field to change.
EXPLAINER_VIDEO_URL = ""          # e.g. "assets/video/mobi-explainer.mp4" or a YouTube/Vimeo link
EXPLAINER_VIDEO_POSTER = ""       # optional thumbnail for self-hosted video, e.g. "assets/img/explainer-poster.jpg"
EXPLAINER_VIDEO_HEADING = "See How Mobi Replaces the Traditional Estimating Department"
EXPLAINER_VIDEO_SUBHEAD = ("Watch how contractors go from plans and project documents to a detailed, "
                           "human-reviewed estimate — without adding another full-time estimator.")

ASSET_VER = "14"  # bump to bust browser cache when CSS/JS/pricing change
