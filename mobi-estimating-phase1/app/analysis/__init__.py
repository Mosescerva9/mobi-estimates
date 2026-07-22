"""GPT-5.6 structured project-analysis layer.

A fail-closed, source-grounded reasoning/review layer over already-extracted,
tenant-scoped source text. It produces Pydantic-validated project analysis via the
OpenAI Responses API + Structured Outputs (model alias ``gpt-5.6``, reasoning
effort ``medium``). It never authors measurements, quantities, prices, arithmetic,
totals, approval, or delivery status, and it never reaches arbitrary files, URLs,
tools, or secrets.
"""
