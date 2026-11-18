import type { Metadata } from "next";
import { themeScript } from "@/lib/theme";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "TestHarbor",
  description: "Self-hosted test case management",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // The theme script sets class="dark" before React hydrates.
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
