"""Proposal renderers: JSON, Markdown, and print-ready self-contained HTML.

Client-facing only: sell prices + scope narrative. No cost buildup, margins, rates,
labor hours, or internal identifiers are ever rendered. The HTML is fully
self-contained (inline CSS, no external resources) and print-to-PDF ready.
"""

from __future__ import annotations

import html
import json
from decimal import Decimal
from typing import Any


def _money(value: Any, currency: str = "USD") -> str:
    symbol = "$" if currency == "USD" else ""
    dec = Decimal(str(value or "0")).quantize(Decimal("0.01"))
    return f"{symbol}{dec:,.2f}"


def _lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if value in (None, ""):
        return []
    return [str(value)]


def proposal_json(version: dict, line_items: list[dict]) -> str:
    payload = {
        "proposal_number": version.get("proposal_number"),
        "status": version.get("status"),
        "version_number": version.get("version_number"),
        "client_name": version.get("client_name"),
        "client_contact": version.get("client_contact"),
        "prepared_by": version.get("prepared_by"),
        "valid_until": version.get("valid_until"),
        "currency": version.get("currency"),
        "detail_level": version.get("detail_level"),
        "cover_notes": version.get("cover_notes"),
        "total_sell_price": version.get("total_sell_price"),
        "line_items": [{"section": li.get("section"), "description": li.get("description"),
                        "location": li.get("location"), "quantity": li.get("quantity"),
                        "unit": li.get("unit"), "sell_price": li.get("sell_price")}
                       for li in line_items],
        "inclusions": version.get("inclusions") or [],
        "exclusions": version.get("exclusions") or [],
        "assumptions": version.get("assumptions") or [],
        "clarifications": version.get("clarifications") or [],
        "terms": version.get("terms"),
        "snapshot_hash": version.get("snapshot_hash"),
    }
    return json.dumps(payload, indent=2, default=str)


def proposal_markdown(version: dict, line_items: list[dict]) -> str:
    cur = version.get("currency", "USD")
    out: list[str] = []
    out.append(f"# Proposal {version.get('proposal_number') or '(draft)'}")
    out.append("")
    out.append(f"**Prepared for:** {version.get('client_name') or ''}  ")
    if version.get("client_contact"):
        out.append(f"**Attn:** {version['client_contact']}  ")
    if version.get("prepared_by"):
        out.append(f"**Prepared by:** {version['prepared_by']}  ")
    if version.get("valid_until"):
        out.append(f"**Valid until:** {version['valid_until']}  ")
    out.append(f"**Status:** {version.get('status')}")
    out.append("")
    if version.get("cover_notes"):
        out.append(version["cover_notes"]); out.append("")
    out.append("## Scope of work")
    out.append("")
    out.append("| Item | Description | Price |")
    out.append("| --- | --- | ---: |")
    for li in line_items:
        desc = li.get("description") or ""
        if li.get("location"):
            desc += f" ({li['location']})"
        out.append(f"| {li.get('section') or ''} | {desc} | {_money(li.get('sell_price'), cur)} |")
    out.append(f"| | **Total** | **{_money(version.get('total_sell_price'), cur)}** |")
    out.append("")
    for title, key in [("Inclusions", "inclusions"), ("Exclusions", "exclusions"),
                       ("Assumptions", "assumptions"), ("Clarifications", "clarifications")]:
        items = _lines(version.get(key))
        if items:
            out.append(f"## {title}")
            out.extend(f"- {i}" for i in items)
            out.append("")
    if version.get("terms"):
        out.append("## Terms & conditions")
        out.append(version["terms"]); out.append("")
    return "\n".join(out)


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _list_block(title: str, items: list[str]) -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{_esc(i)}</li>" for i in items)
    return f"<section><h2>{_esc(title)}</h2><ul>{lis}</ul></section>"


