"use client";

import React, { useState, useEffect } from "react";
import Sidebar from "./Sidebar";
import AuthPortal from "./AuthPortal";
import { isAuthenticated, AUTH_CHANGE_EVENT } from "@/lib/auth";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<boolean>(false);
  const [mounted, setMounted] = useState<boolean>(false);

  useEffect(() => {
    queueMicrotask(() => {
      setMounted(true);
      setAuth(isAuthenticated());
    });

    const handleAuthChange = () => {
      setAuth(isAuthenticated());
    };

    window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    return () => {
      window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    };
  }, []);

  if (!mounted) {
    return <div className="h-screen w-screen bg-background" />;
  }

  if (!auth) {
    return <AuthPortal />;
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground animate-fade-in">
      <Sidebar />
      <main className="flex-1 overflow-y-auto overflow-x-hidden relative">
        {children}
      </main>
    </div>
  );
}
