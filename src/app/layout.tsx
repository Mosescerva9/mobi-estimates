import type { Metadata } from "next";
import "./globals.css";

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
      <body className="antialiased">{children}</body>
    </html>
  );
}
