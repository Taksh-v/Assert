/* eslint-disable react-hooks/exhaustive-deps */
"use client";

import React, { useState, useEffect, useRef } from "react";
import { Brain, Lock, Loader2, ArrowRight, AlertCircle, CheckCircle2, Eye, EyeOff } from "lucide-react";
import { supabase } from "@/lib/supabase";

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);

  const passwordInputRef = useRef<HTMLInputElement>(null);

  // Initialize recovery session on mount
  useEffect(() => {
    const checkSession = async () => {
      try {
        // Supabase automatically handles the hash token and creates a session
        const { data: { session } } = await supabase.auth.getSession();
        
        // If no session and no recovery type in hash, it's an invalid entry
        if (!session && !window.location.hash.includes("type=recovery")) {
          setError("Invalid or expired reset link. Please request a new one from the sign-in page.");
        }
      } catch (err) {
        setError("Failed to verify reset link.");
      } finally {
        setIsInitializing(false);
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
      setError("Passwords do not match. Please check again.");
      return;
    }

    setLoading(true);
    try {
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;
      
      setSuccess(true);
      // Redirect to sign in after 3 seconds
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
      {/* Decorative gradient blobs (Matching AuthPortal) */}
      <div className="absolute top-[-10%] left-[-5%] h-[600px] w-[600px] rounded-full bg-indigo-600/[0.08] blur-[140px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-5%] h-[600px] w-[600px] rounded-full bg-violet-600/[0.06] blur-[140px] pointer-events-none" />
      
      {/* Subtle patterns */}
      <div 
        className="absolute inset-0 opacity-[0.02] pointer-events-none"
        style={{
          backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
          backgroundSize: "32px 32px"
        }}
      />

      <div className="w-full max-w-[440px] px-6 animate-fade-in z-10">
        {/* Logo & Header */}
        <div className="flex flex-col items-center text-center space-y-3 mb-8">
          <div className="relative group">
            <div className="absolute inset-0 bg-indigo-500/20 rounded-2xl blur-xl" />
            <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-[#0f172a] border border-white/10 shadow-inner">
              <Brain className="h-8 w-8 text-indigo-400" />
            </div>
          </div>
          <div className="space-y-1">
            <h1 className="text-4xl font-extrabold tracking-tight text-white bg-clip-text text-transparent bg-gradient-to-br from-white to-gray-400">
              Assest
            </h1>
            <p className="text-sm font-medium text-gray-500 uppercase tracking-widest">
              Security Portal
            </p>
          </div>
        </div>

        {/* Main Card */}
        <div className="rounded-3xl border border-white/[0.05] bg-white/[0.02] backdrop-blur-xl p-8 shadow-2xl relative overflow-hidden">
          <div className="absolute inset-0 border border-white/5 rounded-3xl pointer-events-none" />
          
          {isInitializing ? (
            <div className="flex flex-col items-center py-12 space-y-4">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
              <p className="text-xs text-white/40 uppercase tracking-widest font-bold">Verifying Session...</p>
            </div>
          ) : success ? (
            /* Success State */
            <div className="flex flex-col items-center text-center py-4 animate-fade-in">
              <div className="relative mb-6">
                <div className="absolute inset-0 bg-emerald-500/20 rounded-full blur-xl" />
                <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-[#0f172a] border border-emerald-500/20 shadow-inner">
                  <CheckCircle2 className="h-10 w-10 text-emerald-500" />
                </div>
              </div>
              <h2 className="text-2xl font-bold text-white mb-2">Password Updated</h2>
              <p className="text-sm text-white/60 mb-6 leading-relaxed">
                Your account is now secure. Redirecting you to sign in with your new password...
              </p>
              <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500 animate-progress" style={{ width: '100%' }} />
              </div>
            </div>
          ) : (
            /* Reset Form */
            <>
              <div className="mb-8 text-center">
                <h2 className="text-xl font-bold text-white mb-1">Create new password</h2>
                <p className="text-xs text-white/40">Choose a secure password for your account</p>
              </div>

              <form className="space-y-5" onSubmit={handleSubmit}>
                {error && (
                  <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs animate-shake">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    <span>{error}</span>
                  </div>
                )}

                <div className="space-y-1.5 group/field">
                  <label className="text-[11px] font-bold uppercase tracking-wider text-white/40 ml-1 group-focus-within/field:text-indigo-400 transition-colors">
                    New Password
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-white/20 group-focus-within/field:text-indigo-400/60 transition-colors" />
                    <input
                      type={showPassword ? "text" : "password"}
                      placeholder="••••••••"
                      value={password}
                      autoFocus
                      ref={passwordInputRef}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full bg-white/[0.03] rounded-xl pl-11 pr-12 py-3 text-sm text-white border border-white/5 focus:border-indigo-500/40 focus:bg-white/[0.06] focus:outline-none transition-all duration-300"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-white/20 hover:text-white/60 transition-colors p-1"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                <div className="space-y-1.5 group/field">
                  <label className="text-[11px] font-bold uppercase tracking-wider text-white/40 ml-1 group-focus-within/field:text-indigo-400 transition-colors">
                    Confirm Password
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-white/20 group-focus-within/field:text-indigo-400/60 transition-colors" />
                    <input
                      type={showPassword ? "text" : "password"}
                      placeholder="••••••••"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className={`w-full bg-white/[0.03] rounded-xl pl-11 pr-4 py-3 text-sm text-white border focus:bg-white/[0.06] focus:outline-none transition-all duration-300 ${
                        confirmPassword && password !== confirmPassword 
                          ? 'border-rose-500/40 focus:border-rose-500/60' 
                          : 'border-white/5 focus:border-indigo-500/40'
                      }`}
                      required
                    />
                  </div>
                  {confirmPassword && password !== confirmPassword && (
                    <p className="text-[10px] text-rose-400 ml-1 mt-1 font-medium animate-fade-in">
                      Passwords do not match yet
                    </p>
                  )}
                </div>

                <button
                  type="submit"
                  disabled={loading || !password || password !== confirmPassword}
                  className="w-full relative flex items-center justify-center gap-2 py-4 px-4 rounded-xl text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:grayscale transition-all duration-500 shadow-[0_10px_30px_rgba(99,102,241,0.2)] active:scale-[0.98] group/submit mt-6"
                >
                  {loading ? (
                    <>
                      <Loader2 className="h-5 w-5 animate-spin" />
                      <span className="animate-pulse">Updating Brain...</span>
                    </>
                  ) : (
                    <>
                      <span className="relative z-10">Change Password</span>
                      <ArrowRight className="h-4 w-4 relative z-10 group-hover/submit:translate-x-1 transition-transform" />
                      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000" />
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => window.location.replace("/auth")}
                  className="w-full text-center text-xs font-semibold text-white/30 hover:text-white/60 transition mt-4 bg-transparent border-none cursor-pointer"
                >
                  Return to Sign In
                </button>
              </form>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="mt-12 flex flex-col items-center gap-4">
          <p className="text-[10px] font-bold text-white/20 uppercase tracking-[0.3em]">
            Assest Security • End-to-End Encryption
          </p>
        </div>
      </div>

      <style jsx global>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          25% { transform: translateX(-4px); }
          75% { transform: translateX(4px); }
        }
        .animate-shake {
          animation: shake 0.4s cubic-bezier(.36,.07,.19,.97) both;
        }
        @keyframes progress {
          from { transform: translateX(-100%); }
          to { transform: translateX(0); }
        }
        .animate-progress {
          animation: progress 3s linear forwards;
        }
      `}</style>
    </div>
  );
}
