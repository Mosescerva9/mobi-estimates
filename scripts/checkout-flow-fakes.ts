import crypto from "crypto";

/**
 * Minimal in-memory stand-in for the subset of the supabase-js query builder
 * used by `src/lib/checkout-claims.ts` and `src/lib/entitlement.ts`. It never
 * touches the network — every operation reads/writes a plain in-memory table.
 * Not a general-purpose Supabase mock; only implements the chains those two
 * modules actually call.
 */

type Row = Record<string, unknown>;
type FilterFn = (row: Row) => boolean;
type PendingOp =
  | { kind: "insert"; payload: Row }
  | { kind: "update"; payload: Row }
  | { kind: "upsert"; payload: Row; onConflict: string }
  | { kind: "delete" };

const UNIQUE_KEYS: Record<string, string[]> = {
  checkout_claims: ["claim_token", "stripe_checkout_session_id"],
  webhook_events: ["id"],
};

class FakeQueryBuilder {
  private filters: FilterFn[] = [];
  private orderKey: string | null = null;
  private orderAscending = true;
  private limitCount: number | null = null;
  private op: PendingOp | null = null;

  constructor(
    private readonly db: FakeSupabaseAdmin,
    private readonly table: string,
  ) {}

  select(_columns?: string): this {
    return this;
  }

  eq(column: string, value: unknown): this {
    this.filters.push((row) => row[column] === value);
    return this;
  }

  is(column: string, value: null): this {
    this.filters.push((row) => (row[column] ?? null) === value);
    return this;
  }

  not(column: string, _operator: string, value: unknown): this {
    this.filters.push((row) => (row[column] ?? null) !== value);
    return this;
  }

  order(column: string, opts?: { ascending?: boolean }): this {
    this.orderKey = column;
    this.orderAscending = opts?.ascending ?? true;
    return this;
  }

  limit(count: number): this {
    this.limitCount = count;
    return this;
  }

  insert(payload: Row): this {
    this.op = { kind: "insert", payload };
    return this;
  }

  update(payload: Row): this {
    this.op = { kind: "update", payload };
    return this;
  }

  upsert(payload: Row, opts: { onConflict: string }): this {
    this.op = { kind: "upsert", payload, onConflict: opts.onConflict };
    return this;
  }

  delete(): this {
    this.op = { kind: "delete" };
    return this;
  }

  async maybeSingle(): Promise<{ data: Row | null; error: { message: string } | null }> {
    try {
      if (this.op) {
        const { data } = this.applyOp();
        return { data: (data as Row) ?? null, error: null };
      }
      const rows = this.matchingRows();
      return { data: rows[0] ?? null, error: null };
    } catch (e) {
      return { data: null, error: { message: (e as Error).message } };
    }
  }

  /** Makes bare `await builder` (no .maybeSingle()) resolve like supabase-js does. */
  then<T1, T2>(
    onfulfilled?: (value: { data: unknown; error: { message: string } | null }) => T1,
    onrejected?: (reason: unknown) => T2,
  ) {
    const settle = async () => {
      try {
        if (this.op) return this.applyOp();
        return { data: this.matchingRows(), error: null };
      } catch (e) {
        return { data: null, error: { message: (e as Error).message } };
      }
    };
    return settle().then(onfulfilled, onrejected);
  }

  private matchingRows(): Row[] {
    let rows = this.db.rows(this.table).filter((row) => this.filters.every((f) => f(row)));
    if (this.orderKey) {
      const key = this.orderKey;
      rows = [...rows].sort((a, b) => {
        const av = a[key] as string;
        const bv = b[key] as string;
        const cmp = av < bv ? -1 : av > bv ? 1 : 0;
        return this.orderAscending ? cmp : -cmp;
      });
    }
    if (this.limitCount != null) rows = rows.slice(0, this.limitCount);
    return rows;
  }

  private applyOp(): { data: unknown; error: { message: string } | null } {
    const op = this.op!;
    const all = this.db.rows(this.table);

    if (op.kind === "insert") {
      const row: Row = { id: crypto.randomUUID(), ...op.payload };
      const conflictKey = (UNIQUE_KEYS[this.table] ?? []).find(
        (key) => row[key] != null && all.some((r) => r[key] === row[key]),
      );
      if (conflictKey) {
        return { data: null, error: { message: `duplicate key value violates unique constraint on "${conflictKey}"` } };
      }
      all.push(row);
      return { data: row, error: null };
    }

    if (op.kind === "update") {
      const matches = all.filter((row) => this.filters.every((f) => f(row)));
      matches.forEach((row) => Object.assign(row, op.payload));
      return { data: matches[0] ?? null, error: null };
    }

    if (op.kind === "upsert") {
      const key = op.onConflict;
      const existing = all.find((row) => row[key] === op.payload[key]);
      if (existing) {
        Object.assign(existing, op.payload);
        return { data: existing, error: null };
      }
      const row: Row = { id: crypto.randomUUID(), ...op.payload };
      all.push(row);
      return { data: row, error: null };
    }

    // delete
    const remaining = all.filter((row) => !this.filters.every((f) => f(row)));
    this.db.setRows(this.table, remaining);
    return { data: null, error: null };
  }
}

/**
 * Stands in for the service-role Supabase client. Guardrail: this class makes
 * no network calls under any circumstance, so it is safe to construct even if
 * live-looking credentials are present in the environment (see the harness
 * entrypoint for the explicit check).
 */
export class FakeSupabaseAdmin {
  private tables = new Map<string, Row[]>();

  rows(table: string): Row[] {
    if (!this.tables.has(table)) this.tables.set(table, []);
    return this.tables.get(table)!;
  }

  setRows(table: string, rows: Row[]): void {
    this.tables.set(table, rows);
  }

  from(table: string): FakeQueryBuilder {
    return new FakeQueryBuilder(this, table);
  }

  seed(table: string, rows: Row[]): void {
    this.setRows(table, rows.map((r) => ({ ...r })));
  }
}
