"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  BookOpen,
  BotMessageSquare,
  ClipboardCheck,
  FileText,
  Home,
  Star,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { routes } from "@/lib/routes";
import type { NavigationItem } from "@/types/navigation";
import { BrandLogo } from "./BrandLogo";

const navigationItems: NavigationItem[] = [
  { id: "dashboard", label: "Dashboard", href: routes.dashboard, icon: Home },
  { id: "gpt", label: "Siong GPT", href: routes.gpt, icon: BotMessageSquare },
  { id: "knowledge", label: "Knowledge Hub", href: routes.knowledge, icon: BookOpen },
  { id: "documents", label: "Documents", href: routes.documents, icon: FileText },
  { id: "favorites", label: "Favorites / Recent", href: routes.favorites, icon: Star },
  { id: "tasks", label: "My Tasks", href: routes.tasks, icon: ClipboardCheck },
  { id: "notifications", label: "Notifications", href: routes.notifications, icon: Bell, notification: true },
];

interface SidebarProps {
  className?: string;
  onClose?: () => void;
}

export function Sidebar({ className, onClose }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className={cn("relative flex h-full w-[264px] shrink-0 flex-col overflow-hidden border-r border-line bg-white", className)}>
      <div className="flex h-[98px] shrink-0 items-center border-b border-line px-5">
        <BrandLogo priority />
        {onClose ? (
          <button type="button" onClick={onClose} className="focus-ring ml-auto rounded-md p-2 text-muted-blue lg:hidden" aria-label="Close navigation">
            <X size={20} />
          </button>
        ) : null}
      </div>

      <nav aria-label="Main navigation" className="relative z-10 px-3 pt-7">
        <ul className="space-y-2">
          {navigationItems.map((item) => {
            const active = pathname === item.href;
            const Icon = item.icon;
            return (
              <li key={item.id}>
                <Link
                  href={item.href}
                  onClick={onClose}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "focus-ring relative flex h-[52px] items-center gap-5 rounded-r-[10px] rounded-l-md px-5 text-[16px] font-medium transition-colors",
                    active ? "bg-brand-green-light font-bold text-brand-navy" : "text-brand-navy hover:bg-slate-50",
                  )}
                >
                  {active ? <span aria-hidden className="absolute inset-y-0 -left-3 w-1 rounded-r bg-brand-green" /> : null}
                  <span className="relative">
                    <Icon size={24} strokeWidth={1.9} />
                    {item.notification ? <span className="absolute -right-1 -top-1 size-2 rounded-full bg-red-500 ring-2 ring-white" /> : null}
                  </span>
                  <span>{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div aria-hidden className="construction-art pointer-events-none absolute inset-x-0 bottom-0 h-[315px] bg-[position:bottom_left] opacity-70" />
      <div className="relative z-10 mt-auto mb-4 px-[30px] text-[10px] font-semibold tracking-[.34em] text-[#7385a1]">
        <p>BUILDING</p><p>A BETTER</p><p>TOMORROW</p>
        <span className="mt-2 block h-0.5 w-11 bg-brand-green" />
      </div>
    </aside>
  );
}
