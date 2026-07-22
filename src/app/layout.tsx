import type { Metadata } from "next";
import { Poppins } from "next/font/google";
import "./globals.css";

// Poppins is open source under the SIL Open Font License and closely matches
// the clean geometric sans-serif hierarchy selected for the marketing redesign.
const poppins = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Mobi Estimates — Client Portal",
  description:
    "Submit projects, upload bid documents, track status, and receive estimates from Mobi Estimates.",
  robots: { index: false }, // portal is private
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${poppins.className} antialiased`}>{children}</body>
    </html>
  );
}
