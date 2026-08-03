import type { ReactNode } from "react";
import { tokens } from "./tokens";

/**
 * A control that looks live but does nothing — every real Stripe action is
 * inert in this demonstration. Stays focusable, announces aria-disabled, shows
 * a tooltip, and carries sr-only text explaining why.
 */
export function InertButton({
  label,
  children,
  className = "",
  style,
}: {
  label: string;
  children: ReactNode;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <button
      type="button"
      aria-disabled="true"
      title={`${label} — unavailable in this demonstration`}
      onClick={(e) => e.preventDefault()}
      className={`sd-inert ${className}`}
      style={style}
    >
      {children}
      <span className="sr-only">
        {" "}
        {label} is unavailable in this visual demonstration.
      </span>
    </button>
  );
}

export function Card({
  children,
  className = "",
  style,
}: {
  children: ReactNode;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <section
      className={`bg-white ${className}`}
      style={{
        borderRadius: tokens.radius.card,
        border: `1px solid ${tokens.color.border}`,
        boxShadow: tokens.shadow.card,
        ...style,
      }}
    >
      {children}
    </section>
  );
}

type Tone = "success" | "info" | "warning" | "danger" | "neutral";

const toneMap: Record<Tone, { bg: string; fg: string }> = {
  success: { bg: tokens.color.successBg, fg: tokens.color.successText },
  info: { bg: tokens.color.infoBg, fg: tokens.color.infoText },
  warning: { bg: tokens.color.warningBg, fg: tokens.color.warningText },
  danger: { bg: tokens.color.dangerBg, fg: tokens.color.dangerText },
  neutral: { bg: "#eef2f6", fg: "#3c4257" },
};

export function StatusPill({
  children,
  tone = "success",
  dot = true,
}: {
  children: ReactNode;
  tone?: Tone;
  dot?: boolean;
}) {
  const { bg, fg } = toneMap[tone];
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-[2px] text-[12px] font-medium"
      style={{ background: bg, color: fg }}
    >
      {dot && (
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: fg }}
        />
      )}
      {children}
    </span>
  );
}

export function Avatar({ initials }: { initials: string }) {
  return (
    <span
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold"
      style={{ background: tokens.color.purpleSoft, color: tokens.color.purpleDark }}
    >
      {initials}
    </span>
  );
}
