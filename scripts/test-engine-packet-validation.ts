import { validateEnginePacketResponse, type EnginePacketSource } from "../src/lib/engine";

/**
 * Adversarial coverage for the engine packet RESPONSE trust boundary. Every
 * malformed / inconsistent / spoofed engine response must be rejected by the
 * pure runtime validator BEFORE any DB write, and a faithful response must pass.
 * This tests the validator directly (no server-action mocking required).
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
const test = (name: string, fn: () => void) => tests.push({ name, fn });

const SHA_A = "a".repeat(64);
const SHA_B = "b".repeat(64);
const PACKET_SHA = "c".repeat(64);

// Two submitted sources; a stub Blob stands in for the source file.
const stubBlob = { size: 0 } as unknown as Blob;
function submitted(): EnginePacketSource[] {
  return [
    { file: stubBlob, fileName: "manual.pdf", projectFileId: "f1", storagePath: "p/manual.pdf", order: 0, declaredSha256: SHA_A, bytes: 100 },
    { file: stubBlob, fileName: "drawings.pdf", projectFileId: "f2", storagePath: "p/drawings.pdf", order: 1, declaredSha256: SHA_B, bytes: 200 },
  ];
}

function goodResponse(): unknown {
  return {
    project_id: "engine-1",
    name: "Project",
    status: "uploaded",
    original_file_name: "Project — combined packet.pdf",
    page_count: 5,
    file_sha256: PACKET_SHA,
    file_size_bytes: 999,
    created_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-01T00:00:00+00:00",
    error_message: null,
    portal_project_id: "portal-1",
    idempotent_reuse: false,
    packet_manifest: {
      schema_version: "engine_packet_v1",
      packet: { sha256: PACKET_SHA, bytes: 4242, page_count: 5, source_count: 2 },
      sources: [
        { order: 0, project_file_id: "f1", original_filename: "manual.pdf", storage_path: "p/manual.pdf", source_sha256: SHA_A, source_bytes: 100, source_page_count: 3, combined_page_start: 1, combined_page_end: 3 },
        { order: 1, project_file_id: "f2", original_filename: "drawings.pdf", storage_path: "p/drawings.pdf", source_sha256: SHA_B, source_bytes: 200, source_page_count: 2, combined_page_start: 4, combined_page_end: 5 },
      ],
    },
  };
}

const OPTS = { portalProjectId: "portal-1", expectedEngineProjectId: null };

function expectReject(raw: unknown, label: string, opts = OPTS) {
  let threw = false;
  try {
    validateEnginePacketResponse(raw, submitted(), opts);
  } catch {
    threw = true;
  }
  assert(threw, `${label} should have been rejected`);
}

test("faithful response passes and is returned validated", () => {
  const out = validateEnginePacketResponse(goodResponse(), submitted(), OPTS);
  assert(out.project_id === "engine-1", "project_id must survive validation");
  assert(out.packet_manifest.packet.source_count === 2, "source_count must survive");
});

test("expected engine id match passes", () => {
  const out = validateEnginePacketResponse(goodResponse(), submitted(), {
    portalProjectId: "portal-1",
    expectedEngineProjectId: "engine-1",
  });
  assert(out.project_id === "engine-1", "matching expected id must pass");
});

test("portal project id mismatch rejected", () => {
  expectReject(goodResponse(), "portal id mismatch", { portalProjectId: "OTHER", expectedEngineProjectId: null });
});

test("expected engine id mismatch rejected", () => {
  expectReject(goodResponse(), "engine id mismatch", { portalProjectId: "portal-1", expectedEngineProjectId: "engine-2" });
});

test("uppercase / non-64 sha rejected", () => {
  const r = goodResponse() as any;
  r.packet_manifest.packet.sha256 = PACKET_SHA.toUpperCase();
  expectReject(r, "uppercase packet sha");
  const r2 = goodResponse() as any;
  r2.file_sha256 = "abc";
  expectReject(r2, "short file sha");
});

test("file_sha256 not equal to packet sha rejected", () => {
  const r = goodResponse() as any;
  r.file_sha256 = "d".repeat(64);
  expectReject(r, "file sha != packet sha");
});

test("source_count mismatch rejected", () => {
  const r = goodResponse() as any;
  r.packet_manifest.packet.source_count = 3;
  expectReject(r, "source_count mismatch");
});

test("submitted source sha mismatch rejected", () => {
  const r = goodResponse() as any;
  r.packet_manifest.sources[0].source_sha256 = "e".repeat(64);
  expectReject(r, "source sha spoof");
});

test("submitted source byte-count mismatch rejected", () => {
  const r = goodResponse() as any;
  r.packet_manifest.sources[1].source_bytes = 999;
  expectReject(r, "source bytes mismatch");
});

test("wrong project_file_id / storage_path / filename rejected", () => {
  const bad = ["project_file_id", "storage_path", "original_filename"] as const;
  for (const key of bad) {
    const r = goodResponse() as any;
    r.packet_manifest.sources[0][key] = "TAMPERED";
    expectReject(r, `${key} tamper`);
  }
});

test("noncontiguous / non-covering page ranges rejected", () => {
  const r = goodResponse() as any;
  r.packet_manifest.sources[1].combined_page_start = 5; // gap after page 3
  expectReject(r, "noncontiguous pages");
  const r2 = goodResponse() as any;
  r2.packet_manifest.packet.page_count = 6; // pages do not cover
  expectReject(r2, "page coverage mismatch");
});

test("duplicate / noncontiguous orders rejected", () => {
  const r = goodResponse() as any;
  r.packet_manifest.sources[1].order = 0; // duplicate order
  expectReject(r, "duplicate order");
});

test("missing keys / null manifest / wrong types rejected", () => {
  expectReject({ ...(goodResponse() as any), packet_manifest: null }, "null manifest");
  const r = goodResponse() as any;
  delete r.portal_project_id;
  expectReject(r, "missing portal id");
  const r2 = goodResponse() as any;
  r2.packet_manifest.sources = "not-an-array";
  expectReject(r2, "sources not array");
  const r3 = goodResponse() as any;
  r3.page_count = "5";
  expectReject(r3, "page_count wrong type");
});

function main(): void {
  let failures = 0;
  for (const t of tests) {
    try {
      t.fn();
      console.log(`  PASS  ${t.name}`);
    } catch (e) {
      failures += 1;
      console.error(`  FAIL  ${t.name}`);
      console.error(`        ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  console.log(`\n${tests.length - failures}/${tests.length} passed`);
  if (failures > 0) process.exit(1);
}

main();
