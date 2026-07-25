import type { ItemStatus } from "@/lib/types";

export function StatusPill({ status }: { status: ItemStatus }) {
  return (
    <span className="status-pill">
      <span className={`status-dot ${status}`} />
      {status.replaceAll("_", " ")}
    </span>
  );
}
