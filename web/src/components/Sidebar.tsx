"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquare, Link2, Settings, Shield, Brain } from "lucide-react";

const navItems = [
  { name: "Chat", href: "/", icon: MessageSquare },
  { name: "Connectors", href: "/connectors", icon: Link2 },
  { name: "Admin", href: "/admin", icon: Shield },
  { name: "Settings", href: "/settings", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="flex h-screen w-64 flex-col border-r bg-card/30 backdrop-blur-xl">
      <div className="flex h-16 items-center gap-2 px-6">
        <Brain className="h-8 w-8 text-primary" />
        <span className="text-xl font-bold tracking-tight">Assest</span>
      </div>

      <nav className="flex-1 space-y-1 px-4 py-4">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;

          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all ${
                isActive
                  ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20"
                  : "text-muted hover:bg-accent hover:text-foreground"
              }`}
            >
              <Icon className="h-5 w-5" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      <div className="border-t p-4">
        <div className="flex items-center gap-3 px-2">
          <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
            <span className="text-xs font-bold text-primary">JD</span>
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-medium">John Doe</span>
            <span className="text-xs text-muted">default-workspace</span>
          </div>
        </div>
      </div>
    </div>
  );
}
