import { BookOpen, ExternalLink, FileSpreadsheet } from "lucide-react";
import type { RelatedKnowledgeItem } from "@/types/knowledge";
import { PanelCard } from "./PanelCard";

export function RelatedKnowledge({ items }: { items: RelatedKnowledgeItem[] }) {
  return (
    <PanelCard title="Related Knowledge" icon={BookOpen} viewAll>
      <div className="space-y-2 p-3">
        {items.map((item) => (
          <article key={item.id} className="flex min-h-[73px] items-center gap-3 rounded-lg border border-line px-3 py-2">
            <span className={`flex h-11 w-8 shrink-0 items-center justify-center rounded border text-[9px] font-extrabold ${item.fileType === "PDF" ? "border-red-300 bg-red-50 text-red-600" : "border-emerald-300 bg-emerald-50 text-emerald-700"}`}>
              {item.fileType === "XLS" ? <FileSpreadsheet size={23} /> : item.fileType}
            </span>
            <div className="min-w-0 flex-1">
              <h3 className="line-clamp-2 text-[13px] font-bold leading-tight">{item.title}</h3>
              <p className="mt-1 text-[10px] text-muted-blue">{item.department} <span className="px-1">·</span> {item.documentType} <span className="px-1">·</span> {item.version}</p>
              <p className="text-[10px] text-muted-blue">{item.updatedAt}</p>
            </div>
            <a href={item.documentUrl} className="focus-ring flex shrink-0 items-center gap-1 rounded-md p-1 text-[11px] font-semibold text-action hover:bg-blue-50">Open <ExternalLink size={15} /></a>
          </article>
        ))}
      </div>
    </PanelCard>
  );
}
