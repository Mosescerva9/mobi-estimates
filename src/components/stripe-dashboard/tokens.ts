// Design tokens for the Stripe Dashboard demonstration. Typed object so both
// TS components and the scoped stripe-demo.css stay in lockstep. These are
// hand-tuned to resemble Stripe's dashboard; nothing here is proprietary.

export const tokens = {
  color: {
    purple: "#635bff",
    purpleDark: "#5147ff",
    purpleSoft: "#f0efff",
    ink: "#0a2540",
    text: "#3c4257",
    muted: "#697386",
    faint: "#8792a2",
    bg: "#f6f9fc",
    border: "#e6ebf1",
    borderSoft: "#eef2f6",
    successBg: "#d3f8df",
    successText: "#0e6245",
    infoBg: "#dde9ff",
    infoText: "#0b4f9e",
    warningBg: "#fdf3d8",
    warningText: "#8a5a00",
    dangerBg: "#fbe3e8",
    dangerText: "#a42538",
    white: "#ffffff",
  },
  radius: {
    card: "10px",
    control: "8px",
  },
  shadow: {
    card: "0 1px 1px rgba(16,24,40,0.04)",
  },
  font: {
    stack:
      'ui-sans-serif, -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif',
  },
  // The Stripe app header height (px).
  chrome: {
    header: 56,
  },
  chart: {
    grid: "#eef2f6",
    line: "#635bff",
    lineWidth: 1.75,
    areaTop: 0.14,
    areaBottom: 0.01,
    tooltipBg: "#0a2540",
  },
} as const;

export type Tokens = typeof tokens;
