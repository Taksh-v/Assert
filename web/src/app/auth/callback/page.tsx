"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { commitSession, apiFetch, WorkspaceInfo } from "@/lib/auth";

export default function AuthCallback() {
  const router = useRouter();
  const processed = useRef(false);

  useEffect(() => {
    // Prevent double-execution in React Strict Mode
    if (processed.current) return;

    const handleCallback = async () => {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code");
      const error = params.get("error");
      const hash = window.location.hash;

      // 1. Handle explicit errors from the provider
      if (error) {
        console.error("Auth provider error:", error);
        router.push("/?error=" + encodeURIComponent(error));
        return;
      }

      // 2. If there's a code, exchange it for a session
      if (code) {
        processed.current = true;
        console.log("[AuthCallback] Code detected, exchanging...");
        const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);

        if (exchangeError) {
          console.error("Auth callback exchange error:", exchangeError.message);
          router.push("/?error=" + encodeURIComponent(exchangeError.message));
          return;
        }
      }
      // 3. Handle Hash Fragment (implicit flow fallback)
      else if (hash && hash.includes("access_token")) {
        console.log("[AuthCallback] Access token found in hash fragment.");
        processed.current = true;
      }

      // 4. Final verification: do we have a session now?
      const { data: { session } } = await supabase.auth.getSession();
      if (session) {
        console.log("[AuthCallback] Session verified! Pre-loading profile before redirect...");

        // Build user info from Supabase session metadata (available immediately, no backend call)
        const userMeta = session.user.user_metadata ?? {};
        const userInfo = {
          id: session.user.id,
          email: session.user.email ?? "",
          full_name: userMeta.full_name || userMeta.name || session.user.email,
        };

        // Fetch workspace BEFORE commitSession using the token directly in the header.
        // We cannot use ensureDefaultWorkspace() here because it calls apiFetch() which
        // reads the token from localStorage — but commitSession() hasn't run yet, so
        // localStorage is empty and every request would get a 401.
        let workspace: WorkspaceInfo | null = null;
        try {
          const wsRes = await apiFetch("/workspaces", {
            headers: { Authorization: `Bearer ${session.access_token}` }
          });
          if (wsRes.ok) {
            const workspaces = await wsRes.json() as WorkspaceInfo[];
            workspace = workspaces?.[0] ?? null;
          }
          // If no workspace exists yet (new OAuth user), the backend auto-provisions one
          // inside get_current_user() via the Supabase JWT path. The next page load or
          // apiFetch call will pick it up after commitSession() runs.
        } catch {
          console.warn("[AuthCallback] Could not load workspace, proceeding anyway.");
        }

        // Atomically write token + user + workspace to localStorage in one shot.
        // This means AppShell will find a fully-committed session on first render
        // and will NOT trigger the expensive /users/me hydration path.
        commitSession(session.access_token, userInfo, workspace);
        console.log("[AuthCallback] Session committed. Redirecting home...");

        // Replace history so the user cannot "back" into /auth/callback
        window.location.replace("/");
      } else {
        // No session after exchange — send back to sign-in
        console.warn("[AuthCallback] No session found after exchange.");
        router.push("/");
      }
    };

    handleCallback();
  }, [router]);

  return (
    <div className="h-screen w-screen bg-[#020617] flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="h-5 w-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        <div className="animate-pulse text-indigo-500/50 text-[10px] font-bold uppercase tracking-[0.3em]">
          Finalizing Identity...
        </div>
      </div>
    </div>
  );
}
