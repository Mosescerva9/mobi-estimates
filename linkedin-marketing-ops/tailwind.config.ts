import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        steel: {
          50: "#f2f5f8",
          100: "#e4ebf2",
          200: "#c8d5e3",
          700: "#334155",
          900: "#0f1724",
        },
        blueprint: {
          DEFAULT: "#1f6b8a",
          dark: "#164e66",
          soft: "#d7ebf3",
        },
        signal: {
          DEFAULT: "#c45c26",
          soft: "#f6e4d8",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "Segoe UI", "sans-serif"],
        sans: ["var(--font-sans)", "Segoe UI", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
