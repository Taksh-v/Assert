"use client";

import React, { useState } from "react";
import { Brain, Mail, Lock, User, Loader2, ArrowRight, AlertCircle, CheckCircle2, Code2, Globe, Zap } from "lucide-react";
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
            // Auto-create a default workspace if none exists (common for new users)
            const createWsRes = await apiFetch("/api/workspaces", {
              method: "POST",
              headers: { 
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json"
              },
              body: JSON.stringify({ name: "My Workspace" })
            });
            if (createWsRes.ok) {
              const newWs = await createWsRes.json();
              setActiveWorkspace(newWs);
            }
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

  const handleSocialLogin = (provider: string) => {
    // These will be connected once the backend OAuth providers are configured
    setError(`Login with ${provider} will be available once OAuth is configured in your dashboard.`);
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-[#020617] overflow-hidden">
      {/* Decorative gradient blobs */}
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
            <div className="absolute inset-0 bg-indigo-500/20 rounded-2xl blur-xl group-hover:bg-indigo-500/30 transition-all duration-500" />
            <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-[#0f172a] border border-white/10 shadow-inner">
              <Brain className="h-8 w-8 text-indigo-400" />
            </div>
          </div>
          <div className="space-y-1">
            <h1 className="text-4xl font-extrabold tracking-tight text-white bg-clip-text text-transparent bg-gradient-to-br from-white to-gray-400">
              Assest
            </h1>
            <p className="text-sm font-medium text-gray-500 uppercase tracking-widest">
              Company Brain
            </p>
          </div>
        </div>

        {/* Main Card */}
        <div className="rounded-3xl border border-white/[0.05] bg-white/[0.02] backdrop-blur-xl p-8 shadow-2xl relative overflow-hidden group">
          {/* Subtle inner border for glass effect */}
          <div className="absolute inset-0 border border-white/5 rounded-3xl pointer-events-none" />
          
          {/* Tab Switcher */}
          <div className="flex rounded-2xl bg-black/20 p-1.5 border border-white/5 mb-8">
            <button
              onClick={() => { setIsLogin(true); setError(null); setSuccess(null); }}
              className={`flex-1 py-2.5 text-sm font-semibold rounded-xl transition-all duration-500 ${
                isLogin 
                  ? "bg-indigo-600 text-white shadow-[0_0_20px_rgba(99,102,241,0.3)]" 
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setIsLogin(false); setError(null); setSuccess(null); }}
              className={`flex-1 py-2.5 text-sm font-semibold rounded-xl transition-all duration-500 ${
                !isLogin 
                  ? "bg-indigo-600 text-white shadow-[0_0_20px_rgba(99,102,241,0.3)]" 
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Join
            </button>
          </div>

          {/* Social Logins */}
          <div className="space-y-3 mb-8">
            <div className="grid grid-cols-3 gap-3">
              <button 
                onClick={() => handleSocialLogin('Google')}
                className="flex items-center justify-center py-3 px-4 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.08] hover:border-white/10 transition-all duration-300 group/btn"
              >
                <Globe className="h-5 w-5 text-gray-400 group-hover/btn:text-white transition-colors" />
              </button>
              <button 
                onClick={() => handleSocialLogin('GitHub')}
                className="flex items-center justify-center py-3 px-4 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.08] hover:border-white/10 transition-all duration-300 group/btn"
              >
                <Code2 className="h-5 w-5 text-gray-400 group-hover/btn:text-white transition-colors" />
              </button>
              <button 
                onClick={() => handleSocialLogin('Facebook')}
                className="flex items-center justify-center py-3 px-4 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.08] hover:border-white/10 transition-all duration-300 group/btn"
              >
                <Zap className="h-5 w-5 text-gray-400 group-hover/btn:text-white transition-colors" />
              </button>
            </div>
            <div className="relative flex items-center justify-center py-2">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-white/5"></div>
              </div>
              <span className="relative px-4 text-[10px] font-bold uppercase tracking-[0.2em] text-white/20 bg-transparent backdrop-blur-none">
                or use email
              </span>
            </div>
          </div>

          {/* Form */}
          <form className="space-y-4" onSubmit={handleSubmit}>
            {error && (
              <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs animate-shake">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}
            {success && (
              <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs animate-fade-in">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <span>{success}</span>
              </div>
            )}

            {!isLogin && (
              <div className="space-y-1.5 group/field">
                <label className="text-[11px] font-bold text-white/40 uppercase tracking-wider ml-1 group-focus-within/field:text-indigo-400 transition-colors">
                  Identity
                </label>
                <div className="relative">
                  <User className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-white/20 group-focus-within/field:text-indigo-400/60 transition-colors" />
                  <input
                    type="text"
                    required
                    placeholder="Enter your name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full bg-white/[0.03] border border-white/5 focus:border-indigo-500/40 focus:bg-white/[0.06] rounded-xl pl-11 pr-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none transition-all duration-300"
                  />
                </div>
              </div>
            )}

            <div className="space-y-1.5 group/field">
              <label className="text-[11px] font-bold text-white/40 uppercase tracking-wider ml-1 group-focus-within/field:text-indigo-400 transition-colors">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-white/20 group-focus-within/field:text-indigo-400/60 transition-colors" />
                <input
                  type="email"
                  required
                  placeholder="name@work.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-white/[0.03] border border-white/5 focus:border-indigo-500/40 focus:bg-white/[0.06] rounded-xl pl-11 pr-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none transition-all duration-300"
                />
              </div>
            </div>

            <div className="space-y-1.5 group/field">
              <label className="text-[11px] font-bold text-white/40 uppercase tracking-wider ml-1 group-focus-within/field:text-indigo-400 transition-colors">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-white/20 group-focus-within/field:text-indigo-400/60 transition-colors" />
                <input
                  type="password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-white/[0.03] border border-white/5 focus:border-indigo-500/40 focus:bg-white/[0.06] rounded-xl pl-11 pr-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none transition-all duration-300"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full relative flex items-center justify-center gap-2 py-4 px-4 rounded-xl text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500 overflow-hidden disabled:opacity-50 transition-all duration-500 shadow-[0_10px_30px_rgba(99,102,241,0.2)] active:scale-[0.98] group/submit mt-4"
            >
              {loading ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span className="animate-pulse">Accessing Brain...</span>
                </>
              ) : (
                <>
                  <span className="relative z-10">{isLogin ? "Enter Brain" : "Create Brain"}</span>
                  <ArrowRight className="h-4 w-4 relative z-10 group-hover/submit:translate-x-1 transition-transform" />
                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000" />
                </>
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <div className="mt-12 flex flex-col items-center gap-4">
          <p className="text-[10px] font-bold text-white/20 uppercase tracking-[0.3em]">
            Powered by Assest Advanced Retrieval
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
      `}</style>
    </div>
  );
}
