/* eslint-disable react-hooks/set-state-in-effect */
"use client";

import React, { useState, useRef, useEffect } from "react";
import { Brain, Mail, Lock, User, Loader2, ArrowRight, AlertCircle, CheckCircle2, ChevronLeft } from "lucide-react";
import { apiFetch, commitSession, WorkspaceInfo } from "@/lib/auth";
import { supabase } from "@/lib/supabase";
import { getSiteUrl } from "@/lib/config";

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

export default function AuthPortal() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [success, setSuccess] = useState<string | null>(null);

  // Field-specific validation errors (Google-style progressive authentication)
  const [emailError, setEmailError] = useState<React.ReactNode | null>(null);
  const [passwordError, setPasswordError] = useState<React.ReactNode | null>(null);
  const [fullNameError, setFullNameError] = useState<React.ReactNode | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);

  // Focus management input refs
  const emailInputRef = useRef<HTMLInputElement>(null);
  const passwordInputRef = useRef<HTMLInputElement>(null);

  // Last-account memory state
  const [savedEmail, setSavedEmail] = useState("");
  const [savedName, setSavedName] = useState("");
  const [useSavedAccount, setUseSavedAccount] = useState(false);

  // Progressive Wizard steps:
  // Login: "email" -> "password"
  // Join: "name_email" -> "create_password"
  const [step, setStep] = useState<"email" | "password" | "name_email" | "create_password">("email");

  const resetErrors = (loginMode = isLogin) => {
    setEmailError(null);
    setPasswordError(null);
    setFullNameError(null);
    setGeneralError(null);
    setStep(loginMode ? "email" : "name_email");
  };

  // Listen for saved account hydration and query parameter errors (e.g. from redirect callback)
  useEffect(() => {
    if (typeof window !== "undefined") {
      // Load last logged-in account if exists
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

      // Check URL for callback errors
      const params = new URLSearchParams(window.location.search);
      const urlError = params.get("error");
      if (urlError) {
        const decodedErr = decodeURIComponent(urlError);
        setGeneralError(decodedErr);

        // Auto-hydrate login/password steps for email collision redirection
        if (decodedErr.includes("already exists") || decodedErr.includes("already registered")) {
          setIsLogin(true);
          setStep("email");
          setUseSavedAccount(false);
          const emailMatch = decodedErr.match(/([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+)/);
          if (emailMatch) {
            setEmail(emailMatch[1]);
            setStep("password");
          }
        }

        // Clean up url so it isn't sticky on page refresh
        const cleanUrl = window.location.pathname;
        window.history.replaceState({}, document.title, cleanUrl);
      }
    }
  }, []);

  const [loading, setLoading] = useState(false);

  const handleNextStep = async () => {
    setEmailError(null);
    setFullNameError(null);
    setGeneralError(null);
    let hasError = false;

    if (isLogin) {
      if (!email.trim()) {
        setEmailError("Enter an email address");
        hasError = true;
      } else if (!/\S+@\S+\.\S+/.test(email)) {
        setEmailError("Enter a valid email address");
        hasError = true;
      }

      if (hasError) return;

      setLoading(true);
      try {
        const response = await apiFetch("/api/users/check-email", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ email }),
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || "Failed to verify email.");
        }

        const data = await response.json();
        if (!data.exists) {
          setEmailError(
            <>
              {"Couldn't find your account."}{" "}
              <button
                type="button"
                onClick={() => {
                  setIsLogin(false);
                  setStep("name_email");
                  setEmailError(null);
                  setPasswordError(null);
                  setFullNameError(null);
                  setGeneralError(null);
                  setTimeout(() => {
                    emailInputRef.current?.focus();
                  }, 50);
                }}
                className="text-indigo-400 hover:text-indigo-300 underline font-semibold focus:outline-none cursor-pointer"
              >
                Create one instead
              </button>
            </>
          );
        } else if (data.auth_type === "oauth") {
          setEmailError(
            <>
              This account uses Google/GitHub to sign in. Please use the Google/GitHub buttons above.
            </>
          );
        } else {
          setStep("password");
        }
      } catch (err: unknown) {
        const errMsg = err instanceof Error ? err.message : "An error occurred.";
        setGeneralError(errMsg);
      } finally {
        setLoading(false);
      }

    } else {
      if (!fullName.trim()) {
        setFullNameError("Enter first and last name");
        hasError = true;
      }

      if (!email.trim()) {
        setEmailError("Enter an email address");
        hasError = true;
      } else if (!/\S+@\S+\.\S+/.test(email)) {
        setEmailError("Enter a valid email address");
        hasError = true;
      }

      if (hasError) return;

      setLoading(true);
      try {
        const response = await apiFetch("/api/users/check-email", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ email }),
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || "Failed to verify email.");
        }

        const data = await response.json();
        if (data.exists) {
          setEmailError(
            <>
              This email is already in use.{" "}
              <button
                type="button"
                onClick={() => {
                  setIsLogin(true);
                  if (data.auth_type === "password") {
                    setStep("password");
                  } else {
                    setStep("email");
                  }
                  setEmailError(null);
                  setPasswordError(null);
                  setFullNameError(null);
                  setGeneralError(null);
                  setTimeout(() => {
                    passwordInputRef.current?.focus();
                  }, 50);
                }}
                className="text-indigo-400 hover:text-indigo-300 underline font-semibold focus:outline-none cursor-pointer"
              >
                Sign in instead
              </button>
            </>
          );
        } else {
          setStep("create_password");
        }
      } catch (err: unknown) {
        const errMsg = err instanceof Error ? err.message : "An error occurred.";
        setGeneralError(errMsg);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleFinalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError(null);
    setGeneralError(null);
    let hasError = false;

    if (isLogin) {
      if (!password.trim()) {
        setPasswordError("Enter a password");
        hasError = true;
      }
      if (hasError) return;

      setSuccess(null);
      setLoading(true);

      try {
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
          const detail = errData.detail || "Invalid email or password.";
          
          if (detail.includes("Incorrect password") || detail.includes("Incorrect email or password")) {
            setPasswordError("Wrong password. Try again or check details.");
          } else {
            setGeneralError(detail);
          }
          return;
        }

        const data = await response.json();
        const token = data.access_token;

        // Fetch profile and workspaces in parallel for speed
        const [userRes, workspaceRes] = await Promise.all([
          apiFetch("/api/users/me", {
            headers: { Authorization: `Bearer ${token}` }
          }),
          apiFetch("/api/workspaces", {
            headers: { Authorization: `Bearer ${token}` }
          })
        ]);

        if (!userRes.ok) {
          throw new Error("Failed to fetch user profile details.");
        }

        const userData = await userRes.json();
        const userInfo = {
          id: userData.id,
          email: userData.email,
          full_name: userData.full_name,
        };

        if (typeof window !== "undefined") {
          localStorage.setItem("assest_last_email", userInfo.email);
          if (userInfo.full_name) {
            localStorage.setItem("assest_last_name", userInfo.full_name);
          }
        }

        let workspace: WorkspaceInfo | null = null;
        if (workspaceRes.ok) {
          const workspaces = await workspaceRes.json() as WorkspaceInfo[];
          if (workspaces && workspaces.length > 0) {
            workspace = workspaces[0];
          } else {
            const wsName = "My Workspace";
            const wsSlug = `workspace-${Math.random().toString(36).substring(2, 10)}`;
            const createWsRes = await apiFetch("/api/workspaces", {
              method: "POST",
              headers: { 
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
              },
              body: JSON.stringify({ name: wsName, slug: wsSlug })
            });
            if (createWsRes.ok) {
              workspace = await createWsRes.json();
            }
          }
        }

        commitSession(token, userInfo, workspace);
        setSuccess("Success! Logging in...");
        if (typeof window !== "undefined") {
          window.location.replace("/");
        }
      } catch (err: unknown) {
        const errMsg = err instanceof Error ? err.message : "An unexpected error occurred.";
        setGeneralError(errMsg);
      } finally {
        setLoading(false);
      }
    } else {
      if (!password.trim()) {
        setPasswordError("Enter a password");
        hasError = true;
      } else if (password.length < 6) {
        setPasswordError("Use 6 characters or more for your password");
        hasError = true;
      }

      if (hasError) return;

      setSuccess(null);
      setLoading(true);

      try {
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
          const detail = errData.detail || "Registration failed. Email might be in use.";
          
          if (detail.includes("Email already registered")) {
            setEmailError(
              <>
                This email is already in use.{" "}
                <button
                  type="button"
                  onClick={() => {
                    setIsLogin(true);
                    setStep("password");
                    setEmailError(null);
                    setPasswordError(null);
                    setFullNameError(null);
                    setGeneralError(null);
                    setTimeout(() => {
                      passwordInputRef.current?.focus();
                    }, 50);
                  }}
                  className="text-indigo-400 hover:text-indigo-300 underline font-semibold focus:outline-none cursor-pointer"
                >
                  Sign in instead
                </button>
              </>
            );
            setStep("name_email");
          } else {
            setGeneralError(detail);
          }
          return;
        }

        setSuccess("Account created! Entering Brain...");
        
        // --- AUTO-LOGIN ---
        const params = new URLSearchParams();
        params.append("username", email);
        params.append("password", password);

        const loginRes = await apiFetch("/api/login", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: params,
        });

        if (!loginRes.ok) {
          throw new Error("Account created but auto-login failed. Please sign in manually.");
        }

        const loginData = await loginRes.json();
        const token = loginData.access_token;
        
        const [userRes, workspaceRes] = await Promise.all([
          apiFetch("/api/users/me", {
            headers: { Authorization: `Bearer ${token}` }
          }),
          apiFetch("/api/workspaces", {
            headers: { Authorization: `Bearer ${token}` }
          })
        ]);

        if (!userRes.ok) {
          throw new Error("Auto-login succeeded but failed to load user profile.");
        }

        const userData = await userRes.json();
        const userInfo = {
          id: userData.id,
          email: userData.email,
          full_name: userData.full_name || fullName,
        };

        if (typeof window !== "undefined") {
          localStorage.setItem("assest_last_email", userInfo.email);
          if (userInfo.full_name) {
            localStorage.setItem("assest_last_name", userInfo.full_name);
          }
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
              headers: { 
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
              },
              body: JSON.stringify({ name: wsName, slug: wsSlug })
            });
            if (createWsRes.ok) {
              workspace = await createWsRes.json();
            }
          }
        }

        commitSession(token, userInfo, workspace);
        setSuccess("Success! Entering Brain...");
        if (typeof window !== "undefined") {
          window.location.replace("/");
        }
      } catch (err: unknown) {
        const errMsg = err instanceof Error ? err.message : "An unexpected error occurred.";
        setGeneralError(errMsg);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isLogin) {
      if (step === "email") {
        handleNextStep();
      } else {
        handleFinalSubmit(e);
      }
    } else {
      if (step === "name_email") {
        handleNextStep();
      } else {
        handleFinalSubmit(e);
      }
    }
  };

  const handleBackToEmail = () => {
    setStep(isLogin ? "email" : "name_email");
    setPassword("");
    setPasswordError(null);
    setGeneralError(null);
    setTimeout(() => {
      emailInputRef.current?.focus();
    }, 50);
  };

  const handleSocialLogin = async (provider: 'google' | 'github') => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: provider,
      options: {
        redirectTo: `${getSiteUrl()}/auth/callback`,
      },
    });
    if (error) {
      console.error(`${provider} login error:`, error.message);
      setGeneralError(`${provider} login failed. Please try again.`);
    }
  };

  const isFirstStep = step === "email" || step === "name_email";

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
          
          {useSavedAccount && savedEmail ? (
            /* Welcome Back Card (Personalized Avatar + Name + Password) */
            <div className="flex flex-col items-center animate-fade-in">
              <div className="relative group mb-6">
                <div className="absolute inset-0 bg-indigo-500/10 rounded-full blur-md group-hover:bg-indigo-500/20 transition duration-500" />
                <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-[#0f172a] border border-white/10 shadow-inner text-indigo-400 text-2xl font-bold uppercase tracking-wider">
                  {savedName ? savedName.split(" ").map(n => n[0]).slice(0, 2).join("") : savedEmail[0].toUpperCase()}
                </div>
              </div>
              
              <div className="text-center mb-6 w-full">
                <h2 className="text-xl font-bold text-white mb-1 truncate px-2">
                  Welcome back, {savedName ? savedName.split(" ")[0] : "User"}
                </h2>
                <p className="text-xs text-white/40 truncate max-w-[280px] mx-auto">
                  {savedEmail}
                </p>
              </div>

              {/* Password Form for Saved Account */}
              <form className="w-full space-y-4" onSubmit={handleFormSubmit}>
                {generalError && (
                  <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs animate-shake">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    <span>{generalError}</span>
                  </div>
                )}
                {success && (
                  <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs animate-fade-in">
                    <CheckCircle2 className="h-4 w-4 shrink-0" />
                    <span>{success}</span>
                  </div>
                )}

                <div className="space-y-1.5 group/field">
                  <label className={`text-[11px] font-bold uppercase tracking-wider ml-1 transition-colors ${passwordError ? 'text-rose-400' : 'text-white/40 group-focus-within/field:text-indigo-400'}`}>
                    Password
                  </label>
                  <div className="relative">
                    <Lock className={`absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 transition-colors ${passwordError ? 'text-rose-400/60' : 'text-white/20 group-focus-within/field:text-indigo-400/60'}`} />
                    <input
                      type="password"
                      placeholder="••••••••"
                      value={password}
                      autoFocus
                      ref={passwordInputRef}
                      onChange={(e) => {
                        setPassword(e.target.value);
                        if (passwordError) setPasswordError(null);
                      }}
                      className={`w-full bg-white/[0.03] rounded-xl pl-11 pr-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none transition-all duration-300 border ${
                        passwordError 
                          ? 'border-rose-500/40 focus:border-rose-500/60 bg-rose-500/[0.02]' 
                          : 'border-white/5 focus:border-indigo-500/40 focus:bg-white/[0.06]'
                      }`}
                    />
                  </div>
                  {passwordError && (
                    <p className="text-[10px] text-rose-400 ml-1 mt-1 font-medium flex items-center gap-1.5 animate-fade-in">
                      <AlertCircle className="h-3 w-3 shrink-0" />
                      {passwordError}
                    </p>
                  )}
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
                      <span className="relative z-10">Enter Brain</span>
                      <ArrowRight className="h-4 w-4 relative z-10 group-hover/submit:translate-x-1 transition-transform" />
                      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000" />
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setUseSavedAccount(false);
                    setEmail("");
                    setFullName("");
                    setPassword("");
                    resetErrors(true);
                    setTimeout(() => {
                      emailInputRef.current?.focus();
                    }, 50);
                  }}
                  className="w-full text-center text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition mt-4 focus:outline-none cursor-pointer bg-transparent border-none"
                >
                  Use another account
                </button>
              </form>
            </div>
          ) : (
            /* Standard progressive auth flow */
            <>
              {/* Tab Switcher - only show on first step */}
              {isFirstStep ? (
                <div className="flex rounded-2xl bg-black/20 p-1.5 border border-white/5 mb-8 animate-fade-in">
                  <button
                    type="button"
                    onClick={() => { setIsLogin(true); resetErrors(true); }}
                    className={`flex-1 py-2.5 text-sm font-semibold rounded-xl transition-all duration-500 ${
                      isLogin 
                        ? "bg-indigo-600 text-white shadow-[0_0_20px_rgba(99,102,241,0.3)]" 
                        : "text-gray-400 hover:text-gray-200"
                    }`}
                  >
                    Sign In
                  </button>
                  <button
                    type="button"
                    onClick={() => { setIsLogin(false); resetErrors(false); }}
                    className={`flex-1 py-2.5 text-sm font-semibold rounded-xl transition-all duration-500 ${
                      !isLogin 
                        ? "bg-indigo-600 text-white shadow-[0_0_20px_rgba(99,102,241,0.3)]" 
                        : "text-gray-400 hover:text-gray-200"
                    }`}
                  >
                    Join
                  </button>
                </div>
              ) : (
                /* Email Pill Header for Step 2 */
                <div className="flex items-center gap-3 px-4 py-3 bg-white/[0.03] border border-white/5 rounded-2xl mb-6 animate-fade-in">
                  <button
                    type="button"
                    onClick={handleBackToEmail}
                    className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-white/5 transition-all text-white/50 hover:text-white bg-transparent border-none cursor-pointer"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <div className="flex-1 min-w-0">
                    <div className="text-[10px] font-bold text-white/40 uppercase tracking-wider">
                      {isLogin ? "Signing in as" : "Creating account for"}
                    </div>
                    <div className="text-sm font-medium text-white truncate">
                      {email}
                    </div>
                  </div>
                </div>
              )}

              {/* Social Logins - only show on first step */}
              {isFirstStep && (
                <div className="space-y-3 mb-8 animate-fade-in">
                  <div className="grid grid-cols-2 gap-3">
                    <button 
                      type="button"
                      onClick={() => handleSocialLogin('google')}
                      className="flex items-center justify-center py-3 px-4 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.08] hover:border-white/10 transition-all duration-300 group/btn cursor-pointer"
                    >
                      <GoogleIcon />
                    </button>
                    <button 
                      type="button"
                      onClick={() => handleSocialLogin('github')}
                      className="flex items-center justify-center py-3 px-4 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.08] hover:border-white/10 transition-all duration-300 group/btn cursor-pointer"
                    >
                      <GitHubIcon />
                    </button>
                  </div>
                  <div className="relative flex items-center justify-center py-2">
                    <div className="absolute inset-0 flex items-center">
                      <div className="w-full border-t border-white/5"></div>
                    </div>
                    <span className="relative px-4 text-[10px] font-bold uppercase tracking-[0.2em] text-white/20 bg-[#020617]">
                      or use email
                    </span>
                  </div>
                </div>
              )}

              {/* Form */}
              <form className="space-y-4" onSubmit={handleFormSubmit}>
                {generalError && (
                  <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs animate-shake">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    <span>{generalError}</span>
                  </div>
                )}
                {success && (
                  <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs animate-fade-in">
                    <CheckCircle2 className="h-4 w-4 shrink-0" />
                    <span>{success}</span>
                  </div>
                )}

                {/* JOIN STEP 1: Full Name */}
                {!isLogin && step === "name_email" && (
                  <div className="space-y-1.5 group/field animate-fade-in">
                    <label className={`text-[11px] font-bold uppercase tracking-wider ml-1 transition-colors ${fullNameError ? 'text-rose-400' : 'text-white/40 group-focus-within/field:text-indigo-400'}`}>
                      Identity
                    </label>
                    <div className="relative">
                      <User className={`absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 transition-colors ${fullNameError ? 'text-rose-400/60' : 'text-white/20 group-focus-within/field:text-indigo-400/60'}`} />
                      <input
                        type="text"
                        placeholder="Enter your name"
                        value={fullName}
                        onChange={(e) => {
                          setFullName(e.target.value);
                          if (fullNameError) setFullNameError(null);
                        }}
                        className={`w-full bg-white/[0.03] rounded-xl pl-11 pr-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none transition-all duration-300 border ${
                          fullNameError 
                            ? 'border-rose-500/40 focus:border-rose-500/60 bg-rose-500/[0.02]' 
                            : 'border-white/5 focus:border-indigo-500/40 focus:bg-white/[0.06]'
                        }`}
                      />
                    </div>
                    {fullNameError && (
                      <p className="text-[10px] text-rose-400 ml-1 mt-1 font-medium flex items-center gap-1.5 animate-fade-in">
                        <AlertCircle className="h-3 w-3 shrink-0" />
                        {fullNameError}
                      </p>
                    )}
                  </div>
                )}

                {/* STEP 1 (BOTH): Email */}
                {isFirstStep && (
                  <div className="space-y-1.5 group/field animate-fade-in">
                    <label className={`text-[11px] font-bold uppercase tracking-wider ml-1 transition-colors ${emailError ? 'text-rose-400' : 'text-white/40 group-focus-within/field:text-indigo-400'}`}>
                      Email
                    </label>
                    <div className="relative">
                      <Mail className={`absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 transition-colors ${emailError ? 'text-rose-400/60' : 'text-white/20 group-focus-within/field:text-indigo-400/60'}`} />
                      <input
                        type="email"
                        placeholder="name@work.com"
                        value={email}
                        ref={emailInputRef}
                        onChange={(e) => {
                          setEmail(e.target.value);
                          if (emailError) setEmailError(null);
                        }}
                        className={`w-full bg-white/[0.03] rounded-xl pl-11 pr-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none transition-all duration-300 border ${
                          emailError 
                            ? 'border-rose-500/40 focus:border-rose-500/60 bg-rose-500/[0.02]' 
                            : 'border-white/5 focus:border-indigo-500/40 focus:bg-white/[0.06]'
                        }`}
                      />
                    </div>
                    {emailError && (
                      <p className="text-[10px] text-rose-400 ml-1 mt-1 font-medium flex items-start gap-1.5 animate-fade-in leading-relaxed">
                        <AlertCircle className="h-3 w-3 shrink-0 mt-0.5" />
                        <span className="flex-1">{emailError}</span>
                      </p>
                    )}
                  </div>
                )}

                {/* STEP 2 (BOTH): Password */}
                {!isFirstStep && (
                  <div className="space-y-1.5 group/field animate-fade-in">
                    <label className={`text-[11px] font-bold uppercase tracking-wider ml-1 transition-colors ${passwordError ? 'text-rose-400' : 'text-white/40 group-focus-within/field:text-indigo-400'}`}>
                      Password
                    </label>
                    <div className="relative">
                      <Lock className={`absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 transition-colors ${passwordError ? 'text-rose-400/60' : 'text-white/20 group-focus-within/field:text-indigo-400/60'}`} />
                      <input
                        type="password"
                        placeholder="••••••••"
                        value={password}
                        autoFocus
                        ref={passwordInputRef}
                        onChange={(e) => {
                          setPassword(e.target.value);
                          if (passwordError) setPasswordError(null);
                        }}
                        className={`w-full bg-white/[0.03] rounded-xl pl-11 pr-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none transition-all duration-300 border ${
                          passwordError 
                            ? 'border-rose-500/40 focus:border-rose-500/60 bg-rose-500/[0.02]' 
                            : 'border-white/5 focus:border-indigo-500/40 focus:bg-white/[0.06]'
                        }`}
                      />
                    </div>
                    {passwordError && (
                      <p className="text-[10px] text-rose-400 ml-1 mt-1 font-medium flex items-center gap-1.5 animate-fade-in">
                        <AlertCircle className="h-3 w-3 shrink-0" />
                        {passwordError}
                      </p>
                    )}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full relative flex items-center justify-center gap-2 py-4 px-4 rounded-xl text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500 overflow-hidden disabled:opacity-50 transition-all duration-500 shadow-[0_10px_30px_rgba(99,102,241,0.2)] active:scale-[0.98] group/submit mt-4"
                >
                  {loading ? (
                    <>
                      <Loader2 className="h-5 w-5 animate-spin" />
                      <span className="animate-pulse">
                        {isFirstStep ? "Verifying..." : "Accessing Brain..."}
                      </span>
                    </>
                  ) : (
                    <>
                      <span className="relative z-10">
                        {isFirstStep 
                          ? "Next" 
                          : (isLogin ? "Enter Brain" : "Create Brain")
                        }
                      </span>
                      <ArrowRight className="h-4 w-4 relative z-10 group-hover/submit:translate-x-1 transition-transform" />
                      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000" />
                    </>
                  )}
                </button>
              </form>
            </>
          )}
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
