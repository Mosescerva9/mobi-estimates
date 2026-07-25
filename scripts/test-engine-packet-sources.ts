import {
  resolveAcceptedPacketSources,
  type ActiveProjectFileRow,
  type RegisterDocumentRow,
} from "../src/lib/engine-packet-sources";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
const test = (name: string, fn: () => void) => tests.push({ name, fn });

const PROJECT = "project-1";
const COMPANY = "company-1";

function active(
  id: string,
  overrides: Partial<ActiveProjectFileRow> = {},
): ActiveProjectFileRow {
  return {
    id,
    project_id: PROJECT,
    company_id: COMPANY,
    storage_path: `${PROJECT}/${id}.pdf`,
    file_name: `${id}.pdf`,
    ...overrides,
  };
}

function registered(
  id: string,
  overrides: Partial<RegisterDocumentRow> = {},
): RegisterDocumentRow {
  return {
    project_file_id: id,
    project_id: PROJECT,
    company_id: COMPANY,
    storage_path: `${PROJECT}/${id}.pdf`,
    file_name: `${id}.pdf`,
    review_status: "accepted",
    ...overrides,
  };
}

function resolve(
  activeFiles: ActiveProjectFileRow[],
  register: RegisterDocumentRow[],
) {
  return resolveAcceptedPacketSources({
    projectId: PROJECT,
    companyId: COMPANY,
    activeFiles,
    register,
  });
}

function expectBlocked(
  label: string,
  activeFiles: ActiveProjectFileRow[],
  register: RegisterDocumentRow[],
) {
  const result = resolve(activeFiles, register);
  assert(!result.ok, `${label} must fail closed`);
}

test("faithful active accepted set resolves using active-file identity", () => {
  const result = resolve([active("f1"), active("f2")], [registered("f1"), registered("f2")]);
  assert(result.ok, "faithful accepted set must resolve");
  assert(result.acceptedDocs.length === 2, "both accepted documents must be returned exactly once");
  assert(result.acceptedDocs[0].storage_path === `${PROJECT}/f1.pdf`, "active storage identity must be returned");
});

test("unregistered active file blocks a stale register", () => {
  expectBlocked("missing register row", [active("f1"), active("f2")], [registered("f1")]);
});

test("stale extra or soft-deleted accepted row blocks", () => {
  // Soft-deleted files are omitted by the server query, so an accepted row that
  // names one has no active backing and must fail exactly like a stale extra.
  expectBlocked("stale extra accepted row", [active("f1")], [registered("f1"), registered("deleted")]);
});

test("cross-project accepted row blocks", () => {
  expectBlocked(
    "cross-project register row",
    [active("f1")],
    [registered("f1", { project_id: "other-project" })],
  );
});

test("cross-company accepted row blocks", () => {
  expectBlocked(
    "cross-company register row",
    [active("f1")],
    [registered("f1", { company_id: "other-company" })],
  );
});

test("unexpected active row from another project or company blocks", () => {
  expectBlocked(
    "cross-project active row",
    [active("f1", { project_id: "other-project" })],
    [registered("f1")],
  );
  expectBlocked(
    "cross-company active row",
    [active("f1", { company_id: "other-company" })],
    [registered("f1")],
  );
});

test("register path or name divergence blocks", () => {
  expectBlocked(
    "path mismatch",
    [active("f1")],
    [registered("f1", { storage_path: "other/path.pdf" })],
  );
  expectBlocked(
    "name mismatch",
    [active("f1")],
    [registered("f1", { file_name: "renamed.pdf" })],
  );
});

test("duplicate accepted rows for one active file block", () => {
  expectBlocked("duplicate accepted rows", [active("f1")], [registered("f1"), registered("f1")]);
});

test("pending or replacement-needed register rows block", () => {
  expectBlocked("pending row", [active("f1")], [registered("f1", { review_status: "pending" })]);
  expectBlocked(
    "replacement row",
    [active("f1")],
    [registered("f1", { review_status: "needs_replacement" })],
  );
});

test("empty accepted set and non-PDF accepted file block", () => {
  expectBlocked("empty accepted set", [active("f1")], [registered("f1", { review_status: "ignored" })]);
  expectBlocked(
    "non-PDF accepted file",
    [active("f1", { file_name: "notes.docx", storage_path: `${PROJECT}/notes.docx` })],
    [registered("f1", { file_name: "notes.docx", storage_path: `${PROJECT}/notes.docx` })],
  );
});

test("missing and duplicate active identities block", () => {
  expectBlocked("missing active id", [active("f1", { id: null })], [registered("f1")]);
  expectBlocked("duplicate active id", [active("f1"), active("f1")], [registered("f1")]);
});

function main(): void {
  let failures = 0;
  for (const item of tests) {
    try {
      item.fn();
      console.log(`  PASS  ${item.name}`);
    } catch (error) {
      failures += 1;
      console.error(`  FAIL  ${item.name}`);
      console.error(`        ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  console.log(`\n${tests.length - failures}/${tests.length} passed`);
  if (failures > 0) process.exit(1);
}

main();
