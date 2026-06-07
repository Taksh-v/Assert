"use client";

import React, { useState, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Sidebar from "./Sidebar";
import { isAuthenticated, AUTH_CHANGE_EVENT } from "@/lib/auth";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<boolean>(false);
  const [mounted, setMounted] = useState<boolean>(false);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    setMounted(true);
    const authed = isAuthenticated();
    setAuth(authed);

    // If not authenticated and not already on the auth page, redirect to auth
    if (!authed && pathname !== "/auth") {
      router.push("/auth");
    }
    // If authenticated and on the auth page, redirect to home
    else if (authed && pathname === "/auth") {
      router.push("/");
    }

    const handleAuthChange = () => {
      const currentAuth = isAuthenticated();
      setAuth(currentAuth);
      if (!currentAuth) {
        router.push("/auth");
      } else if (pathname === "/auth") {
        router.push("/");
      }
    };

    window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    return () => {
      window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    };
  }, [pathname, router]);

  if (!mounted) {
    return <div className="h-screen w-screen bg-[var(--bg-root)]" />;
  }

  // If we are on the auth page, just render the children (which will be our AuthPortal page)
  if (pathname === "/auth") {
    return <div className="h-screen w-screen overflow-auto">{children}</div>;
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[var(--bg-root)] text-[var(--text-primary)] animate-fade-in">
      <Sidebar />
      <main className="flex-1 overflow-hidden h-full relative flex flex-col">
        {children}
      </main>
    </div>
  );
}
