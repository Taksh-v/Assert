"use client";

import React, { useState } from "react";
import { Brain, Mail, Lock, User, Loader2, ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";
import { apiFetch, setAuthToken, setCurrentUser, setActiveWorkspace, WorkspaceInfo } from "@/lib/auth";

export default function AuthPortal() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password.trim() || (!isLogin && !fullName.trim())) {
      setError("Please fill in all fields.");
      return;
    }

    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      if (isLogin) {
        const params = new URLSearchParams();
        params.append("username", email);
        params.append("password", password);

        const response = await apiFetch("/api/login", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: params,
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || "Invalid email or password.");
        }

        const data = await response.json();
        const token = data.access_token;
        setAuthToken(token);

        const userRes = await apiFetch("/api/users/me", {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!userRes.ok) {
          throw new Error("Failed to fetch user profile details.");
        }

        const userData = await userRes.json();
        setCurrentUser({
          id: userData.id,
          email: userData.email,
          full_name: userData.full_name,
        });

        const workspaceRes = await apiFetch("/api/workspaces", {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (workspaceRes.ok) {
          const workspaces = await workspaceRes.json() as WorkspaceInfo[];
          if (workspaces && workspaces.length > 0) {
            setActiveWorkspace(workspaces[0]);
          } else {
            throw new Error("No workspace is available for this account.");
          }
        }

        setSuccess("Success! Logging in...");
      } else {
        const response = await apiFetch("/api/register", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email,
            password,
            full_name: fullName,
          }),
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || "Registration failed. Email might be in use.");
        }

        setSuccess("Account created successfully! Switching to Sign In...");
        setTimeout(() => {
          setIsLogin(true);
          setSuccess(null);
          setPassword("");
        }, 1500);
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-[--bg-root] px-4 py-12 overflow-hidden">
      {/* Decorative gradient blobs */}
      <div className="absolute top-[-15%] left-[-10%] h-[500px] w-[500px] rounded-full bg-indigo-600/[0.06] blur-[180px] pointer-events-none" />
      <div className="absolute bottom-[-15%] right-[-10%] h-[500px] w-[500px] rounded-full bg-violet-600/[0.04] blur-[180px] pointer-events-none" />
      
      {/* Dot grid */}
      <div 
        className="absolute inset-0 opacity-[0.015] pointer-events-none"
        style={{
          backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
          backgroundSize: "24px 24px"
        }}
      />

      <div className="w-full max-w-[420px] space-y-8 z-10">
        {/* Logo & Header */}
        <div className="flex flex-col items-center text-center space-y-4">
          <div className="relative group">
            <div className="absolute inset-0 bg-indigo-500/15 rounded-2xl blur-xl group-hover:bg-indigo-500/20 transition-all duration-500" />
            <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl bg-[--accent-muted] border border-[--border-subtle]">
              <Brain className="h-6 w-6 text-[--accent]" />
            </div>
          </div>
          <div className="space-y-1">
            <h1 className="text-3xl font-bold tracking-tight text-[--text-primary]">
              Assest
            </h1>
            <p className="text-sm text-[--text-muted]">
              Company Brain
            </p>
          </div>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-[--border-subtle] bg-[--bg-surface] p-8 shadow-[--shadow-elevated]">
          {/* Tab Switcher */}
            <div className="flex rounded-xl bg-[--bg-root] p-1 border border-[--border-subtle] mb-8">
            <button
              onClick={() => { setIsLogin(true); setError(null); setSuccess(null); }}
              className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-300 ${
                isLogin 
                  ? "bg-[--accent] text-white shadow-lg" 
                  : "text-[--text-muted] hover:text-[--text-secondary]"
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setIsLogin(false); setError(null); setSuccess(null); }}
              className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-300 ${
                !isLogin 
                  ? "bg-[--accent] text-white shadow-lg" 
                  : "text-[--text-muted] hover:text-[--text-secondary]"
              }`}
            >
              Create Account
            </button>
          </div>

          {/* Form */}
          <form className="space-y-5" onSubmit={handleSubmit}>
            {error && (
              <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-[--danger-muted] border border-red-500/20 text-red-400 text-sm animate-fade-in">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}
            {success && (
              <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-[--success-muted] border border-emerald-500/20 text-emerald-400 text-sm animate-fade-in">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <span>{success}</span>
              </div>
            )}

            {!isLogin && (
              <div className="space-y-2">
                <label className="text-[12px] font-medium text-[--text-muted] px-1">
                  Full Name
                </label>
                <div className="relative flex items-center">
                  <User className="absolute left-4 h-4 w-4 text-[--text-muted]" />
                  <input
                    type="text"
                    required
                    placeholder="Jane Doe"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full bg-[--bg-root] border border-[--border-subtle] hover:border-[var(--accent)]/20 focus:border-[--border-focus] rounded-xl pl-11 pr-4 py-3 text-sm text-[--text-primary] placeholder-[--text-muted] focus:outline-none transition-all duration-300"
                  />
                </div>
              </div>
            )}

            <div className="space-y-2">
              <label className="text-[12px] font-medium text-[--text-muted] px-1">
                Email Address
              </label>
              <div className="relative flex items-center">
                <Mail className="absolute left-4 h-4 w-4 text-[--text-muted]" />
                <input
                  type="email"
                  required
                  placeholder="name@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-[--bg-root] border border-[--border-subtle] hover:border-[var(--accent)]/20 focus:border-[--border-focus] rounded-xl pl-11 pr-4 py-3 text-sm text-[--text-primary] placeholder-[--text-muted] focus:outline-none transition-all duration-300"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-[12px] font-medium text-[--text-muted] px-1">
                Password
              </label>
              <div className="relative flex items-center">
                <Lock className="absolute left-4 h-4 w-4 text-[--text-muted]" />
                <input
                  type="password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-[--bg-root] border border-[--border-subtle] hover:border-[var(--accent)]/20 focus:border-[--border-focus] rounded-xl pl-11 pr-4 py-3 text-sm text-[--text-primary] placeholder-[--text-muted] focus:outline-none transition-all duration-300"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3.5 px-4 rounded-xl text-sm font-semibold text-white bg-[--accent] hover:bg-[--accent-hover] disabled:opacity-50 transition-all duration-300 shadow-lg shadow-indigo-500/10 active:scale-[0.98]"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  {isLogin ? "Sign In" : "Create Account"}
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <p className="text-center text-[11px] text-[--text-muted]">
          Enterprise Knowledge Platform
        </p>
      </div>
    </div>
  );
}
