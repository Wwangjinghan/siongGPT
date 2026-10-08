"use client";

import { useState } from "react";
import { ChevronDown, LogOut, Menu, UserRound } from "lucide-react";
import type { UserProfile } from "@/types/user";

interface TopHeaderProps {
  title: string;
  subtitle: string;
  user: UserProfile;
  onMenuClick?: () => void;
  onLogout: () => Promise<void>;
  isLoggingOut?: boolean;
}

export function TopHeader({ title, subtitle, user, onMenuClick, onLogout, isLoggingOut = false }: TopHeaderProps) {
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [personalInfoOpen, setPersonalInfoOpen] = useState(false);

  async function handleLogout() {
    await onLogout();
    setUserMenuOpen(false);
    setPersonalInfoOpen(false);
  }

  return (
    <header className="relative z-40 flex h-[96px] shrink-0 items-center overflow-visible border-b border-line bg-white px-9">
      <div aria-hidden className="construction-art pointer-events-none absolute inset-y-0 right-[215px] w-[580px] bg-[position:center_bottom] opacity-65" />
      <button type="button" onClick={onMenuClick} className="focus-ring relative mr-4 rounded-lg p-2 text-brand-navy lg:hidden" aria-label="Open navigation">
        <Menu size={24} />
      </button>
      <div className="relative">
        <h1 className="text-[28px] font-extrabold leading-8 tracking-[-.02em] text-brand-navy">{title}</h1>
        <p className="mt-0.5 text-[17px] text-muted-blue">{subtitle}</p>
      </div>
      <div className="relative ml-auto flex items-center gap-5">
        <p className="hidden max-w-[210px] text-[12px] leading-[1.45] text-[#7485a4] xl:block">
          Knowledge for People.<br />Solutions for a Stronger Tomorrow.
        </p>
        <span className="hidden h-9 w-px bg-line xl:block" />
        <button type="button" onClick={() => setUserMenuOpen((open) => !open)} className="focus-ring flex items-center gap-3 rounded-lg p-1 text-left hover:bg-slate-50" aria-label="Open user menu" aria-expanded={userMenuOpen} aria-haspopup="menu">
          <span className="flex size-11 items-center justify-center rounded-full bg-[#e8edf5] text-sm font-semibold text-brand-navy">{user.initials}</span>
          <span className="hidden leading-tight sm:block">
            <strong className="block text-sm">{user.name}</strong>
            <span className="text-xs text-muted-blue">{user.organization}</span>
          </span>
          <ChevronDown className={`hidden text-muted-blue transition-transform sm:block ${userMenuOpen ? "rotate-180" : ""}`} size={16} />
        </button>
        {userMenuOpen ? (
          <div role="menu" className="card-shadow absolute right-0 top-[54px] z-50 w-60 rounded-lg border border-line bg-white p-1.5">
            <button type="button" role="menuitem" aria-expanded={personalInfoOpen} onClick={() => setPersonalInfoOpen((open) => !open)} className="focus-ring flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-sm text-brand-navy transition-colors hover:bg-slate-50">
              <UserRound size={16} /> Personal information
              <ChevronDown className={`ml-auto transition-transform ${personalInfoOpen ? "rotate-180" : ""}`} size={15} />
            </button>
            {personalInfoOpen ? (
              <div className="mx-2 mb-1 rounded-md bg-slate-50 px-3 py-2 text-xs">
                <strong className="block truncate text-brand-navy">{user.name}</strong>
                <span className="mt-0.5 block truncate text-muted-blue">{user.organization}</span>
              </div>
            ) : null}
            <div className="my-1 h-px bg-line" />
            <button type="button" role="menuitem" disabled={isLoggingOut} onClick={() => void handleLogout()} className="focus-ring flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-brand-navy transition-colors hover:bg-slate-50 disabled:opacity-60">
              <LogOut size={16} /> {isLoggingOut ? "Logging out..." : "Logout"}
            </button>
          </div>
        ) : null}
      </div>
    </header>
  );
}
