import { statusLabel } from "@/lib/status";
import type { ItemStatus } from "@/lib/types";

export function StatusPill({ status }: { status: ItemStatus }) {
  return (
    <span className="status-pill">
      <span className={`status-dot ${status}`} />
      {statusLabel(status)}
    </span>
  );
}
