#!/usr/bin/env python3
"""Centralized site configuration for FleetBuilt Partners.

Single source of truth for company info, contact details, pricing, CTAs,
SEO, and deployment paths. Edit values here — pages pull from this module.
Empty strings are treated as "not configured" and are hidden in the UI.
"""

# --------------------------------------------------------------------------
# Company / brand
# --------------------------------------------------------------------------
SITE_NAME = "FleetBuilt Partners"
TAGLINE = "You supply the trucks. We help you build the training operation."
TAGLINE_SECONDARY = (
    "Stop searching for CDL drivers. Start developing a path to train them "
    "inside your operation."
)
LEGAL_NAME = "FleetBuilt Partners"
BUSINESS_LOCATION = "United States"
GOVERNING_LAW = "[State/Country — owner to supply]"

# --------------------------------------------------------------------------
# Contact — leave blank to hide from the public UI until verified
# --------------------------------------------------------------------------
EMAIL = "moses@fleetbuiltpartners.com"
PHONE = ""
PHONE_HREF = ""
SCHEDULING_URL = ""

SOCIAL = {
    "linkedin": "",
    "instagram": "",
    "facebook": "",
}

# --------------------------------------------------------------------------
# Deployment / domain
# --------------------------------------------------------------------------
CANONICAL_BASE = "https://fleetbuiltpartners.com"
# No live FleetBuilt Stripe or customer portal yet. Public CTAs stay on-site
# (contact / mailto) until a FleetBuilt payment account is connected.
PORTAL_BASE = ""
LOGIN_URL = "contact.html"
CHECKOUT_BASE = "contact.html"
INTRO_OFFER_URL = "contact.html"
INTRO_OFFER_HEADLINE = "Start with a Feasibility Blueprint"
INTRO_OFFER_SUMMARY = (
    "A scoped Feasibility Blueprint is $2,500. Founding internal-academy "
    "implementation is $15,000 total."
)
INTRO_OFFER_REVIEW = (
    "Work is scoped to one employer, one site, one state, and one CDL class. "
    "Third-party and operating costs are additional."
)
INTRO_OFFER_AFTER = (
    "The Blueprint fee is credited toward founding implementation if the same "
    "scoped project is contracted within 60 days of Blueprint delivery."
)

# --------------------------------------------------------------------------
# Analytics — blank = no tag emitted (never commit a real secret/key here)
# --------------------------------------------------------------------------
ANALYTICS_ID = ""

# --------------------------------------------------------------------------
# Forms — endpoint for real submissions. Blank = front-end demo mode
# (validates + shows success, no network call). Wire to Formspree/Netlify/
# your backend by setting FORM_ENDPOINT.
# --------------------------------------------------------------------------
FORM_ENDPOINT = ""
LEAD_CAPTURE_ENDPOINT = ""
ACCEPTED_FILE_TYPES = ".pdf, .doc, .docx, .png, .jpg, .jpeg, .xlsx, .xls, .csv, .zip"
MAX_FILE_NOTE = (
    "Optional background files only — policies, org charts, or notes that help "
    "us understand your operation. Nothing here is an application filing."
)

# --------------------------------------------------------------------------
# Sample download — blank = lead-capture only (no broken link)
# --------------------------------------------------------------------------
SAMPLE_PDF_URL = ""

# --------------------------------------------------------------------------
# Scope / compliance (locked)
# --------------------------------------------------------------------------
SCOPE_LINE = "One employer · one site · one state · one CDL class"
COMPLIANCE_NOTE = (
    "You remain the regulated training provider. FleetBuilt Partners provides "
    "launch support only. We do not operate your CDL school, and we do not "
    "promise approval, hiring results, pass rates, ROI, or opening dates."
)
LOGO_NOTE = (
    "Our logo is a truck with a green graduation cap — a mark for the training "
    "path you want to build. It does not mean we operate your CDL school."
)
CREDIT_NOTE = (
    "The $2,500 Blueprint fee is credited toward the $15,000 founding "
    "implementation if the same scoped project is contracted within 60 days "
    "of Blueprint delivery."
)
THIRD_PARTY_NOTE = "Third-party and operating costs are additional."

# --------------------------------------------------------------------------
# Turnaround language — no opening-date or approval promises
# --------------------------------------------------------------------------
TURNAROUND_SINGLE = "Schedule confirmed after a scope conversation"
TURNAROUND_FULL = "Schedule confirmed after a scope conversation"
TURNAROUND_NOTE = (
    "Timing depends on the information you provide, the decisions you make, "
    "and work that remains yours as the training provider. We do not publish "
    "opening dates or approval timelines."
)

