import type { LucideIcon } from "lucide-react";

export interface NavigationItem {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  notification?: boolean;
}