def proposal_html(version: dict, line_items: list[dict]) -> str:
    cur = version.get("currency", "USD")
    rows = ""
    for li in line_items:
        desc = _esc(li.get("description"))
        if li.get("location"):
            desc += f' <span class="loc">({_esc(li["location"])})</span>'
        qty = ""
        if li.get("quantity"):
            qty = f'{_esc(li.get("quantity"))} {_esc(li.get("unit"))}'
        rows += (f'<tr><td>{_esc(li.get("section"))}</td><td>{desc}</td>'
                 f'<td class="num">{_esc(qty)}</td>'
                 f'<td class="money">{_money(li.get("sell_price"), cur)}</td></tr>')
    lists = "".join([
        _list_block("Inclusions", _lines(version.get("inclusions"))),
        _list_block("Exclusions", _lines(version.get("exclusions"))),
        _list_block("Assumptions", _lines(version.get("assumptions"))),
        _list_block("Clarifications", _lines(version.get("clarifications"))),
    ])
    terms = (f'<section><h2>Terms &amp; Conditions</h2><p class="terms">'
             f'{_esc(version.get("terms"))}</p></section>') if version.get("terms") else ""
    cover = f'<p class="cover">{_esc(version.get("cover_notes"))}</p>' if version.get("cover_notes") else ""
    meta = "".join(filter(None, [
        f'<div><span>Prepared for</span><strong>{_esc(version.get("client_name"))}</strong></div>',
        f'<div><span>Attn</span><strong>{_esc(version.get("client_contact"))}</strong></div>' if version.get("client_contact") else "",
        f'<div><span>Prepared by</span><strong>{_esc(version.get("prepared_by"))}</strong></div>' if version.get("prepared_by") else "",
        f'<div><span>Valid until</span><strong>{_esc(version.get("valid_until"))}</strong></div>' if version.get("valid_until") else "",
        f'<div><span>Status</span><strong>{_esc(version.get("status"))}</strong></div>',
    ]))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Proposal {_esc(version.get('proposal_number') or '')}</title>
<style>
  :root {{ --ink:#1a1a1a; --muted:#666; --line:#ddd; --accent:#0b5; }}
  * {{ box-sizing: border-box; }}
  body {{ font: 14px/1.5 -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
          color: var(--ink); margin: 0; padding: 2rem; background:#fff; }}
  .doc {{ max-width: 800px; margin: 0 auto; }}
  header.top {{ display:flex; justify-content:space-between; align-items:flex-start;
                border-bottom: 3px solid var(--accent); padding-bottom: 1rem; }}
  header.top h1 {{ font-size: 1.5rem; margin: 0; }}
  .num-badge {{ text-align:right; color: var(--muted); }}
  .meta {{ display:grid; grid-template-columns: repeat(auto-fit,minmax(160px,1fr));
           gap:.5rem 1.5rem; margin: 1.2rem 0; }}
  .meta div span {{ display:block; color: var(--muted); font-size:.75rem;
                    text-transform:uppercase; letter-spacing:.04em; }}
  .cover {{ margin: 1rem 0; }}
  table {{ width:100%; border-collapse: collapse; margin: 1rem 0; }}
  th, td {{ text-align:left; padding:.55rem .5rem; border-bottom:1px solid var(--line);
            vertical-align: top; }}
  th {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
  td.money, th.money, .money {{ text-align:right; white-space:nowrap; font-variant-numeric: tabular-nums; }}
  td.num {{ text-align:right; color: var(--muted); white-space:nowrap; }}
  .loc {{ color: var(--muted); }}
  tfoot td {{ font-weight:700; border-top:2px solid var(--ink); border-bottom:none;
              font-size:1.05rem; }}
  h2 {{ font-size: .95rem; text-transform:uppercase; letter-spacing:.04em;
        border-bottom:1px solid var(--line); padding-bottom:.25rem; margin-top:1.5rem; }}
  ul {{ margin:.5rem 0; padding-left: 1.2rem; }}
  .terms {{ white-space: pre-wrap; color:#333; }}
  footer {{ margin-top:2rem; color: var(--muted); font-size:.8rem;
            border-top:1px solid var(--line); padding-top:.75rem; }}
  @media print {{ body {{ padding:0; }} }}
</style></head>
<body><div class="doc">
  <header class="top">
    <h1>Proposal</h1>
    <div class="num-badge"><div><strong>{_esc(version.get('proposal_number') or 'DRAFT')}</strong></div>
      <div>Rev {_esc(version.get('version_number'))}</div></div>
  </header>
  <div class="meta">{meta}</div>
  {cover}
  <section>
    <h2>Scope of Work</h2>
    <table>
      <thead><tr><th>Section</th><th>Description</th><th class="num">Qty</th>
        <th class="money">Price</th></tr></thead>
      <tbody>{rows}</tbody>
      <tfoot><tr><td colspan="3">Total ({_esc(cur)})</td>
        <td class="money">{_money(version.get('total_sell_price'), cur)}</td></tr></tfoot>
    </table>
  </section>
  {lists}
  {terms}
  <footer>This proposal is valid until the date shown above. All prices are in
    {_esc(cur)}. Generated deterministically by Mobi.</footer>
</div></body></html>"""
