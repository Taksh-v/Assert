"use client";

import React, { useState } from "react";
import { Brain, Mail, Lock, User, Loader2, ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";
import { apiFetch, setAuthToken, setCurrentUser, setActiveWorkspace, WorkspaceInfo } from "@/lib/auth";

// Custom Brand Icons (SVGs) for maximum reliability
const GoogleIcon = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-1 .67-2.26 1.07-3.71 1.07-2.87 0-5.3-1.94-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
    <path d="M5.84 14.11c-.22-.67-.35-1.39-.35-2.11s.13-1.44.35-2.11V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l3.66-2.83z" fill="#FBBC05"/>
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.83c.86-2.59 3.29-4.53 6.16-4.53z" fill="#EA4335"/>
  </svg>
);

const GitHubIcon = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
    <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.082.814-.26.814-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.43.372.823 1.102.823 2.222 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
  </svg>
);

const FacebookIcon = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="#1877F2">
    <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
  </svg>
);

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
            const wsName = "My Workspace";
            const wsSlug = `workspace-${Math.random().toString(36).substring(2, 10)}`;
            const createWsRes = await apiFetch("/api/workspaces", {
              method: "POST",
              headers: { 
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json"
              },
              body: JSON.stringify({ name: wsName, slug: wsSlug })
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

          {/* Social Logins with Custom SVGs */}
          <div className="space-y-3 mb-8">
            <div className="grid grid-cols-3 gap-3">
              <button 
                onClick={() => handleSocialLogin('Google')}
                className="flex items-center justify-center py-3 px-4 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.08] hover:border-white/10 transition-all duration-300 group/btn"
              >
                <GoogleIcon />
              </button>
              <button 
                onClick={() => handleSocialLogin('GitHub')}
                className="flex items-center justify-center py-3 px-4 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.08] hover:border-white/10 transition-all duration-300 group/btn"
              >
                <GitHubIcon />
              </button>
              <button 
                onClick={() => handleSocialLogin('Facebook')}
                className="flex items-center justify-center py-3 px-4 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.08] hover:border-white/10 transition-all duration-300 group/btn"
              >
                <FacebookIcon />
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
