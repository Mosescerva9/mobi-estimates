// End-to-end staff workbench runtime harness (internal/local only).
//
// Proves the full slice against the REAL merged OpenTakeoff runtime:
//   public fixture -> C011 -> confirm scale -> line coords ->
//   actual OpenTakeoff MCP subprocess -> 37.5 LF -> approve ->
//   canonical evidence-like record persisted to a temp file -> reload -> verify.
//
// It shells out to the Python bridge (scripts/opentakeoff_workbench_bridge.py),
// which drives the pinned local opentakeoff-mcp subprocess. No mocks, no
// confidential files, persist=False on the Python side (nothing hits a real DB).
//
// Run: npm run harness:estimator-takeoff-workbench

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  applyWorkbenchAction,
  defaultTrainingEligibility,
  previewFromRuntimePayload,
  type RuntimeBridgePayload,
} from "../src/lib/estimator-takeoff-workbench";

const REPO_ROOT = path.resolve(__dirname, "..");
const PHASE1 = path.join(REPO_ROOT, "mobi-estimating-phase1");

function runPythonBridge(outPath: string): RuntimeBridgePayload {
  const result = spawnSync(
    "python",
    ["scripts/opentakeoff_workbench_bridge.py", "--out", outPath],
    {
      cwd: PHASE1,
      env: { ...process.env, MOBI_DEPLOYMENT_ENVIRONMENT: "local", PYTHONPATH: "." },
      encoding: "utf-8",
      timeout: 180_000,
    },
  );
  if (result.status !== 0) {
    throw new Error(
      `Python runtime bridge failed (status ${result.status}):\n${result.stderr || result.stdout}`,
    );
  }
  return JSON.parse(readFileSync(outPath, "utf-8")) as RuntimeBridgePayload;
}

function main(): void {
  const tempDir = mkdtempSync(path.join(tmpdir(), "mobi-workbench-"));
  const bridgeOut = path.join(tempDir, "runtime-c011.json");
  const evidenceStore = path.join(tempDir, "canonical-evidence.json");
  try {
    console.log("[1] Driving real OpenTakeoff MCP runtime against public C011 fixture...");
    const payload = runPythonBridge(bridgeOut);

    // Assert the ACTUAL runtime measurement, not a fabricated frontend object.
    assert.equal(payload.runtime, "real_opentakeoff_mcp_subprocess");
    assert.equal(payload.provider, "open_takeoff");
    assert.equal(payload.quantity, 37.5, "expected real runtime to measure 37.5 LF");
    assert.equal(payload.unit, "LF");
    assert.equal(payload.sheet_label, "C011");
    assert.equal(payload.page_number, 4);
    assert.equal(payload.scale, "units_per_px:0.08012820512820511");
    console.log(
      `    -> ${payload.quantity} ${payload.unit} on ${payload.sheet_label} p${payload.page_number} ` +
        `via ${payload.engine_version} (${payload.scale})`,
    );

    console.log("[2] Mapping runtime evidence into staff workbench preview...");
    const preview = previewFromRuntimePayload(payload);
    assert.equal(preview.provenance, "OpenTakeoff measured");
    assert.equal(preview.reviewStatus, "pending");
    assert.equal(
      defaultTrainingEligibility(preview.provenance, preview.reviewStatus),
      "not_training_eligible",
      "unreviewed runtime output must not be training-eligible",
    );

    console.log("[3] Staff approves the measurement...");
    const decision = applyWorkbenchAction(preview, "approve", {
      reviewer: "staff:harness",
      timestamp: new Date("2026-07-16T00:00:00.000Z").toISOString(),
    });
    assert.equal(decision.preview.reviewStatus, "approved");
    assert.equal(decision.preview.provenance, "OpenTakeoff measured");

    console.log("[4] Persisting canonical evidence-like record to temp store...");
    const canonicalRecord = {
      takeoff_provider: decision.preview.provider,
      evidence_class: decision.preview.evidenceClass,
      provenance_label: decision.preview.provenance,
      review_status: decision.preview.reviewStatus,
      reviewed_by: decision.preview.reviewer,
      sheet_id: decision.preview.sheetId,
      page_number: decision.preview.pageNumber,
      scale: decision.preview.scaleLabel,
      quantity: decision.preview.quantity,
      unit: decision.preview.unit,
      trade: decision.preview.trade,
      scope_category: decision.preview.scopeCategory,
      condition: decision.preview.condition,
      engine_version: decision.preview.engineVersion,
      region_coordinates: decision.preview.sourceRegion,
      marked_geometry: decision.preview.markedGeometry,
      training_eligibility: defaultTrainingEligibility(
        decision.preview.provenance,
        decision.preview.reviewStatus,
      ),
    };
    writeFileSync(evidenceStore, JSON.stringify(canonicalRecord, null, 2));

    console.log("[5] Reloading persisted record and verifying round-trip...");
    const reloaded = JSON.parse(readFileSync(evidenceStore, "utf-8"));
    assert.deepEqual(reloaded, canonicalRecord);
    assert.equal(reloaded.quantity, 37.5);
    assert.equal(reloaded.unit, "LF");
    assert.equal(reloaded.takeoff_provider, "open_takeoff");
    assert.equal(reloaded.review_status, "approved");
    assert.equal(reloaded.provenance_label, "OpenTakeoff measured");

    console.log("\nWORKBENCH E2E HARNESS: PASS");
    console.log(`  ${reloaded.quantity} ${reloaded.unit} (${reloaded.provenance_label}, ${reloaded.review_status})`);
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
}

main();
