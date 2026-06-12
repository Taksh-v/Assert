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
          const userRes = await apiFetch("/users/me", {
            headers: { Authorization: `Bearer ${session.access_token}` }
          });
          
          if (!userRes.ok) {
            const errData = await userRes.json().catch(() => ({}));
            const errMsg = errData.detail || "Identity sync failed.";
            console.error("[AuthCallback] Profile verification failed:", errMsg);
            await supabase.auth.signOut().catch(() => {});
            localStorage.removeItem("assest_identity_v1");
            localStorage.removeItem("assest_auth_user");
            localStorage.removeItem("assest_auth_workspace");
            router.push("/?error=" + encodeURIComponent(errMsg));
            return;
          }
          
          const userData = await userRes.json();
          userInfo = {
            id: userData.id,
            email: userData.email,
            full_name: userData.full_name || userInfo.full_name,
          };
 
          // 2. Fetch or create workspace
          const wsRes = await apiFetch("/workspaces", {
            headers: { Authorization: `Bearer ${session.access_token}` }
          });
          if (wsRes.ok) {
            const workspaces = await wsRes.json() as WorkspaceInfo[];
            if (workspaces && workspaces.length > 0) {
              workspace = workspaces[0];
            } else {
              // No workspace exists yet — create one now before committing session.
              // This can happen if auto-provisioning failed silently or the user
              // is an identity-linked account whose old workspace is under a different user id.
              console.log("[AuthCallback] No workspaces found, creating default workspace...");
              const wsName = userInfo.full_name
                ? `${userInfo.full_name.split(" ")[0]}'s Workspace`
                : "My Workspace";
              const wsSlug = `ws-${userInfo.id.slice(0, 8)}-${Math.random().toString(36).slice(2, 6)}`;
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
                console.log("[AuthCallback] Default workspace created:", workspace?.name);
              } else {
                console.warn("[AuthCallback] Failed to create default workspace — proceeding without one.");
              }
            }
          }
        } catch (err) {
          console.warn("[AuthCallback] Profile validation failed, returning to sign in.", err);
          await supabase.auth.signOut().catch(() => {});
          localStorage.removeItem("assest_identity_v1");
          localStorage.removeItem("assest_auth_user");
          localStorage.removeItem("assest_auth_workspace");
          router.push("/?error=" + encodeURIComponent("Failed to synchronize session. Please try again."));
          return;
        }

        // Atomically write token + user + workspace to localStorage in one shot.
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
