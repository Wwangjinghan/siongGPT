import { ExternalLink, FileText } from "lucide-react";
import type { Citation } from "@/types/knowledge";

export function SourceCard({ citation }: { citation: Citation }) {
  return (
    <article className="flex min-w-0 flex-1 items-center gap-4 rounded-lg border border-line bg-[#fbfcfe] px-3 py-2.5">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[#e9f2ff] text-action"><FileText size={22} /></span>
      <div className="min-w-0 flex-1">
        <h4 className="truncate text-[13px] font-bold">{citation.title}</h4>
        <p className="text-[11px] text-muted-blue">{citation.version} <span className="px-1">·</span> {citation.updatedAt}</p>
        <p className="mt-0.5 truncate text-[11px] text-muted-blue">{citation.description}</p>
      </div>
      <a href={citation.documentUrl} className="focus-ring flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-action hover:bg-blue-50">
        Open source <ExternalLink size={15} />
      </a>
    </article>
  );
}
