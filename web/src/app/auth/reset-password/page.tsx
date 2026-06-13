"use client";

import React, { useState } from "react";
import { Brain, Lock, Loader2, ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";
import { supabase } from "@/lib/supabase";

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Initialize recovery session on mount
  React.useEffect(() => {
    const checkSession = async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session && !window.location.hash.includes("type=recovery")) {
        setError("Invalid or expired reset link. Please request a new one.");
      }
    };
    checkSession();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;
      setSuccess(true);
      setTimeout(() => {
        window.location.replace("/auth");
      }, 3000);
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Failed to update password.";
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-[#020617] overflow-hidden">
      <div className="absolute top-[-10%] left-[-5%] h-[600px] w-[600px] rounded-full bg-indigo-600/[0.08] blur-[140px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-5%] h-[600px] w-[600px] rounded-full bg-violet-600/[0.06] blur-[140px] pointer-events-none" />
      
      <div className="w-full max-w-[440px] px-6 z-10">
        <div className="flex flex-col items-center text-center space-y-3 mb-8">
          <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-[#0f172a] border border-white/10 shadow-inner">
            <Brain className="h-8 w-8 text-indigo-400" />
          </div>
          <div className="space-y-1">
            <h1 className="text-3xl font-extrabold tracking-tight text-white">Reset Password</h1>
            <p className="text-sm font-medium text-gray-500 uppercase tracking-widest">Secure your account</p>
          </div>
        </div>

        <div className="rounded-3xl border border-white/[0.05] bg-white/[0.02] backdrop-blur-xl p-8 shadow-2xl relative">
          {success ? (
            <div className="text-center space-y-4 py-4 animate-fade-in">
              <div className="flex justify-center">
                <CheckCircle2 className="h-12 w-12 text-emerald-500" />
              </div>
              <h2 className="text-xl font-bold text-white">Password Updated!</h2>
              <p className="text-sm text-white/60">Your password has been changed successfully. Redirecting you to sign in...</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              )}
              
              <div className="space-y-1.5">
                <label className="text-[11px] font-bold uppercase tracking-wider text-white/40 ml-1">New Password</label>
                <div className="relative">
                  <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-white/20" />
                  <input
                    type="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full bg-white/[0.03] rounded-xl pl-11 pr-4 py-3 text-sm text-white border border-white/5 focus:border-indigo-500/40 focus:outline-none"
                    required
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] font-bold uppercase tracking-wider text-white/40 ml-1">Confirm Password</label>
                <div className="relative">
                  <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-white/20" />
                  <input
                    type="password"
                    placeholder="••••••••"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="w-full bg-white/[0.03] rounded-xl pl-11 pr-4 py-3 text-sm text-white border border-white/5 focus:border-indigo-500/40 focus:outline-none"
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-4 rounded-xl text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500 transition-all flex items-center justify-center gap-2 mt-4 shadow-[0_10px_30px_rgba(99,102,241,0.2)]"
              >
                {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <>Update Password <ArrowRight className="h-4 w-4" /></>}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
