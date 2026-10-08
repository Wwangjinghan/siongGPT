import { Building2, Database, ExternalLink, Landmark } from "lucide-react";
import type { RelatedSystem } from "@/types/knowledge";
import { PanelCard } from "./PanelCard";

const systemIcons = { finance: Landmark, project: Building2, supplier: Database };

export function RelatedSystems({ systems }: { systems: RelatedSystem[] }) {
  return (
    <PanelCard title="Related Systems" icon={Database}>
      <div className="space-y-1.5 p-3">
        {systems.map((system) => {
          const Icon = systemIcons[system.icon];
          return (
            <a key={system.id} href={system.url} className="focus-ring flex min-h-[50px] items-center gap-3 rounded-lg border border-line px-3 py-1.5 transition-colors hover:bg-slate-50">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-[#eaf3ff] text-action"><Icon size={18} /></span>
              <span className="min-w-0 flex-1"><strong className="block text-[12px]">{system.name}</strong><span className="block truncate text-[10px] text-muted-blue">{system.description}</span></span>
              <ExternalLink className="text-action" size={16} />
            </a>
          );
        })}
      </div>
    </PanelCard>
  );
}
