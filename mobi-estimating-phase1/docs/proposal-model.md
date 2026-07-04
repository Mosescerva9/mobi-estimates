# Proposal Model

## Entities

- **proposals** — one per client offer for a project's estimate (`estimate_id`,
  `client_name`, `current_version_id`).
- **proposal_versions** — immutable once issued. Fields: `version_number`, `status`,
  `proposal_number`, `prepared_by`, `client_name/contact`, `valid_until`,
  `detail_level`, `currency`, `total_sell_price`, `cover_notes`, `terms`,
  `inclusions/exclusions/assumptions/clarifications`, `snapshot_hash`, lifecycle
  timestamps (`issued_at`, `accepted_at`, `declined_at`, `decline_reason`,
  `superseded_at`), and the source `estimate_version_id`.
- **proposal_line_items** — client-facing rows: `section`, `trade_code`,
  `category_code`, `description`, `location`, `quantity`, `unit`, **`sell_price`**.
  No cost/margin/rate/hour fields exist on this table by design.
- **proposal_snapshots** — normalized JSON of the resolved client-facing content +
  SHA-256 for reproducibility.
- **proposal_review_events** — append-only lifecycle log (issue/accept/decline/
  supersede/expire).

## Sell-price allocation

Phase 4 applies overhead/profit/tax at the estimate level, so a proposal allocates
the estimate's **final sell price** across trades (or lines) in proportion to each
group's direct cost using the largest-remainder method. This keeps client sell
prices reconciled to the estimate total exactly while never exposing the cost basis.

## Lifecycle & rules

- Build requires an **approved** estimate version.
- `draft → issued`: assigns a proposal number (auto `P-<id8>-<vv>` if none), stores
  the snapshot, and freezes the version.
- `issued → accepted | declined`: client response; decline requires a reason.
- `issued → expired`: lazily set when read past `valid_until`.
- `regenerate`: creates a new version from the current approved estimate version and
  supersedes the prior version — unless it was already accepted.
- Exports (HTML/Markdown/JSON) render sell + scope only.
