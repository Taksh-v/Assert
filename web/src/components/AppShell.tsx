"use client";

import React, { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";
import AuthPortal from "./AuthPortal";
import { isAuthenticated, ensureDefaultWorkspace, AUTH_CHANGE_EVENT } from "@/lib/auth";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [auth, setAuth] = useState<boolean | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState<boolean>(false);
  const [mounted, setMounted] = useState<boolean>(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
    
    const checkAuth = async () => {
      const authStatus = await isAuthenticated();
      setAuth(authStatus);
      if (authStatus) {
        const ws = await ensureDefaultWorkspace();
        if (ws) {
          setWorkspaceReady(true);
        }
      }
    };

    checkAuth();

    const handleAuthChange = async () => {
      const authStatus = await isAuthenticated();
      console.log("[AppShell] Auth change detected, new state:", authStatus);
      setAuth(authStatus);
      if (authStatus) {
        const ws = await ensureDefaultWorkspace();
        setWorkspaceReady(!!ws);
      } else {
        setWorkspaceReady(false);
      }
    };

    window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    // Also listen for cross-tab or storage changes
    window.addEventListener('storage', handleAuthChange);

    return () => {
      window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
      window.removeEventListener('storage', handleAuthChange);
    };
  }, []);

  // Prevent flickering during hydration, and WAIT for workspace if authenticated
  if (!mounted || auth === null || (auth && !workspaceReady)) {
    return (
      <div className="h-screen w-screen bg-[#020617] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="h-5 w-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          <div className="animate-pulse text-indigo-500/50 text-[10px] font-bold uppercase tracking-[0.3em]">
            {!mounted || auth === null ? "Assest Brain Syncing..." : "Provisioning Workspace..."}
          </div>
        </div>
      </div>
    );
  }

  // If not logged in, show the login portal UNLESS we are on a public unauthenticated route
  if (!auth) {
    if (pathname && pathname.startsWith("/auth/reset-password")) {
      return <>{children}</>;
    }
    return <AuthPortal />;
  }

  // If logged in and workspace is ready, show the full app shell
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[var(--bg-root)] text-[var(--text-primary)] animate-fade-in">
      <Sidebar />
      <main className="flex-1 overflow-hidden h-full relative flex flex-col">
        {children}
      </main>
    </div>
  );
}
