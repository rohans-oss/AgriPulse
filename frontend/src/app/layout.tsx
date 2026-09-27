import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AgriFlow AI",
  description: "Agricultural supply-chain intelligence — core platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
