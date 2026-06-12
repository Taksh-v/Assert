"use client";

import React, { useState, useEffect } from "react";
import Sidebar from "./Sidebar";
import AuthPortal from "./AuthPortal";
import { isAuthenticated, ensureDefaultWorkspace, AUTH_CHANGE_EVENT } from "@/lib/auth";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<boolean | null>(null);
  const [mounted, setMounted] = useState<boolean>(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
    
    const checkAuth = async () => {
      const authStatus = await isAuthenticated();
      if (authStatus) {
        await ensureDefaultWorkspace();
      }
      setAuth(authStatus);
    };

    checkAuth();

    const handleAuthChange = async () => {
      const authStatus = await isAuthenticated();
      if (authStatus) {
        await ensureDefaultWorkspace();
      }
      console.log("[AppShell] Auth change detected, new state:", authStatus);
      setAuth(authStatus);
    };

    window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    // Also listen for cross-tab or storage changes
    window.addEventListener('storage', handleAuthChange);

    return () => {
      window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
      window.removeEventListener('storage', handleAuthChange);
    };
  }, []);

  // Prevent flickering during hydration
  if (!mounted || auth === null) {
    return (
      <div className="h-screen w-screen bg-[#020617] flex items-center justify-center">
        <div className="animate-pulse text-indigo-500/50 text-[10px] font-bold uppercase tracking-[0.3em]">
          Assest Brain Syncing...
        </div>
      </div>
    );
  }

  // If not logged in, show ONLY the login portal
  if (!auth) {
    return <AuthPortal />;
  }

  // If logged in, show the full app shell with sidebar and content
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[var(--bg-root)] text-[var(--text-primary)] animate-fade-in">
      <Sidebar />
      <main className="flex-1 overflow-hidden h-full relative flex flex-col">
        {children}
      </main>
    </div>
  );
}