# --------------------------------------------------------------------------
# Pricing — locked offer
# --------------------------------------------------------------------------
PROJECT_PLANS = [
    {
        "id": "feasibility-blueprint",
        "name": "Feasibility Blueprint",
        "price": "$2,500",
        "period": "fixed fee",
        "best_for": "A written path for standing up an internal CDL training operation at one site.",
        "features": [
            "Feasibility snapshot for one employer, one site, one state, one CDL class",
            "Decision memo covering what you must own versus what launch support can prepare",
            "Gap list: people, equipment, space, records, and third-party costs",
            "Recommended next-step sequence — not an approval or opening date",
            "Credited toward founding implementation if contracted within 60 days",
        ],
        "cta": "Discuss the Blueprint",
        "href": "contact.html",
        "featured": False,
    },
]

PROJECT_PRICING_DISCLAIMER = (
    "Fees cover FleetBuilt launch-support work only. Third-party filings, "
    "instructors, range time, insurance, software, and other operating costs "
    "are additional. Exact sequencing is confirmed after we review your "
    "operation — we do not sell guaranteed approval or hiring results."
)

MONTHLY_PLANS = [
    {
        "id": "founding-implementation",
        "name": "Founding implementation",
        "price": "$15,000",
        "period": "total",
        "capacity": "One scoped internal-academy launch",
        "active": "One employer · one site · one state · one CDL class",
        "best_for": "Hands-on implementation support after you decide the Blueprint path is worth building.",
        "features": [
            "Founding internal-academy implementation for the same scoped project",
            "Milestone-based launch support — you remain the training provider",
            "Working sessions to organize roles, records, and operating rhythm",
            "Coordination notes for third parties you choose to hire",
            "Blueprint fee credited if contracted within 60 days of delivery",
        ],
        "cta": "Discuss founding work",
        "href": "contact.html",
        "featured": True,
        "badge": "Founding scope",
    },
]


MONTHLY_CAPACITY_NOTE = (
    "Founding implementation is a fixed $15,000 engagement for one scoped "
    "project. It is launch support, not an outsourced CDL school and not a "
    "subscription."
)

STANDARD_BID_DEF = (
    "Every engagement is reviewed before work begins. Expanding beyond one "
    "employer, one site, one state, or one CDL class is a new scoped project."
)

ROLLOVER_POLICY = ""
CANCELLATION_POLICY = (
    "Fees for delivered Blueprint work are earned. Founding implementation "
    "milestones are confirmed in writing before that work starts."
)

# --------------------------------------------------------------------------
# Founder / company trust — leave blank to hide individual fields
# --------------------------------------------------------------------------
FOUNDER = {
    "name": "",
    "photo": "",
    "bio": "",
    "construction_experience": "",
    "estimating_experience": "",
    "software": "",
    "location": "",
    "linkedin": "",
    "phone": "",
    "email": EMAIL,
    "registration": "",
}

FOUNDER_STATEMENT = (
    "Fleets should not have to keep paying the hidden cost of an empty seat "
    "while they wait on an external CDL school calendar. FleetBuilt Partners "
    "helps employers map and stand up an internal training path — without "
    "taking over as the school, and without promising hiring results."
)

# --------------------------------------------------------------------------
# Primary / secondary CTAs (label -> destination)
# --------------------------------------------------------------------------
CTA_PRIMARY = ("Discuss the Blueprint", "contact.html")
CTA_UPLOAD = ("Start a conversation", "contact.html")
CTA_PRICING = ("View Pricing", "pricing.html")
CTA_SAMPLE = ("See what you get", "sample-estimate.html")
CTA_CAPACITY = ("Discuss founding scope", "capacity-plan.html")
CTA_COMPARE = ("Compare the offer", "pricing.html")
CTA_JOIN = ("Discuss the Blueprint", "contact.html")
CTA_MAIL = ("Email Moses", "mailto:moses@fleetbuiltpartners.com")

# --------------------------------------------------------------------------
# Explainer video (homepage, immediately below the hero)
# --------------------------------------------------------------------------
EXPLAINER_VIDEO_URL = ""
EXPLAINER_VIDEO_POSTER = ""
EXPLAINER_VIDEO_HEADING = "See how FleetBuilt helps you map an internal training path"
EXPLAINER_VIDEO_SUBHEAD = (
    "A short look at the Blueprint-to-implementation sequence — launch "
    "support for an employer-owned training operation, not a school we run."
)

# --------------------------------------------------------------------------
# Real proof — logos & testimonials. EMPTY until genuine, verifiable proof
# exists. Never add fabricated proof.
# --------------------------------------------------------------------------
CUSTOMER_LOGOS = []
TESTIMONIALS = []

ASSET_VER = "21"

LOGO_HORIZONTAL = "assets/img/logo-horizontal.jpeg"
LOGO_STACKED = "assets/img/logo-stacked.jpeg"
LOGO_ICON = "assets/img/logo-icon-stacked.png"
LOGO_PRIMARY = LOGO_STACKED
OG_IMAGE = "assets/img/og-logo.png"
