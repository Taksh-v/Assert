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

    // Track the latest auth state in a local variable so event handlers avoid stale closures.
    // A ref would survive re-renders but since this effect only runs once ([]) we use a closure var.
    let currentAuth: boolean | null = null;

    const resolveWorkspace = async () => {
      // Race workspace fetch against a 5s timeout so a slow backend never
      // permanently blocks the loading screen.
      const timeoutPromise = new Promise<null>(resolve => setTimeout(() => resolve(null), 5000));
      await Promise.race([ensureDefaultWorkspace(), timeoutPromise]);
      setWorkspaceReady(true); // Always unblock — workspace may just be slow
    };

    const checkAuth = async () => {
      const authStatus = await isAuthenticated();
      currentAuth = authStatus;
      setAuth(authStatus);
      if (authStatus) {
        await resolveWorkspace();
      }
    };

    checkAuth();

    const handleAuthChange = async () => {
      const authStatus = await isAuthenticated();
      console.log("[AppShell] Auth change detected, new state:", authStatus);

      // Debounce: if we were authenticated and now appear not to be,
      // wait briefly in case it is a mid-flight transition (e.g. token being committed).
      if (currentAuth && !authStatus) {
        await new Promise(r => setTimeout(r, 800));
        const finalStatus = await isAuthenticated();
        if (!finalStatus) {
          currentAuth = false;
          setAuth(false);
          setWorkspaceReady(false);
        }
        return;
      }

      currentAuth = authStatus;
      setAuth(authStatus);
      if (authStatus) {
        await resolveWorkspace();
      } else {
        setWorkspaceReady(false);
      }
    };

    window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    // Also listen for cross-tab / storage changes
    window.addEventListener("storage", handleAuthChange);

    return () => {
      window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
      window.removeEventListener("storage", handleAuthChange);
    };
  }, []);

  // Prevent flickering during hydration, and WAIT for workspace if authenticated.
  // The workspace wait is bounded by the 5s timeout above, so we never get stuck here permanently.
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

  // If not logged in, show the login portal UNLESS on a public unauthenticated route
  if (!auth) {
    if (pathname && pathname.startsWith("/auth/reset-password")) {
      return <>{children}</>;
    }
    return <AuthPortal />;
  }

  // Logged in and workspace ready — show full app shell
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[var(--bg-root)] text-[var(--text-primary)] animate-fade-in">
      <Sidebar />
      <main className="flex-1 overflow-hidden h-full relative flex flex-col">
        {children}
      </main>
    </div>
  );
}
