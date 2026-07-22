"""Dedicated, strict-safe output schemas for the live GPT-5.6 extraction path.

The legacy provider response contracts in :mod:`app.extraction.provider_schemas`
are unsafe to hand to a live model as an OpenAI Structured-Outputs
``text_format``:

* they carry model-authored ``Decimal`` quantity/confidence fields — but the live
  model must NEVER output a measurement, quantity, dimension, unit cost, price, or
  numeric confidence;
* they use ``dict[str, Any]`` free-form maps, which produce
  ``additionalProperties: true`` and are rejected by strict Structured Outputs;
* they carry Pydantic ``default`` values, which emit JSON-Schema ``default``
  keywords that strict Structured Outputs also rejects.

These dedicated schemas are what the live model actually fills in. They are
closed (``extra="forbid"``), fully default-free (every field required; optional
facts are ``X | None`` emitted explicitly), and contain **no** numeric
quantity/price/confidence field at all. They also expose **no** model-authored
descriptive prose field: the model returns only a category code, a sheet
relevance verdict, and verbatim source quotes. The provider adapts them into the
existing caller contract server-side — leaving quantities null, deriving every
description from the verbatim source quote, and constructing all evidence/source
metadata itself. The model never authors descriptions, locations, assumptions,
exclusions, classification reasons, or any numeric/quantity/price metadata.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

LIVE_EXTRACTION_SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Fail-closed semantic safety for model-authored free text (defense-in-depth)
# ---------------------------------------------------------------------------
# The primary safety guarantee is now STRUCTURAL: the live output schemas below
# expose NO model-authored descriptive prose field at all — no ``description``,
# ``location``, ``assumptions``, ``exclusions``, or classification ``reason``.
# The model only returns a category code, a relevance verdict, and verbatim
# source quotes; the server derives every descriptive/quantitative value itself.
# So persistence no longer depends on the completeness of any denylist.
#
# This validator is retained purely as a defense-in-depth utility (exercised by
# the test suite) for any code path that still handles model-authored strings. It
# fails closed on prohibited content:
#   * ANY model-authored digit is rejected: descriptive prose must never carry a
#     numeric measurement, quantity, dimension, price, or count. The more specific
#     currency/unit/dimension patterns run first purely to report a precise
#     category label; the digit catch-all covers everything else.
#   * Spelled-out number words are ALSO rejected now (``two``, ``three``, ``sixth``
#     …): with all descriptive prose removed from the model schema, denylist
#     completeness is no longer a persistence dependency, so this filter can be
#     maximally strict without dropping legitimate grounded evidence.
#   * Explicit approval / final-status / payment / customer-communication claims
#     are rejected even when they carry no number at all.
#   * The offending text is never echoed back in the error (safe error mapping).
#
# NOTE: evidence quotes are deliberately NOT run through this filter — they are
# required to be a verbatim substring of the supplied source page, so a number in
# a quote is *sourced*, not model-authored, and rejecting it would drop legitimate
# grounded evidence.


class LiveTextPolicyViolation(ValueError):
    """Raised when model-authored free text smuggles a prohibited class.

    ``category`` is a short, non-sensitive class label (never the offending text).
    """

    def __init__(self, category: str) -> None:
        super().__init__(f"prohibited_free_text:{category}")
        self.category = category


# Any currency symbol is model-authored money — never allowed in scope prose.
_CURRENCY_SYMBOL = re.compile(r"[$€£¥₹]")

# A digit run adjacent to a money word ("500 dollars", "12 usd", "0.75 cents").
_NUMERIC_CURRENCY = re.compile(
    r"\d[\d,\.]*\s*(usd|dollars?|dollar|cents?|eur|euros?|gbp|pounds?\s+sterling|cad|aud)\b",
    re.IGNORECASE,
)

# Explicit price/cost/total vocabulary. A descriptive scope line has no legitimate
# need to author a price, cost, subtotal, total, markup, or invoice amount.
_MONEY_TERMS = re.compile(
    r"\b("
    r"price|priced|pricing|cost|costs|costed|budget|unit\s+cost|unit\s+price|"
    r"subtotal|sub-total|total|totals|grand\s+total|line\s+total|"
    r"total\s+cost|total\s+price|markup|mark-up|invoice|invoiced|"
    r"amount\s+due|cost\s+each|price\s+each"
    r")\b",
    re.IGNORECASE,
)

# A digit run adjacent to an estimating unit / dimension. Spelled-out numbers are
# intentionally excluded so ordinary scope prose ("two finish coats") is allowed.
_NUMERIC_UNIT = re.compile(
    r"\d[\d,\.]*\s*"
    r"("
    r"sf|sq\.?\s*ft|square\s+f(?:ee|oo)t|lf|lin\.?\s*ft|linear\s+f(?:ee|oo)t|"
    r"cy|cubic\s+yards?|sy|square\s+yards?|"
    r"ft|feet|foot|in|inch|inches|yd|yds|yards?|"
    r"mm|cm|meters?|metres?|"
    r"gal|gallons?|qt|quarts?|"
    r"lbs?|pounds?|oz|ounces?|kg|kilograms?|tons?|"
    r"mils?|dft|wft|percent|"
    r"ea|each|pcs?|pieces?|units?|items?|doors?|windows?|fixtures?"
    r")\b|\d[\d,\.]*\s*%",
    re.IGNORECASE,
)

# Dimension shorthand: 5', 6", 2x4, 10 x 20.
_DIMENSION = re.compile(r"\d\s*['\"]|\d[\d,\.]*\s*[x×]\s*\d", re.IGNORECASE)

# Catch-all: ANY digit in model-authored prose is prohibited. Runs after the more
# specific numeric patterns so those report a precise category; this covers every
# remaining digit-bearing case (counts without a unit, sheet numbers, "3 coats").
_ANY_DIGIT = re.compile(r"\d")

# Spelled-out number words (cardinal and ordinal), zero through the common forms,
# plus "once"/"twice". With all descriptive prose removed from the model output
# schema, denylist completeness is no longer a persistence dependency, so this
# filter now rejects word-numbers too — e.g. "two finish coats", "the second
# coat". Evidence quotes bypass this filter entirely (they are sourced verbatim).
_SPELLED_NUMBER = re.compile(
    r"\b("
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand|million|billion|trillion|"
    r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|"
    r"eighteenth|nineteenth|twentieth|thirtieth|fortieth|fiftieth|sixtieth|"
    r"seventieth|eightieth|ninetieth|hundredth|thousandth|"
    r"once|twice"
    r")\b",
    re.IGNORECASE,
)

# Explicit workflow action / status claims the model must never assert: approval /
# authorization, proposal, final delivery/status, completion status, payment, or
# any customer/client communication. These are rejected even without a digit.
_ACTION_STATUS = re.compile(
    r"\b("
    # Approval / authorization / sign-off.
    r"approve|approved|approves|approving|approval|"
    r"authoriz(e|ed|ation)|authoris(e|ed|ation)|"
    r"sign(ed)?[-\s]?off|signed\s+off\s+by|"
    # Proposal / final delivery / final status.
    r"proposal|finaliz(e|ed|es|ing|ation)|finalis(e|ed|es|ing|ation)|"
    r"final\s+(delivery|deliverable|estimate|proposal|invoice|status|price|bid)|"
    r"delivered|deliver\s+to\s+(the\s+)?(customer|client)|ready\s+to\s+deliver|"
    # Explicit completion status.
    r"completed|completion\s+status|marked\s+(as\s+)?complete|"
    r"work\s+(is\s+)?complete|status\s*:\s*complete|"
    # Payment / balance.
    r"payment|paid\s+in\s+full|remit(tance)?|deposit\s+received|"
    r"balance\s+due|amount\s+outstanding|invoice\s+sent|"
    # Any customer/client communication (message / notify / contact).
    r"emailed?\s+(the\s+)?(customer|client)|e-mail(ed)?\s+(the\s+)?(customer|client)|"
    r"messaged?\s+(the\s+)?(customer|client)|"
    r"notif(y|ied|ication)\s+(to\s+)?(the\s+)?(customer|client)|"
    r"(customer|client)\s+notif(y|ied|ication)|"
    r"notify\s+(the\s+)?(customer|client)|"
    r"contact(ing|ed)?\s+(the\s+)?(customer|client)|"
    r"send(ing)?\s+(the\s+)?(customer|client)\s+(an?\s+)?(message|email|e-mail|notification)|"
    r"message(d|ing)?\s+(the\s+)?(customer|client)|"
    r"communicat(e|ed|ing|ion)\s+(with|to)\s+(the\s+)?(customer|client)|"
    r"sent\s+to\s+(the\s+)?(customer|client)"
    r")\b",
    re.IGNORECASE,
)

# Ordered so the most specific class is reported first.
_POLICY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("currency", _CURRENCY_SYMBOL),
    ("currency", _NUMERIC_CURRENCY),
    ("price_cost_total", _MONEY_TERMS),
    ("numeric_measurement", _NUMERIC_UNIT),
    ("numeric_dimension", _DIMENSION),
    ("action_status_claim", _ACTION_STATUS),
    ("numeric_content", _ANY_DIGIT),
    ("spelled_number", _SPELLED_NUMBER),
)


def assert_free_text_safe(value: str | None) -> None:
    """Fail closed on model-authored free text that smuggles a prohibited class.

    ``None``/empty is always allowed. Raises :class:`LiveTextPolicyViolation`
    (whose message never contains the offending text) on the first match.
    """

    if not value:
        return
    for category, pattern in _POLICY_PATTERNS:
        if pattern.search(value):
            raise LiveTextPolicyViolation(category)


class LiveExtractionModel(BaseModel):
    """Base: unknown keys forbidden, enums serialized as their string values."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True, strict=True)


