# OpenTakeoff License Review

Updated: 2026-07-16T00:35Z

Source reviewed: `https://github.com/Kentucky-ai/opentakeoff`, cloned to `/tmp/opentakeoff-eval` at commit `36a9aa7ebe0a6dde116c0a3d68a16fe39a0c94bf`.

## Verdict
OpenTakeoff is usable for Mobi commercial evaluation/integration under Apache License 2.0, provided Mobi preserves the required license and NOTICE attribution and does not imply Kentucky AI endorsement.

This is an engineering/legal-compliance review, not formal legal advice.

## Files reviewed
- `LICENSE` — Apache License 2.0.
- `NOTICE` — `OpenTakeoff Copyright 2026 Kentucky AI and the OpenTakeoff contributors`.
- `THIRD-PARTY-NOTICES.md` — dependency notices.
- `mcp/package.json` — `license: Apache-2.0`, package `opentakeoff-mcp@0.1.1`.
- `README.md`, `mcp/README.md`, `docs/MCP.md` — integration and licensing claims.

## Apache 2.0 requirements
- Include a copy of the Apache 2.0 license when redistributing OpenTakeoff or derivative works.
- Preserve copyright, patent, trademark, and attribution notices that apply.
- Preserve a readable copy of NOTICE attributions when distributing derivatives.
- Mark modified files with prominent notices if Mobi modifies OpenTakeoff source files.
- Do not use licensor names/trademarks/product names except for reasonable origin attribution and NOTICE reproduction.

## NOTICE requirements
Required attribution currently found:

```text
OpenTakeoff
Copyright 2026 Kentucky AI and the OpenTakeoff contributors
```

If Mobi vendors or modifies OpenTakeoff code, preserve this NOTICE in Mobi’s third-party notices and add a Mobi modifications notice where appropriate.

## Third-party dependency notices
OpenTakeoff’s notice file lists:

| Project | License | Use |
|---|---|---|
| `pdfjs-dist` / pdf.js | Apache-2.0 | PDF parsing/rendering |
| React / `react-dom` | MIT | UI runtime |
| React Router | MIT | Routing |
| Vite | MIT | Build/dev server |
| fflate | MIT | ZIP plan set unpacking |
| pdf-lib | MIT | Image-to-PDF wrapping |
| TypeScript | Apache-2.0 | Type checking geometry libs |
| tsx | MIT | TS tests/runtime |
| MCP TypeScript SDK | MIT | MCP protocol layer |
| Zod | MIT | MCP input validation |
| FastAPI | MIT | Optional AI sandbox |
| Starlette | BSD-3-Clause | Optional AI sandbox |
| Uvicorn | BSD-3-Clause | Optional AI sandbox |
| Pydantic | MIT | Optional AI sandbox |

## Patent-related language
Apache 2.0 includes a contributor patent grant and patent-litigation termination clause. Mobi may use, modify, and distribute the work under the license, but patent litigation against the work/contributors can terminate patent rights granted under the license.

README mentions “Markup-as-label training data (patent pending)” for Kentucky AI research. This does not appear to change the Apache license on OpenTakeoff code, but Mobi should not copy proprietary research claims, models, or non-code assets beyond what is Apache-licensed in the repository.

## Commercial-use compatibility
Apache 2.0 permits commercial use, modification, sublicensing, and distribution if license/notice conditions are satisfied.

## Modifications documentation
Apache 2.0 requires modified files to carry prominent notices stating they were changed. Mobi should maintain `docs/legal/opentakeoff-modifications.md` or equivalent if source is vendored/modified.

## MCP package and browser engine license
- `mcp/package.json` declares `Apache-2.0`.
- Browser/web code is covered by the repository `LICENSE` and root notices.
- MCP imports the web engine modules directly, so preserve notices for both MCP and web engine if vendored.

## Proprietary/non-open references
README references Kentucky AI, Spline commercial app, proprietary AI models/research, and model cards. These are not automatically licensed to Mobi. Do not use proprietary Kentucky AI models, brand endorsements, private datasets, or non-included components unless separately and lawfully licensed.

## Mobi compliance rules
- Preserve OpenTakeoff `LICENSE`, `NOTICE`, and `THIRD-PARTY-NOTICES.md` if vendoring source.
- Attribute as third-party open-source measurement engine; do not imply endorsement.
- Do not copy Kentucky AI proprietary models, research claims, private datasets, or trademarks into Mobi marketing.
- Keep Mobi marketing language as “AI-powered, human-reviewed construction estimating,” not fully autonomous or guaranteed.
