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

        const userMeta = session.user.user_metadata ?? {};
        let userInfo = {
          id: session.user.id,
          email: session.user.email ?? "",
          full_name: userMeta.full_name || userMeta.name || session.user.email,
        };

        let workspace: WorkspaceInfo | null = null;
        try {
          // 1. Verify user profile on backend
          console.log("[AuthCallback] Verifying profile on backend...");
          const userRes = await apiFetch("/users/me", {
            headers: { Authorization: `Bearer ${session.access_token}` }
          });
          
          if (!userRes.ok) {
            const errData = await userRes.json().catch(() => ({}));
            const errMsg = errData.detail || "Identity synchronization failed. Check backend logs.";
            console.error("[AuthCallback] Profile verification failed:", errMsg);
            throw new Error(errMsg);
          }
          
          const userData = await userRes.json();
          userInfo = {
            id: userData.id,
            email: userData.email,
            full_name: userData.full_name || userInfo.full_name,
          };
 
          // 2. Fetch or create workspace
          console.log("[AuthCallback] Fetching workspaces...");
          const wsRes = await apiFetch("/workspaces", {
            headers: { Authorization: `Bearer ${session.access_token}` }
          });
          
          if (wsRes.ok) {
            const workspaces = await wsRes.json() as WorkspaceInfo[];
            if (workspaces && workspaces.length > 0) {
              workspace = workspaces[0];
              console.log("[AuthCallback] Found existing workspace:", workspace.name);
            } else {
              console.log("[AuthCallback] No workspaces found, creating 'Main Workspace'...");
              const wsName = "Main Workspace";
              const wsSlug = `main-${userInfo.id.slice(0, 5)}-${Math.random().toString(36).slice(2, 5)}`;
              const createWsRes = await apiFetch("/workspaces", {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  Authorization: `Bearer ${session.access_token}`,
                },
                body: JSON.stringify({ name: wsName, slug: wsSlug }),
              });
              if (createWsRes.ok) {
                workspace = await createWsRes.json() as WorkspaceInfo;
                console.log("[AuthCallback] Main workspace created successfully.");
              } else {
                console.warn("[AuthCallback] Failed to create Main Workspace.");
              }
            }
          }
        } catch (err) {
          const errorMessage = err instanceof Error ? err.message : "Failed to synchronize session.";
          console.error("[AuthCallback] OAuth Finalization Error:", errorMessage);
          await supabase.auth.signOut().catch(() => {});
          localStorage.removeItem("assest_identity_v1");
          localStorage.removeItem("assest_auth_user");
          localStorage.removeItem("assest_auth_workspace");
          router.push("/?error=" + encodeURIComponent(errorMessage));
          return;
        }

        // Atomically write token + user + workspace to localStorage in one shot.
        commitSession(session.access_token, userInfo, workspace);
        
        // Update the "Last Account" memory to the new OAuth user
        if (typeof window !== "undefined") {
          localStorage.setItem("assest_last_email", userInfo.email);
          if (userInfo.full_name) {
            localStorage.setItem("assest_last_name", userInfo.full_name);
          }
        }
        
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
