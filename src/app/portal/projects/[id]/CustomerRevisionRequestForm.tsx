type RevisionNoticeCode = "recorded" | "missing_text" | "engine_unavailable" | "project_unlinked" | "failed";

const REVISION_NOTICE_COPY: Record<RevisionNoticeCode, { tone: "success" | "warning" | "error"; message: string }> = {
  recorded: {
    tone: "success",
    message: "Revision request recorded. Mobi will review it and update the project if scope changes are needed.",
  },
  missing_text: {
    tone: "warning",
    message: "Please describe the change or question before submitting a revision request.",
  },
  engine_unavailable: {
    tone: "error",
    message: "Revision requests are temporarily unavailable. Please contact Mobi and include this project number.",
  },
  project_unlinked: {
    tone: "warning",
    message: "This project is not linked to the estimating workspace yet. Please contact Mobi for changes on this project.",
  },
  failed: {
    tone: "error",
    message: "We could not record the revision request right now. Please try again or contact Mobi directly.",
  },
};

export function revisionNoticeCopy(value: string | undefined): { tone: "success" | "warning" | "error"; message: string } | null {
  if (!value || !(value in REVISION_NOTICE_COPY)) return null;
  return REVISION_NOTICE_COPY[value as RevisionNoticeCode];
}

export function RevisionNotice({ code }: { code: string | undefined }) {
  const notice = revisionNoticeCopy(code);
  if (!notice) return null;
  const cls =
    notice.tone === "success"
      ? "border-green-200 bg-green-50 text-green-800"
      : notice.tone === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-800"
        : "border-red-200 bg-red-50 text-red-800";
  return <p className={`mt-4 rounded-lg border px-4 py-3 text-sm ${cls}`}>{notice.message}</p>;
}

export function CustomerRevisionRequestForm({
  action,
  projectId,
}: {
  action: (formData: FormData) => void;
  projectId: string;
}) {
  return (
    <form action={action} className="mt-4 space-y-3">
      <input type="hidden" name="projectId" value={projectId} />
      <div>
        <label htmlFor="revisionText" className="text-sm font-semibold text-navy">
          Describe the change or question
        </label>
        <textarea
          id="revisionText"
          name="revisionText"
          required
          minLength={1}
          maxLength={5000}
          rows={4}
          placeholder="Example: Please add the electrical outlets shown on E-101, or clarify whether door hardware is included."
          className="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-800 shadow-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
      </div>
      <p className="text-xs leading-relaxed text-slate-500">
        This records your requested revision for review. It does not approve, price, bill, or deliver a final estimate automatically.
      </p>
      <button
        type="submit"
        className="rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white shadow-sm hover:opacity-90"
      >
        Submit revision request
      </button>
    </form>
  );
}
