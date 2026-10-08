"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { routes } from "@/lib/routes";
import { Sidebar } from "./Sidebar";
import { TopHeader } from "./TopHeader";

interface AppShellProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
}

function getInitials(displayName: string): string {
  return displayName
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
}

export function AppShell({ children, title = "Siong GPT", subtitle = "Enterprise Knowledge Workspace" }: AppShellProps) {
  const router = useRouter();
  const { logout, user } = useAuth();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  if (!user) {
    return null;
  }

  const currentUser = {
    initials: getInitials(user.display_name),
    name: user.display_name,
    organization: user.department?.name ?? user.roles[0]?.name ?? "Siong Construction",
  };

  async function handleLogout() {
    setIsLoggingOut(true);

    try {
      await logout();
      router.replace(routes.login);
      router.refresh();
    } catch {
      console.error("Unable to log out. Please try again.");
    } finally {
      setIsLoggingOut(false);
    }
  }

  return (
    <div className="flex h-dvh min-h-[720px] overflow-hidden bg-page">
      <Sidebar className="hidden lg:flex" />
      {mobileNavOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button type="button" aria-label="Close navigation" className="absolute inset-0 bg-brand-navy/35" onClick={() => setMobileNavOpen(false)} />
          <Sidebar className="relative z-10 flex" onClose={() => setMobileNavOpen(false)} />
        </div>
      ) : null}
      <div className="flex min-w-0 flex-1 flex-col">
        <TopHeader title={title} subtitle={subtitle} user={currentUser} onMenuClick={() => setMobileNavOpen(true)} onLogout={handleLogout} isLoggingOut={isLoggingOut} />
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
