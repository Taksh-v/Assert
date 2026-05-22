import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

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
      <body className={`${geistSans.variable} ${geistMono.variable} flex h-screen overflow-hidden bg-background text-foreground`}>
        <AppShell>
          {children}
        </AppShell>
      </body>
    </html>
  );
}
