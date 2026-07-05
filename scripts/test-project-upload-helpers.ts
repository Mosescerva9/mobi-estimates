import {
  MAX_FILES,
  buildStoragePath,
  isAllowedExtension,
  mergePickedFiles,
  sanitizeFilename,
  validateProjectFile,
} from "../src/lib/projects";

/**
 * Offline guard for the project-file upload helpers shared by NewProjectForm
 * and AddProjectFilesForm: extension/size/empty-file validation, the
 * MAX_FILES overflow report (no silent drop), and storage-path uniqueness.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
function test(name: string, fn: () => void) {
  tests.push({ name, fn });
}

test("allowed extensions are case-insensitive", () => {
  assert(isAllowedExtension("plans.PDF"), "expected .PDF to be allowed");
  assert(isAllowedExtension("plans.Dwg"), "expected .Dwg to be allowed");
  assert(isAllowedExtension("photo.JPEG"), "expected .JPEG to be allowed");
});

test("disallowed extensions are rejected regardless of case", () => {
  assert(!isAllowedExtension("virus.EXE"), "expected .EXE to be rejected");
  assert(!isAllowedExtension("notes.txt"), "expected .txt to be rejected");
  assert(!isAllowedExtension("no-extension"), "expected a file with no extension to be rejected");
});

test("sanitizeFilename strips path separators", () => {
  assert(
    sanitizeFilename("../../etc/passwd.pdf") === "passwd.pdf",
    `expected path traversal to be stripped, got ${sanitizeFilename("../../etc/passwd.pdf")}`,
  );
  assert(
    sanitizeFilename("C:\\Users\\me\\plans.dwg") === "plans.dwg",
    `expected Windows path to be stripped, got ${sanitizeFilename("C:\\Users\\me\\plans.dwg")}`,
  );
});

test("sanitizeFilename replaces unsafe characters and preserves extension", () => {
  const result = sanitizeFilename("my plan (rev #2)!.pdf");
  assert(result.endsWith(".pdf"), `expected .pdf extension preserved, got ${result}`);
  assert(!/[^a-zA-Z0-9._-]/.test(result), `expected only safe chars, got ${result}`);
});

test("sanitizeFilename never returns an empty stem", () => {
  const result = sanitizeFilename("###.pdf");
  assert(result === "file.pdf", `expected fallback stem "file", got ${result}`);
});

test("zero-byte files are rejected", () => {
  const error = validateProjectFile({ name: "empty.pdf", size: 0 });
  assert(error === "File is empty", `expected empty-file error, got ${error}`);
});

test("negative size is treated as empty (defensive)", () => {
  const error = validateProjectFile({ name: "weird.pdf", size: -1 });
  assert(error === "File is empty", `expected empty-file error, got ${error}`);
});

test("oversize files are rejected", () => {
  const error = validateProjectFile({ name: "huge.pdf", size: 26214401 });
  assert(error?.startsWith("Too large"), `expected size error, got ${error}`);
});

test("unsupported extension is rejected before the size check", () => {
  const error = validateProjectFile({ name: "app.exe", size: 100 });
  assert(error === "Unsupported file type", `expected extension error, got ${error}`);
});

test("valid file passes with no error", () => {
  const error = validateProjectFile({ name: "plan.pdf", size: 1024 });
  assert(error === undefined, `expected no error, got ${error}`);
});

test("selecting more than MAX_FILES reports the overflow instead of silently dropping", () => {
  const existing = Array.from({ length: MAX_FILES - 2 }, (_, i) => i);
  const incoming = [100, 101, 102, 103, 104]; // 5 more, only 2 fit
  const { combined, overflow } = mergePickedFiles(existing, incoming);
  assert(combined.length === MAX_FILES, `expected combined length ${MAX_FILES}, got ${combined.length}`);
  assert(overflow === 3, `expected overflow of 3, got ${overflow}`);
  assert(combined[combined.length - 1] === 101, `expected the first 2 overflow files to be kept, got ${combined[combined.length - 1]}`);
});

test("selecting within MAX_FILES reports zero overflow", () => {
  const { combined, overflow } = mergePickedFiles([1, 2], [3, 4]);
  assert(overflow === 0, `expected zero overflow, got ${overflow}`);
  assert(combined.length === 4, `expected combined length 4, got ${combined.length}`);
});

test("storage paths retain the {company}/{project}/ prefix", () => {
  const path = buildStoragePath("company-1", "project-1", "plan.pdf");
  assert(path.startsWith("company-1/project-1/"), `expected company/project prefix, got ${path}`);
  assert(path.endsWith("plan.pdf"), `expected filename preserved at the end, got ${path}`);
});

test("repeated same-name uploads produce unique storage paths", () => {
  const paths = new Set<string>();
  for (let i = 0; i < 50; i++) {
    paths.add(buildStoragePath("company-1", "project-1", "same-name.pdf"));
  }
  assert(paths.size === 50, `expected 50 unique paths, got ${paths.size}`);
  for (const p of paths) {
    assert(p.startsWith("company-1/project-1/"), `expected prefix retained, got ${p}`);
  }
});

function main(): void {
  let failures = 0;
  for (const t of tests) {
    try {
      t.fn();
      console.log(`  PASS  ${t.name}`);
    } catch (e) {
      failures += 1;
      const message = e instanceof Error ? e.message : String(e);
      console.error(`  FAIL  ${t.name}`);
      console.error(`        ${message}`);
    }
  }

  console.log("");
  console.log(`${tests.length - failures}/${tests.length} passed`);
  if (failures > 0) {
    process.exit(1);
  }
}

main();
