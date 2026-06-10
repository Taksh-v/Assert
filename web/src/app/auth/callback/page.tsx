"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

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

      // 1. Handle explicit errors from the provider
      if (error) {
        console.error("Auth provider error:", error);
        router.push("/?error=" + encodeURIComponent(error));
        return;
      }

      // 2. If there's a code, exchange it for a session
      if (code) {
        processed.current = true;
        const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
        
        if (exchangeError) {
          console.error("Auth callback exchange error:", exchangeError.message);
          
          // Check if we actually have a session anyway (maybe it was exchanged by the other run)
          const { data: { session } } = await supabase.auth.getSession();
          if (session) {
            router.push("/");
            return;
          }
          
          router.push("/?error=" + encodeURIComponent(exchangeError.message));
          return;
        }
      }

      // 3. Final verification: do we have a session now?
      const { data: { session } } = await supabase.auth.getSession();
      if (session) {
        router.push("/");
      } else {
        // No code and no session? Redirect home to re-authenticate
        console.warn("No code or session found in callback.");
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
