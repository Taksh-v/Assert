"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function AuthCallback() {
  const router = useRouter();

  useEffect(() => {
    const handleCallback = async () => {
      const { error } = await supabase.auth.exchangeCodeForSession(window.location.search);
      if (error) {
        console.error("Auth callback error:", error.message);
        router.push("/?error=" + encodeURIComponent(error.message));
      } else {
        router.push("/");
      }
    };

    handleCallback();
  }, [router]);

  return (
    <div className="h-screen w-screen bg-[#020617] flex items-center justify-center">
      <div className="animate-pulse text-indigo-500/50 text-[10px] font-bold uppercase tracking-[0.3em]">
        Authenticating...
      </div>
    </div>
  );
}
