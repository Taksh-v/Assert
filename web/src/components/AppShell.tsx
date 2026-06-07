"use client";

import React, { useState, useEffect } from "react";
import Sidebar from "./Sidebar";
import AuthPortal from "./AuthPortal";
import { isAuthenticated, AUTH_CHANGE_EVENT } from "@/lib/auth";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<boolean>(false);
  const [mounted, setMounted] = useState<boolean>(false);

  useEffect(() => {
    setMounted(true);
    setAuth(isAuthenticated());

    const handleAuthChange = () => {
      setAuth(isAuthenticated());
    };

    window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    return () => {
      window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    };
  }, []);

  // Prevent flickering during hydration
  if (!mounted) {
    return (
      <div className="h-screen w-screen bg-[#020617] flex items-center justify-center">
        <div className="animate-pulse text-indigo-500/50 text-[10px] font-bold uppercase tracking-[0.3em]">
          Assest Brain Syncing...
        </div>
      </div>
    );
  }

  // If not logged in, show the login portal regardless of the current path
  if (!auth) {
    return <AuthPortal />;
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
