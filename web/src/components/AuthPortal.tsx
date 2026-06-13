/* eslint-disable react-hooks/set-state-in-effect */
"use client";

import React, { useState, useRef, useEffect } from "react";
import { Brain, Lock, Loader2, ArrowRight, AlertCircle, CheckCircle2, ChevronLeft } from "lucide-react";
import { apiFetch, commitSession, WorkspaceInfo } from "@/lib/auth";
import { supabase } from "@/lib/supabase";
import { getSiteUrl } from "@/lib/config";

export default function AuthPortal() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [success, setSuccess] = useState<string | null>(null);

  // Field-specific validation errors
  const [generalError, setGeneralError] = useState<string | null>(null);

  // Focus management input refs
  const emailInputRef = useRef<HTMLInputElement>(null);

  // Last-account memory state
  const [savedEmail, setSavedEmail] = useState("");
  const [savedName, setSavedName] = useState("");
  const [useSavedAccount, setUseSavedAccount] = useState(false);

  // Progressive Wizard steps
  const [step, setStep] = useState<"email" | "password" | "name_email" | "create_password" | "forgot_password">("email");

  const resetErrors = (loginMode = isLogin) => {
    setGeneralError(null);
    setStep(loginMode ? "email" : "name_email");
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      const lastEmail = localStorage.getItem("assest_last_email");
      const lastName = localStorage.getItem("assest_last_name");
      if (lastEmail) {
        setSavedEmail(lastEmail);
        setEmail(lastEmail);
        if (lastName) {
          setSavedName(lastName);
          setFullName(lastName);
        }
        setUseSavedAccount(true);
        setStep("password");
      }

      const params = new URLSearchParams(window.location.search);
      const urlError = params.get("error");
      if (urlError) {
        setGeneralError(decodeURIComponent(urlError));
        const cleanUrl = window.location.pathname;
        window.history.replaceState({}, document.title, cleanUrl);
      }
    }
  }, []);

  const [loading, setLoading] = useState(false);

  const handleForgotPassword = async () => {
    if (!email.trim()) {
      setGeneralError("Enter your email address to receive a reset link");
      return;
    }
    setLoading(true);
    setGeneralError(null);
    setSuccess(null);
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${getSiteUrl()}/auth/reset-password`,
      });
      if (error) throw error;
      setSuccess("Reset link sent! Please check your inbox.");
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Failed to send reset link.";
      setGeneralError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleNextStep = async () => {
    setGeneralError(null);
    
    if (!email.trim()) {
      setGeneralError("Enter an email address");
      return;
    }
    if (!/\S+@\S+\.\S+/.test(email)) {
      setGeneralError("Enter a valid email address");
      return;
    }

    if (isLogin) {
      setStep("password");
    } else {
      if (!fullName.trim()) {
        setGeneralError("Enter first and last name");
        return;
      }
      setStep("create_password");
    }
  };

  const handleFinalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);

    if (!password.trim()) {
      setGeneralError("Enter a password");
      return;
    }

    setSuccess(null);
    setLoading(true);

    try {
      let authResponse;
      if (isLogin) {
        authResponse = await supabase.auth.signInWithPassword({ email, password });
      } else {
        if (password.length < 6) {
          throw new Error("Use 6 characters or more for your password");
        }
        authResponse = await supabase.auth.signUp({
          email,
          password,
          options: { data: { full_name: fullName } }
        });
      }

      const { data, error } = authResponse;
      if (error) throw error;

      const token = data.session?.access_token;
      if (!token) {
        if (!isLogin) {
          setSuccess("Confirmation email sent! Please check your inbox.");
        } else {
          throw new Error("Failed to retrieve session token.");
        }
        return;
      }

      // Sync with backend
      const [userRes, workspaceRes] = await Promise.all([
        apiFetch("/api/users/me", { headers: { Authorization: `Bearer ${token}` } }),
        apiFetch("/api/workspaces", { headers: { Authorization: `Bearer ${token}` } })
      ]);

      if (!userRes.ok) throw new Error("Failed to load user profile from backend.");
      const userData = await userRes.json();
      const userInfo = { id: userData.id, email: userData.email, full_name: userData.full_name || fullName };

      if (typeof window !== "undefined") {
        localStorage.setItem("assest_last_email", userInfo.email);
        if (userInfo.full_name) localStorage.setItem("assest_last_name", userInfo.full_name);
      }

      let workspace: WorkspaceInfo | null = null;
      if (workspaceRes.ok) {
        const workspaces = await workspaceRes.json() as WorkspaceInfo[];
        if (workspaces && workspaces.length > 0) {
          workspace = workspaces[0];
        } else {
          const wsName = fullName ? `${fullName}'s Workspace` : "My Workspace";
          const wsSlug = `workspace-${Math.random().toString(36).substring(2, 10)}`;
          const createWsRes = await apiFetch("/api/workspaces", {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
            body: JSON.stringify({ name: wsName, slug: wsSlug })
          });
          if (createWsRes.ok) workspace = await createWsRes.json();
        }
      }

      commitSession(token, userInfo, workspace);
      setSuccess("Success! Entering Brain...");
      window.location.replace("/");
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Authentication failed.";
      setGeneralError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (step === "forgot_password") {
      handleForgotPassword();
    } else if (step === "email" || step === "name_email") {
      handleNextStep();
    } else {
      handleFinalSubmit(e);
    }
  };

  const handleBackToEmail = () => {
    setStep(isLogin ? "email" : "name_email");
    setPassword("");
    setGeneralError(null);
    setTimeout(() => emailInputRef.current?.focus(), 50);
  };

  const isFirstStep = step === "email" || step === "name_email" || step === "forgot_password";

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-[#020617] overflow-hidden">
      <div className="absolute top-[-10%] left-[-5%] h-[600px] w-[600px] rounded-full bg-indigo-600/[0.08] blur-[140px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-5%] h-[600px] w-[600px] rounded-full bg-violet-600/[0.06] blur-[140px] pointer-events-none" />
      
      <div className="w-full max-w-[440px] px-6 animate-fade-in z-10">
        <div className="flex flex-col items-center text-center space-y-3 mb-8">
          <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-[#0f172a] border border-white/10 shadow-inner">
            <Brain className="h-8 w-8 text-indigo-400" />
          </div>
          <div className="space-y-1">
            <h1 className="text-4xl font-extrabold tracking-tight text-white bg-clip-text text-transparent bg-gradient-to-br from-white to-gray-400">Assest</h1>
            <p className="text-sm font-medium text-gray-500 uppercase tracking-widest">Company Brain</p>
          </div>
        </div>

        <div className="rounded-3xl border border-white/[0.05] bg-white/[0.02] backdrop-blur-xl p-8 shadow-2xl relative overflow-hidden">
          {useSavedAccount && savedEmail && step === "password" ? (
            <div className="flex flex-col items-center animate-fade-in">
              <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-[#0f172a] border border-white/10 mb-6 text-indigo-400 text-2xl font-bold uppercase">
                {savedName ? savedName.split(" ").map(n => n[0]).slice(0, 2).join("") : savedEmail[0].toUpperCase()}
              </div>
              <div className="text-center mb-6">
                <h2 className="text-xl font-bold text-white mb-1">Welcome back, {savedName ? savedName.split(" ")[0] : "User"}</h2>
                <p className="text-xs text-white/40">{savedEmail}</p>
              </div>
              <form className="w-full space-y-4" onSubmit={handleFormSubmit}>
                {generalError && <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center gap-2"><AlertCircle className="h-4 w-4"/>{generalError}</div>}
                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold uppercase tracking-wider text-white/40 ml-1">Password</label>
                  <div className="relative">
                    <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-white/20" />
                    <input type="password" placeholder="••••••••" value={password} autoFocus onChange={e => setPassword(e.target.value)} className="w-full bg-white/[0.03] rounded-xl pl-11 pr-4 py-3 text-sm text-white border border-white/5 focus:border-indigo-500/40 focus:outline-none"/>
                  </div>
                </div>
                <button type="submit" disabled={loading} className="w-full py-4 rounded-xl text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500 transition-all flex items-center justify-center gap-2">
                  {loading ? <Loader2 className="h-5 w-5 animate-spin"/> : <>Enter Brain <ArrowRight className="h-4 w-4"/></>}
                </button>
                <button type="button" onClick={() => { setUseSavedAccount(false); setStep("email"); }} className="w-full text-center text-xs text-indigo-400 hover:text-indigo-300 mt-2 bg-transparent border-none cursor-pointer">Use another account</button>
              </form>
            </div>
          ) : (
            <>
              {isFirstStep && step !== "forgot_password" && (
                <div className="flex rounded-2xl bg-black/20 p-1.5 border border-white/5 mb-8">
                  <button type="button" onClick={() => { setIsLogin(true); resetErrors(true); }} className={`flex-1 py-2.5 text-sm font-semibold rounded-xl transition ${isLogin ? "bg-indigo-600 text-white" : "text-gray-400"}`}>Sign In</button>
                  <button type="button" onClick={() => { setIsLogin(false); resetErrors(false); }} className={`flex-1 py-2.5 text-sm font-semibold rounded-xl transition ${!isLogin ? "bg-indigo-600 text-white" : "text-gray-400"}`}>Join</button>
                </div>
              )}

              {!isFirstStep && (
                <div className="flex items-center gap-3 px-4 py-3 bg-white/[0.03] border border-white/5 rounded-2xl mb-6">
                  <button type="button" onClick={handleBackToEmail} className="p-1 hover:bg-white/5 rounded text-white/50 bg-transparent border-none cursor-pointer"><ChevronLeft className="h-4 w-4"/></button>
                  <div className="flex-1 truncate"><p className="text-[10px] font-bold text-white/40 uppercase">Account</p><p className="text-sm text-white truncate">{email}</p></div>
                </div>
              )}

              <form className="space-y-4" onSubmit={handleFormSubmit}>
                {generalError && <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center gap-2"><AlertCircle className="h-4 w-4"/>{generalError}</div>}
                {success && <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs flex items-center gap-2"><CheckCircle2 className="h-4 w-4"/>{success}</div>}

                {step === "forgot_password" ? (
                  <div className="space-y-4 animate-fade-in">
                    <div className="space-y-1.5">
                      <label className="text-[11px] font-bold uppercase tracking-wider text-white/40 ml-1">Email for recovery</label>
                      <input type="email" value={email} onChange={e => setEmail(e.target.value)} className="w-full bg-white/[0.03] rounded-xl px-4 py-3 text-sm text-white border border-white/5 focus:border-indigo-500/40 focus:outline-none"/>
                    </div>
                    <button type="submit" disabled={loading} className="w-full py-4 rounded-xl text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500">
                      {loading ? "Sending..." : "Send Reset Link"}
                    </button>
                    <button type="button" onClick={() => setStep("email")} className="w-full text-xs text-indigo-400 bg-transparent border-none cursor-pointer">Back to Sign In</button>
                  </div>
                ) : (
                  <>
                    {!isLogin && step === "name_email" && (
                      <div className="space-y-1.5"><label className="text-[11px] font-bold uppercase text-white/40 ml-1">Name</label>
                      <input type="text" placeholder="Your name" value={fullName} onChange={e => setFullName(e.target.value)} className="w-full bg-white/[0.03] rounded-xl px-4 py-3 text-sm text-white border border-white/5 focus:border-indigo-500/40 focus:outline-none"/></div>
                    )}
                    {isFirstStep && (
                      <div className="space-y-1.5"><label className="text-[11px] font-bold uppercase text-white/40 ml-1">Email</label>
                      <input type="email" placeholder="name@work.com" value={email} ref={emailInputRef} onChange={e => setEmail(e.target.value)} className="w-full bg-white/[0.03] rounded-xl px-4 py-3 text-sm text-white border border-white/5 focus:border-indigo-500/40 focus:outline-none"/></div>
                    )}
                    {!isFirstStep && (
                      <div className="space-y-1.5">
                        <div className="flex justify-between items-center"><label className="text-[11px] font-bold uppercase text-white/40 ml-1">Password</label>
                        {isLogin && <button type="button" onClick={() => setStep("forgot_password")} className="text-[10px] text-indigo-400 bg-transparent border-none cursor-pointer">Forgot?</button>}</div>
                        <input type="password" placeholder="••••••••" value={password} autoFocus onChange={e => setPassword(e.target.value)} className="w-full bg-white/[0.03] rounded-xl px-4 py-3 text-sm text-white border border-white/5 focus:border-indigo-500/40 focus:outline-none"/>
                      </div>
                    )}
                    <button type="submit" disabled={loading} className="w-full py-4 rounded-xl text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500 flex items-center justify-center gap-2 mt-4">
                      {loading ? <Loader2 className="h-5 w-5 animate-spin"/> : <>{isFirstStep ? "Next" : "Enter Brain"} <ArrowRight className="h-4 w-4"/></>}
                    </button>
                  </>
                )}
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
