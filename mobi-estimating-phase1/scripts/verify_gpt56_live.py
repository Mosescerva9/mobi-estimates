"""Opt-in live verification for the GPT-5.6 Responses API structured-output path.

This is the ONLY place in the repository that may make a real, paid OpenAI call,
and it does so only under an explicit gate. It:

* refuses to run without ALL of: ``MOBI_GPT56_LIVE_VERIFY=1``, a configured API
  key, and ``MOBI_ENABLE_LIVE_PROJECT_ANALYSIS=true``;
* sends only a tiny SYNTHETIC, non-customer payload;
* uses model alias ``gpt-5.6`` + reasoning effort ``medium`` + a tiny structured
  schema;
* makes exactly ONE bounded paid request;
* writes sanitized, machine-readable evidence (configured model, returned model
  metadata, request id, parse success, and a flag proving no customer data was
  sent) — never any key material, plan text, or raw provider payload;
* does NOT approve, deliver, price, message, pay, or mutate any production data.

Usage (never paste secrets into chat/commits/logs — export them in your shell)::

    export OPENAI_API_KEY=...            # your key, via env only
    export MOBI_OPENAI_API_KEY=$OPENAI_API_KEY
    export MOBI_ENABLE_LIVE_PROJECT_ANALYSIS=true
    export MOBI_GPT56_LIVE_VERIFY=1
    python -m scripts.verify_gpt56_live --out evidence/gpt56_live.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# A synthetic, non-customer spec snippet. Contains no real project/tenant data.
SYNTHETIC_SOURCE = (
    "### SOURCE (document_id=SYNTHETIC-001, name=synthetic_probe.txt, page=1)\n"
    "SECTION 099000 PAINTING. This is a synthetic connectivity probe, not a real "
    "project. The project type is commercial. No quantities or prices are stated."
)

_PROBE_PROMPT = (
    "Return a tiny structured summary of the supplied synthetic text only. Do not "
    "invent measurements, quantities, or prices. Source-reference your summary."
)


class _ProbeRef(BaseModel):
    # Default-free: strict Structured Outputs rejects JSON-Schema ``default``
    # keywords, so these optional locators are required-nullable (``| None`` with
    # no default) rather than defaulted to None.
    model_config = ConfigDict(extra="forbid")

    document_id: Annotated[str, StringConstraints(max_length=64)] | None
    page_number: Annotated[int, Field(ge=1, le=1000)] | None


class TinyProbe(BaseModel):
    """Deliberately tiny schema to keep the paid request bounded and cheap.

    Default-free like the production schemas so the same strict Structured-Outputs
    contract is exercised.
    """

    model_config = ConfigDict(extra="forbid")

    project_type: Annotated[str, StringConstraints(max_length=64)]
    one_line_summary: Annotated[str, StringConstraints(max_length=280)]
    source_reference: _ProbeRef


def _preflight_exact_model_effort(model: str, reasoning_effort: str) -> list[str]:
    """Return a list of hard-stop reasons if model/effort are not the exact lock.

    A defensive, in-probe re-check of the enforced ``gpt-5.6`` / ``medium`` lock.
    If this returns anything, the probe must exit BEFORE constructing a client or
    making any SDK/network call — a preflight failure costs zero paid requests.
    """

    from app.config import ENFORCED_MODEL_ALIAS, ENFORCED_REASONING_EFFORT

    problems: list[str] = []
    if model != ENFORCED_MODEL_ALIAS:
        problems.append(
            f"configured model {model!r} is not the enforced alias {ENFORCED_MODEL_ALIAS!r}"
        )
    if reasoning_effort != ENFORCED_REASONING_EFFORT:
        problems.append(
            f"configured reasoning effort {reasoning_effort!r} is not the enforced "
            f"{ENFORCED_REASONING_EFFORT!r}"
        )
    return problems


def _gate_or_exit() -> None:
    problems: list[str] = []
    if os.environ.get("MOBI_GPT56_LIVE_VERIFY") != "1":
        problems.append("MOBI_GPT56_LIVE_VERIFY must equal '1'")
    if not os.environ.get("MOBI_OPENAI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        problems.append("an OpenAI API key must be configured via env")
    if os.environ.get("MOBI_ENABLE_LIVE_PROJECT_ANALYSIS", "").lower() not in {"true", "1", "yes"}:
        problems.append("MOBI_ENABLE_LIVE_PROJECT_ANALYSIS must be enabled")
    if problems:
        sys.stderr.write(
            "Refusing to run live verification. Unmet gate(s):\n  - "
            + "\n  - ".join(problems)
            + "\n"
        )
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GPT-5.6 live verification probe")
    parser.add_argument(
        "--out",
        default="evidence/gpt56_live.json",
        help="Path to write sanitized machine-readable evidence.",
    )
    args = parser.parse_args(argv)

    _gate_or_exit()

    # Import inside main so merely importing this module never triggers config
    # load or a network call.
    from app.analysis.openai_client import ResponsesError, build_gpt56_client
    from app.config import settings

    # Hard preflight BEFORE building a client or touching the SDK: the request may
    # only ever go out as exactly gpt-5.6 / medium. A mismatch exits here having
    # made zero SDK/network calls (and therefore zero paid requests).
    preflight_problems = _preflight_exact_model_effort(
        settings.openai_model, settings.openai_reasoning_effort
    )
    if preflight_problems:
        sys.stderr.write(
            "Refusing to run live verification (preflight). Problem(s):\n  - "
            + "\n  - ".join(preflight_problems)
            + "\n"
        )
        return 2

    client = build_gpt56_client(
        api_key=settings.openai_api_key or os.environ.get("OPENAI_API_KEY"),
        model=settings.openai_model,
        reasoning_effort=settings.openai_reasoning_effort,
        timeout_seconds=settings.project_analysis_timeout_seconds,
        live_enabled=settings.enable_live_project_analysis,
    )

    evidence: dict[str, object] = {
        "configured_model": settings.openai_model,
        "configured_reasoning_effort": settings.openai_reasoning_effort,
        "contains_customer_data": False,
        # This records the deliberately bounded client invocation, not a billing
        # claim. A timeout/transport failure can make provider billing unknowable;
        # only a verified response supplies usage below.
        "bounded_client_calls_invoked": 1,
        "provider_response_received": False,
    }

    try:
        result = client.parse(
            system_prompt=_PROBE_PROMPT,
            source_blocks=[SYNTHETIC_SOURCE],
            text_format=TinyProbe,
            schema_version="probe-1.0",
            max_source_chars=len(SYNTHETIC_SOURCE) + 1,
        )
    except ResponsesError as exc:
        evidence.update({"parse_success": False, "error_code": exc.code})
        _write(args.out, evidence)
        sys.stderr.write(f"Live verification failed: {exc.code}\n")
        return 1

    meta = result.metadata
    evidence.update(
        {
            "parse_success": True,
            "provider_response_received": True,
            "returned_model": meta.returned_model,
            "response_id": meta.response_id,
            "request_id": meta.request_id,
            "reasoning_effort_used": meta.reasoning_effort,
            "usage": meta.usage,
        }
    )
    _write(args.out, evidence)
    sys.stdout.write(f"Live verification succeeded. Evidence written to {args.out}\n")
    return 0


def _write(out_path: str, evidence: dict[str, object]) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - manual, gated entry point
    raise SystemExit(main())
