import type { Metadata } from "next";
import "./globals.css";

import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Assest — Company Brain",
  description: "AI-first Knowledge Engine for Indian Startups",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex h-screen overflow-hidden bg-background text-foreground">
        <AppShell>
          {children}
        </AppShell>
      </body>
    </html>
  );
}
