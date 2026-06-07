"use client";

import React, { useState, useEffect, useLayoutEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Sidebar from "./Sidebar";
import { isAuthenticated, AUTH_CHANGE_EVENT } from "@/lib/auth";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<boolean>(false);
  const [mounted, setMounted] = useState<boolean>(false);
  const pathname = usePathname();
  const router = useRouter();

  // Use useLayoutEffect for faster redirect before first paint
  useLayoutEffect(() => {
    const authed = isAuthenticated();
    setAuth(authed);
    setMounted(true);

    if (!authed && pathname !== "/auth") {
      router.replace("/auth");
    }
  }, [pathname, router]);

  useEffect(() => {
    const handleAuthChange = () => {
      const currentAuth = isAuthenticated();
      setAuth(currentAuth);
      if (!currentAuth && window.location.pathname !== "/auth") {
        router.replace("/auth");
      } else if (currentAuth && window.location.pathname === "/auth") {
        router.replace("/");
      }
    };

    window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    return () => {
      window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    };
  }, [pathname, router]);

  // Prevent hydration mismatch: only render after mount
  if (!mounted) {
    return (
      <div className="h-screen w-screen bg-[#020617] flex items-center justify-center">
        <div className="animate-pulse text-indigo-500/50 text-[10px] font-bold uppercase tracking-[0.3em]">
          Assest Brain Syncing...
        </div>
      </div>
    );
  }

  // Auth page rendering (no sidebar)
  if (pathname === "/auth") {
    return <div className="h-screen w-screen overflow-hidden">{children}</div>;
  }

  // Redirecting state
  if (!auth) {
    return (
      <div className="h-screen w-screen bg-[#020617] flex items-center justify-center">
        <div className="animate-pulse text-indigo-500/50 text-[10px] font-bold uppercase tracking-[0.3em]">
          Redirecting to Authorization...
        </div>
      </div>
    );
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
