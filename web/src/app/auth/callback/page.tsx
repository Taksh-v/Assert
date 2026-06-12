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
        console.log("[AuthCallback] Session verified! Finalizing local state...");

        const userMeta = session.user.user_metadata ?? {};
        const userInfo = {
          id: session.user.id,
          email: session.user.email ?? "",
          full_name: userMeta.full_name || userMeta.name || session.user.email,
        };

        // STEP A: Commit session IMMEDIATELY. 
        // This stops the redirect loop because AppShell will now see auth=true.
        commitSession(session.access_token, userInfo, null);

        // STEP B: Attempt backend synchronization in the background.
        // If this fails, we DON'T sign out; we just let the user into the app.
        // ensureDefaultWorkspace() called later in AppShell will handle the rest.
        try {
          console.log("[AuthCallback] Attempting backend identity sync...");
          const userRes = await apiFetch("/users/me", {
            headers: { Authorization: `Bearer ${session.access_token}` }
          });
          
          if (userRes.ok) {
            const userData = await userRes.json();
            const updatedUserInfo = {
              id: userData.id,
              email: userData.email,
              full_name: userData.full_name || userInfo.full_name,
            };
            
            // Refine the session with real backend data
            const wsRes = await apiFetch("/workspaces");
            let workspace = null;
            if (wsRes.ok) {
              const workspaces = await wsRes.json();
              if (workspaces.length > 0) workspace = workspaces[0];
            }
            commitSession(session.access_token, updatedUserInfo, workspace);
            console.log("[AuthCallback] Backend sync successful.");
          } else {
            console.warn("[AuthCallback] Backend sync returned non-200. Proceeding with provider-only identity.");
          }
        } catch (err) {
          console.warn("[AuthCallback] Background sync failed (backend might be offline). User is still authenticated via Supabase.");
        }

        // Update last account memory
        if (typeof window !== "undefined") {
          localStorage.setItem("assest_last_email", userInfo.email);
        }

        console.log("[AuthCallback] Redirecting to dashboard...");
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
