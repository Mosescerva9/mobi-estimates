import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: "#16243f", deep: "#0c1830" },
        brand: { DEFAULT: "#2c5c9e", dark: "#244c84", light: "#5e86c4" },
      },
    },
  },
  plugins: [],
};
export default config;
