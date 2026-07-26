import { statusLabel } from "@/lib/status";
import type { ItemStatus } from "@/lib/types";

export function StatusPill({
  status,
  label,
}: {
  status: ItemStatus;
  /** Optional owner-facing override (e.g. a completed comment reads "Commented"). */
  label?: string;
}) {
  return (
    <span className="status-pill">
      <span className={`status-dot ${status}`} />
      {label ?? statusLabel(status)}
    </span>
  );
}
