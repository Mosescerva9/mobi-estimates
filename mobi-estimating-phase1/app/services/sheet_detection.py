"""Deterministic, rule-based sheet-number and sheet-title candidate detection.

No machine learning and no LLM are involved. Detection is pure Python:
regular expressions plus conservative geometric heuristics over PyMuPDF text
blocks. The detector is intentionally cautious — it prefers to return *no*
candidate (and flag the page for human review) over guessing.

A detected sheet number is only ever a **candidate**. It must be verified by a
human before it can back a trusted downstream source reference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Common construction-drawing discipline prefixes (single or paired letters).
KNOWN_DISCIPLINES: frozenset[str] = frozenset(
    {
        "A", "S", "M", "E", "P", "C", "G", "L", "F", "T", "D", "I", "Q", "H",
        "V", "R", "FP", "FA", "AD", "AV", "ID", "SD", "EL", "ME", "PL",
    }
)

# Matches tokens such as A1.01, A-101, A101, S2.1, M-201, E001, P3.02, C-100,
# G0.01. A discipline prefix (1-2 letters), an optional separator, a number, and
# an optional dotted sub-number.
SHEET_NUMBER_RE = re.compile(
    r"^(?P<disc>[A-Z]{1,2})(?P<sep>[-\.\s]?)(?P<num>\d{1,4})(?:\.(?P<sub>\d{1,2}))?$"
)

# Words that frequently appear in title blocks; their presence boosts a
# title candidate but is never required.
TITLE_KEYWORDS: frozenset[str] = frozenset(
    {
        "PLAN", "PLANS", "ELEVATION", "ELEVATIONS", "SECTION", "SECTIONS",
        "DETAIL", "DETAILS", "SCHEDULE", "SCHEDULES", "NOTES", "FLOOR",
        "ROOF", "FOUNDATION", "FRAMING", "LAYOUT", "DIAGRAM", "RISER",
        "FINISH", "FINISHES", "PARTITION", "REFLECTED", "CEILING", "SITE",
        "COVER", "INDEX", "GENERAL", "DEMOLITION", "ENLARGED", "EXTERIOR",
        "INTERIOR", "MECHANICAL", "ELECTRICAL", "PLUMBING", "STRUCTURAL",
    }
)

ACCEPT_THRESHOLD = 0.60  # minimum confidence to store a detected number
CONFLICT_MARGIN = 0.15  # competing distinct candidates within this are ambiguous


@dataclass(frozen=True)
class TextBlock:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


@dataclass(frozen=True)
class Candidate:
    value: str
    confidence: float
    source_text: str
    in_title_block: bool


@dataclass
class SheetNumberResult:
    best: Candidate | None
    requires_review: bool
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def detected_value(self) -> str | None:
        return self.best.value if self.best is not None else None

    @property
    def confidence(self) -> float | None:
        return round(self.best.confidence, 3) if self.best is not None else None


def normalize_sheet_token(token: str) -> str:
    """Uppercase and strip surrounding punctuation/space from a token."""
    return token.strip().strip(":#").upper()


def _in_title_block(
    block: TextBlock, page_width: float, page_height: float
) -> bool:
    """True if a block sits in the bottom-right title-block region of the page.

    Title blocks are conventionally in the lower-right corner. We treat the
    right 35% and bottom 45% of the page as the candidate region.
    """
    if page_width <= 0 or page_height <= 0:
        return False
    cx = (block.x0 + block.x1) / 2
    cy = (block.y0 + block.y1) / 2
    return cx >= page_width * 0.65 and cy >= page_height * 0.55


def _score_candidate(
    *,
    match: re.Match,
    line_text: str,
    in_title_block: bool,
    has_block_geometry: bool,
) -> float:
    score = 0.40  # base: matched the sheet-number pattern
    disc = match.group("disc")
    if disc in KNOWN_DISCIPLINES:
        score += 0.25
    if has_block_geometry:
        score += 0.25 if in_title_block else 0.0
    else:
        score += 0.10  # no geometry available: small neutral credit
    if len(line_text.strip()) <= 16:  # isolated / short line
        score += 0.15
    if match.group("sub") or match.group("sep"):
        score += 0.05
    return min(score, 1.0)


def _iter_lines(text: str, blocks: list[TextBlock] | None):
    """Yield (line_text, owning_block_or_None) pairs."""
    if blocks:
        for block in blocks:
            for line in block.text.splitlines():
                if line.strip():
                    yield line, block
    else:
        for line in text.splitlines():
            if line.strip():
                yield line, None


def detect_sheet_number_candidates(
    text: str,
    *,
    blocks: list[TextBlock] | None = None,
    page_width: float = 0.0,
    page_height: float = 0.0,
) -> list[Candidate]:
    """Return all sheet-number candidates found on the page, scored."""
    has_geometry = bool(blocks)
    candidates: list[Candidate] = []
    for line_text, block in _iter_lines(text, blocks):
        for raw_token in re.split(r"[\s,;|]+", line_text):
            token = normalize_sheet_token(raw_token)
            if not token:
                continue
            match = SHEET_NUMBER_RE.match(token)
            if not match:
                continue
            in_tb = (
                _in_title_block(block, page_width, page_height)
                if block is not None
                else False
            )
            confidence = _score_candidate(
                match=match,
                line_text=line_text,
                in_title_block=in_tb,
                has_block_geometry=has_geometry,
            )
            candidates.append(
                Candidate(
                    value=token,
                    confidence=confidence,
                    source_text=line_text.strip()[:120],
                    in_title_block=in_tb,
                )
            )
    # Highest-confidence candidates first; stable for determinism.
    candidates.sort(key=lambda c: (-c.confidence, c.value))
    return candidates


def detect_sheet_number(
    text: str,
    *,
    blocks: list[TextBlock] | None = None,
    page_width: float = 0.0,
    page_height: float = 0.0,
) -> SheetNumberResult:
    """Pick the best sheet-number candidate conservatively.

    Stores the best candidate only when it clears ``ACCEPT_THRESHOLD`` and no
    competing distinct candidate is within ``CONFLICT_MARGIN``. Otherwise the
    result is flagged for human review and no number is stored.
    """
    candidates = detect_sheet_number_candidates(
        text, blocks=blocks, page_width=page_width, page_height=page_height
    )
    if not candidates:
        return SheetNumberResult(best=None, requires_review=True, candidates=[])

    best = candidates[0]
    # Conflict: a different value with a near-equal score.
    conflict = any(
        c.value != best.value and (best.confidence - c.confidence) <= CONFLICT_MARGIN
        for c in candidates[1:]
    )
    accepted = best.confidence >= ACCEPT_THRESHOLD and not conflict
    if accepted:
        return SheetNumberResult(
            best=best, requires_review=False, candidates=candidates
        )
    # Uncertain or conflicting: keep candidates for transparency but store none.
    return SheetNumberResult(best=None, requires_review=True, candidates=candidates)


def detect_sheet_title(
    text: str,
    *,
    blocks: list[TextBlock] | None = None,
    page_width: float = 0.0,
    page_height: float = 0.0,
    sheet_number: str | None = None,
) -> str | None:
    """Conservatively detect a sheet title.

    Looks for a title-like line (mostly letters, reasonable length) preferentially
    inside the title-block region. Returns ``None`` when nothing reliable is found
    so the caller leaves the field null and requires review.
    """
    best_line: str | None = None
    best_score = 0.0
    for line_text, block in _iter_lines(text, blocks):
        candidate = line_text.strip()
        if not (3 <= len(candidate) <= 60):
            continue
        upper = candidate.upper()
        if sheet_number and normalize_sheet_token(candidate) == sheet_number:
            continue
        # Reject lines that are themselves sheet numbers or mostly digits.
        if SHEET_NUMBER_RE.match(normalize_sheet_token(candidate)):
            continue
        letters = sum(ch.isalpha() for ch in candidate)
        if letters < max(3, len(candidate) * 0.6):
            continue
        score = 0.30
        if block is not None and _in_title_block(block, page_width, page_height):
            score += 0.40
        words = set(re.findall(r"[A-Z]+", upper))
        if words & TITLE_KEYWORDS:
            score += 0.30
        if score > best_score:
            best_score = score
            best_line = candidate
    # Require at least a keyword hit or a title-block location to be reliable.
    if best_line is not None and best_score >= 0.60:
        return best_line
    return None
