"use client";
 
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import AuthPortal from "@/components/AuthPortal";
import { getCurrentUser } from "@/lib/auth";
 
export default function AuthPage() {
  const router = useRouter();
 
  useEffect(() => {
    if (getCurrentUser()) {
      router.replace("/");
    }
  }, [router]);
 
  return <AuthPortal />;
}
