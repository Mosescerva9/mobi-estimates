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
# Pricing CTAs hand off to checkout on the same public origin (NOT a separate
# portal/preview host), preserving the selected plan.
CHECKOUT_BASE = CANONICAL_BASE

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
ACCEPTED_FILE_TYPES = ".pdf, .dwg, .dwf, .png, .jpg, .jpeg, .xlsx, .xls, .csv, .zip"
MAX_FILE_NOTE = "Up to 25 MB per file. Large plan sets: send a .zip or a shared link in the notes."

# --------------------------------------------------------------------------
# Sample estimate download — blank = lead-capture only (no broken link)
# --------------------------------------------------------------------------
SAMPLE_PDF_URL = ""

# --------------------------------------------------------------------------
# Turnaround language
# --------------------------------------------------------------------------
TURNAROUND_SINGLE = "Typically 2–4 business days"
TURNAROUND_FULL = "Typically 3–5 business days"
TURNAROUND_NOTE = ("Turnaround depends on project size, scope, drawing quality, trade count, "
                   "complexity, and required deliverables. Your delivery schedule is approved before work begins.")

# --------------------------------------------------------------------------
# Pricing — project-based
# --------------------------------------------------------------------------
# Exactly ONE one-time option: Pay Per Project at $599. Not a subscription; the
# 50% first-month discount does not apply. The CTA hands off to checkout on the
# public site, preserving the selected plan.
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
# Three monthly subscription plans. New subscribers get 50% off the FIRST month
# (once); regular monthly pricing begins with the second month. CTA hands off to
# the portal checkout, preserving the selected plan. Capacities and differentiators
# are the approved, authoritative values — do not invent additional ones.
MONTHLY_PLANS = [
    {
        "id": "starter",
        "name": "Starter",
        "price": "$995",
        "first_month": "$497.50",
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
        "first_month": "$997.50",
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
        "first_month": "$1,497.50",
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

# 50%-off-first-month promotion copy (monthly plans only).
FIRST_MONTH_PROMO = "Get 50% off your first month on any monthly plan"
FIRST_MONTH_PROMO_NOTE = ("Regular monthly pricing begins with your second month. "
                          "Pay Per Project is not included in this promotion.")

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
# Every general/primary CTA sends visitors to the pricing page to choose a plan
# first (no "free trial", no "free quote", no "upload plans" as the primary path).
CTA_PRIMARY = ("Join Now", "pricing.html")
CTA_UPLOAD = ("View Plans & Pricing", "pricing.html")
CTA_PRICING = ("View Pricing", "pricing.html")
CTA_SAMPLE = ("Download Sample Estimate", "sample-estimate.html")
CTA_CAPACITY = ("View Plans & Pricing", "pricing.html")
CTA_COMPARE = ("Compare Plans", "pricing.html")

# Primary "Join Now" CTA → the pricing page (NOT signup/checkout directly).
# Visitors review plans, pick one, then the plan card hands off to checkout on
# the public site (https://mobiestimates.com/start?plan=<id>).
CTA_JOIN = ("Join Now", "pricing.html")

ASSET_VER = "12"  # bump to bust browser cache when CSS/JS/pricing change
