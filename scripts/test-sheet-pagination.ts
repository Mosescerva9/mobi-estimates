import { fetchAllEngineSheets, ENGINE_SHEETS_PAGE_LIMIT, type EngineSheetSummary } from "../src/lib/engine";

/**
 * Coverage for the portal-side engine sheet pagination walk. The engine's
 * GET /sheets endpoint caps `limit` at 200/request (app/routers_processing.py);
 * a >200-page joined packet (e.g. the 302-page authoritative packet with
 * verified sheet A101 at page 282) must still be fully enumerable so staff can
 * select it in the takeoff workbench. Every malformed/non-progress/duplicate
 * response must fail closed rather than loop forever or silently truncate.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => Promise<void> };
const tests: Test[] = [];
const test = (name: string, fn: () => Promise<void>) => tests.push({ name, fn });

function sheet(pageNumber: number): EngineSheetSummary {
  return {
    sheet_id: `sheet-${pageNumber}`,
    pdf_page_number: pageNumber,
    detected_sheet_number: null,
    verified_sheet_number: pageNumber === 282 ? "A101" : null,
    detected_sheet_title: null,
    verified_sheet_title: null,
    text_layer_quality: "vector",
    processing_status: "completed",
    review_status: "verified",
  };
}

/** Build a paged fetcher over a full in-memory sheet list, mirroring the
 * engine's real `limit`/`offset`/`total` echo contract. */
function fakeEngine(totalSheets: number) {
  const all = Array.from({ length: totalSheets }, (_, i) => sheet(i + 1));
  return async (limit: number, offset: number) => ({
    items: all.slice(offset, offset + limit),
    total: totalSheets,
    limit,
    offset,
  });
}

async function expectReject(fetchPage: (limit: number, offset: number) => Promise<unknown>, label: string) {
  let threw = false;
  try {
    await fetchAllEngineSheets(fetchPage);
  } catch {
    threw = true;
  }
  assert(threw, `${label} should have been rejected`);
}

test("a 302-sheet project returns every sheet including page 282 (A101)", async () => {
  const result = await fetchAllEngineSheets(fakeEngine(302));
  assert(result.total === 302, `expected total=302, got ${result.total}`);
  assert(result.items.length === 302, `expected 302 items, got ${result.items.length}`);
  const page282 = result.items.find((s) => s.pdf_page_number === 282);
  assert(Boolean(page282), "page 282 must be present in the fetched sheet set");
  assert(page282?.verified_sheet_number === "A101", "page 282 must carry the verified sheet number A101");
  // Deterministic pdf_page_number ASC ordering is preserved end-to-end.
  for (let i = 1; i < result.items.length; i += 1) {
    assert(
      result.items[i - 1].pdf_page_number < result.items[i].pdf_page_number,
      "sheets must stay ordered by pdf_page_number ascending across page boundaries",
    );
  }
});

test("a project with exactly one page (<=200 sheets) makes one request", async () => {
  let calls = 0;
  const fetchPage = async (limit: number, offset: number) => {
    calls += 1;
    return fakeEngine(150)(limit, offset);
  };
  const result = await fetchAllEngineSheets(fetchPage);
  assert(calls === 1, `expected exactly one page request, got ${calls}`);
  assert(result.items.length === 150, "all 150 sheets must be returned");
});

test("each page request respects the <=200 per-request limit", async () => {
  const seenLimits: number[] = [];
  const inner = fakeEngine(450);
  const fetchPage = async (limit: number, offset: number) => {
    seenLimits.push(limit);
    return inner(limit, offset);
  };
  await fetchAllEngineSheets(fetchPage);
  assert(
    seenLimits.every((l) => l <= ENGINE_SHEETS_PAGE_LIMIT),
    "no page request may ask for more than the engine's 200-item cap",
  );
});

test("oversized page (more items than the requested limit) fails closed", async () => {
  // The sane total cap is only checked against the declared `total`, so a server
  // that overfills each page could otherwise hand back far more rows than the cap.
  await expectReject(
    async (limit, offset) => ({
      items: Array.from({ length: limit + 1 }, (_, i) => sheet(offset + i + 1)),
      total: 5000,
      limit,
      offset,
    }),
    "a page larger than the requested limit",
  );
});

test("empty project (zero sheets) returns an empty, valid result", async () => {
  const result = await fetchAllEngineSheets(fakeEngine(0));
  assert(result.total === 0 && result.items.length === 0, "zero-sheet project must return an empty set, not throw");
});

test("malformed page shape fails closed", async () => {
  await expectReject(async () => ({ not: "a valid page" }), "malformed page shape");
});

test("negative total fails closed", async () => {
  await expectReject(async (limit, offset) => ({ items: [], total: -1, limit, offset }), "negative total");
});

test("offset echo mismatch fails closed (never trusts an inconsistent server)", async () => {
  await expectReject(
    async (limit, offset) => ({
      items: [{ sheet_id: "s1", pdf_page_number: 1 }],
      total: 5,
      limit,
      offset: offset + 7, // echoes back a different offset than requested
    }),
    "offset echo mismatch",
  );
});

test("total beyond the sane sheet cap fails closed", async () => {
  await expectReject(fakeEngine(ENGINE_SHEETS_PAGE_LIMIT * 100), "total beyond the sane sheet cap");
});

test("total that changes mid-pagination fails closed", async () => {
  let call = 0;
  const fetchPage = async (limit: number, offset: number) => {
    call += 1;
    const total = call === 1 ? 500 : 300;
    const all = Array.from({ length: 500 }, (_, i) => sheet(i + 1));
    return { items: all.slice(offset, offset + limit), total, limit, offset };
  };
  await expectReject(fetchPage, "total that changes mid-pagination");
});

test("short non-final page fails closed instead of stalling", async () => {
  const fetchPage = async (limit: number, offset: number) => ({
    items: offset === 0 ? [sheet(1)] : [],
    total: 300,
    limit,
    offset,
  });
  await expectReject(fetchPage, "short non-final page (non-progress)");
});

test("zero-item page before total reached fails closed instead of looping forever", async () => {
  const fetchPage = async (limit: number, offset: number) => ({ items: [], total: 300, limit, offset });
  await expectReject(fetchPage, "zero-item page before total reached (non-progress)");
});

test("duplicate sheet_id across pages fails closed", async () => {
  const fetchPage = async (limit: number, offset: number) => {
    const items =
      offset === 0
        ? Array.from({ length: ENGINE_SHEETS_PAGE_LIMIT }, (_, i) => sheet(i + 1))
        : [sheet(1), ...Array.from({ length: 50 }, (_, i) => sheet(ENGINE_SHEETS_PAGE_LIMIT + i + 1))];
    return { items, total: 250, limit, offset };
  };
  await expectReject(fetchPage, "duplicate sheet_id across pages");
});

async function main() {
  let failures = 0;
  for (const t of tests) {
    try {
      await t.fn();
      console.log(`ok - ${t.name}`);
    } catch (error) {
      failures += 1;
      console.error(`FAIL - ${t.name}`);
      console.error(error instanceof Error ? error.message : error);
    }
  }

  if (failures > 0) {
    console.error(`\n${failures} of ${tests.length} sheet-pagination test(s) failed.`);
    process.exit(1);
  }
  console.log(`\nAll ${tests.length} sheet-pagination tests passed.`);
}

void main();
