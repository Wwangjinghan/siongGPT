import type { LucideIcon } from "lucide-react";

interface PanelCardProps {
  title: string;
  icon: LucideIcon;
  viewAll?: boolean;
  children: React.ReactNode;
}

export function PanelCard({ title, icon: Icon, viewAll = false, children }: PanelCardProps) {
  return (
    <section className="card-shadow overflow-hidden rounded-xl border border-line bg-white">
      <header className="flex h-[53px] items-center gap-3 border-b border-line px-4">
        <Icon size={25} className="text-brand-navy" />
        <h2 className="text-[16px] font-bold">{title}</h2>
        {viewAll ? <button type="button" className="focus-ring ml-auto rounded-md px-2 py-1 text-xs font-medium text-action hover:bg-blue-50">View all&nbsp; →</button> : null}
      </header>
      {children}
    </section>
  );
}