# Bounded free-text helpers (mirror the analysis-layer bounds). Only the
# category-code label and the verbatim source quote are model-authored now; every
# descriptive/quantitative value is server-derived, so no medium/long prose helper
# is needed here.
_ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
_QuoteText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class LiveSheetRelevance(str, Enum):
    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"
    UNCERTAIN = "uncertain"


# --- Classification --------------------------------------------------------
class LiveSheetClassificationItem(LiveExtractionModel):
    """One sheet relevance decision, keyed by the page locator the model saw.

    The model is only ever shown ``page`` / ``sheet_number`` — never the internal
    sheet UUID — so it keys by ``pdf_page_number``; the server maps that back to a
    verified sheet id. There is deliberately NO model-authored ``reason`` field:
    the server assigns any classification rationale itself (a fixed value), so the
    model never authors descriptive prose here.
    """

    pdf_page_number: Annotated[int, Field(ge=1, le=100_000)]
    relevance: LiveSheetRelevance


class LiveSheetClassificationOutput(LiveExtractionModel):
    classifications: list[LiveSheetClassificationItem] = Field(max_length=1000)


# --- Scope -----------------------------------------------------------------
class LiveScopeEvidence(LiveExtractionModel):
    """A grounding anchor for a scope candidate: a page plus a required verbatim
    quote from that supplied page. The server verifies the quote is a LITERAL
    exact substring (case/whitespace/punctuation exact) of the raw embedded text
    on that same page before adapting/persisting the candidate, and derives the
    scope description from that sourced quote. No numeric field exists here by
    design."""

    pdf_page_number: Annotated[int, Field(ge=1, le=100_000)]
    quote: _QuoteText


class LiveScopeCandidate(LiveExtractionModel):
    """A candidate scope item. The model authors ONLY a category code and one or
    more verbatim source quotes — it has NO description, location, assumptions,
    exclusions, quantity, unit, price, or confidence field. The server derives the
    description from the first sourced quote, supplies a null quantity, and assigns
    all evidence metadata; the model only categorizes and cites."""

    category_code: _ShortText
    evidence: list[LiveScopeEvidence] = Field(min_length=1, max_length=100)


class LiveScopeExtractionOutput(LiveExtractionModel):
    candidates: list[LiveScopeCandidate] = Field(max_length=1000)
