"use client";

import React, { useState } from "react";
import { Sparkles, Mail, Lock, User, Loader2, ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";
import { setAuthToken, setCurrentUser, setActiveWorkspace, WorkspaceInfo } from "@/lib/auth";

export default function AuthPortal() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
        // 1. Call Login API (form-encoded as required by FastAPI OAuth2)
        const params = new URLSearchParams();
        params.append("username", email);
        params.append("password", password);

        const response = await fetch(`${API_URL}/api/login`, {
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

        // 2. Fetch User Profile Info & Workspaces
        const userRes = await fetch(`${API_URL}/api/users/me`, {
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

        // Fetch workspaces
        const workspaceRes = await fetch(`${API_URL}/api/workspaces`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (workspaceRes.ok) {
          const workspaces = await workspaceRes.json() as WorkspaceInfo[];
          if (workspaces && workspaces.length > 0) {
            setActiveWorkspace(workspaces[0]);
          } else {
            // Fallback default workspace if somehow empty
            setActiveWorkspace({
              id: "default-workspace",
              name: `${userData.full_name || "User"}'s Workspace`,
              slug: "workspace-default",
              role: "owner",
            });
          }
        }

        setSuccess("Success! Logging in...");
      } else {
        // Call Registration API
        const response = await fetch(`${API_URL}/api/register`, {
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
    <div className="relative flex min-h-screen items-center justify-center bg-[#020617] px-4 py-12 sm:px-6 lg:px-8 overflow-hidden font-sans">
      {/* Decorative Blur Backgrounds */}
      <div className="absolute top-[-10%] left-[-10%] h-[500px] w-[500px] rounded-full bg-blue-600/10 blur-[150px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] h-[500px] w-[500px] rounded-full bg-indigo-600/10 blur-[150px] pointer-events-none" />
      
      {/* Subtle Grid Backdrop */}
      <div 
        className="absolute inset-0 opacity-[0.015] pointer-events-none"
        style={{
          backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
          backgroundSize: "24px 24px"
        }}
      />

      <div className="w-full max-w-md space-y-8 z-10">
        {/* Logo and Header */}
        <div className="flex flex-col items-center text-center space-y-4">
          <div className="relative group">
            <div className="absolute inset-0 bg-blue-500/20 rounded-2xl blur-xl group-hover:bg-blue-500/30 transition-all duration-500" />
            <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03] backdrop-blur-xl">
              <Sparkles className="h-6 w-6 text-blue-400 animate-pulse" />
            </div>
          </div>
          <div className="space-y-1">
            <h1 className="text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
              Assest <span className="text-zinc-500 font-normal">Brain</span>
            </h1>
            <p className="text-sm font-medium text-zinc-400">
              AI-first Knowledge Engine for Enterprise Silos
            </p>
          </div>
        </div>

        {/* Card */}
        <div className="relative overflow-hidden rounded-[2rem] border border-white/[0.07] bg-white/[0.02] p-8 shadow-2xl backdrop-blur-2xl transition-all duration-500">
          {/* Card Border Glow */}
          <div className="absolute inset-0 bg-gradient-to-r from-blue-500/10 to-indigo-500/10 opacity-0 transition-opacity duration-500 hover:opacity-100 pointer-events-none" />

          {/* Tab Selection */}
          <div className="flex rounded-xl bg-white/[0.03] p-1 border border-white/5 mb-8">
            <button
              onClick={() => { setIsLogin(true); setError(null); setSuccess(null); }}
              className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all duration-300 ${
                isLogin 
                  ? "bg-white text-black shadow-lg" 
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setIsLogin(false); setError(null); setSuccess(null); }}
              className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all duration-300 ${
                !isLogin 
                  ? "bg-white text-black shadow-lg" 
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Create Account
            </button>
          </div>

          {/* Form */}
          <form className="space-y-6" onSubmit={handleSubmit}>
            {/* Status alerts */}
            {error && (
              <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-medium animate-in fade-in duration-300">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}
            {success && (
              <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-green-500/10 border border-green-500/20 text-green-400 text-xs font-medium animate-in fade-in duration-300">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <span>{success}</span>
              </div>
            )}

            {!isLogin && (
              <div className="space-y-2">
                <label className="text-[10px] font-black uppercase tracking-wider text-zinc-500 px-1">
                  Full Name
                </label>
                <div className="relative flex items-center">
                  <User className="absolute left-4 h-4 w-4 text-zinc-500" />
                  <input
                    type="text"
                    required
                    placeholder="Jane Doe"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full bg-white/[0.03] border border-white/5 hover:border-white/10 focus:border-blue-500/50 focus:bg-white/[0.05] rounded-xl pl-11 pr-4 py-3 text-sm text-white placeholder-zinc-500 focus:outline-none transition-all duration-300"
                  />
                </div>
              </div>
            )}

            <div className="space-y-2">
              <label className="text-[10px] font-black uppercase tracking-wider text-zinc-500 px-1">
                Email Address
              </label>
              <div className="relative flex items-center">
                <Mail className="absolute left-4 h-4 w-4 text-zinc-500" />
                <input
                  type="email"
                  required
                  placeholder="name@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-white/[0.03] border border-white/5 hover:border-white/10 focus:border-blue-500/50 focus:bg-white/[0.05] rounded-xl pl-11 pr-4 py-3 text-sm text-white placeholder-zinc-500 focus:outline-none transition-all duration-300"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-[10px] font-black uppercase tracking-wider text-zinc-500 px-1">
                Password
              </label>
              <div className="relative flex items-center">
                <Lock className="absolute left-4 h-4 w-4 text-zinc-500" />
                <input
                  type="password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-white/[0.03] border border-white/5 hover:border-white/10 focus:border-blue-500/50 focus:bg-white/[0.05] rounded-xl pl-11 pr-4 py-3 text-sm text-white placeholder-zinc-500 focus:outline-none transition-all duration-300"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3.5 px-4 border border-transparent rounded-xl text-xs font-black uppercase tracking-widest text-black bg-white hover:bg-blue-500 hover:text-white disabled:opacity-50 disabled:hover:bg-white disabled:hover:text-black transition-all duration-350 shadow-lg shadow-white/5 active:scale-98"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  {isLogin ? "Sign In" : "Register"}
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <p className="text-center text-[10px] font-medium text-zinc-600 uppercase tracking-widest">
          Hardware-Level Encryption • Zero-Knowledge Vector Indexing
        </p>
      </div>
    </div>
  );
}
