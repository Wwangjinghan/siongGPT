import { BookOpen } from "lucide-react";
import type { Citation } from "@/types/knowledge";
import { SourceCard } from "./SourceCard";

export function AnswerSources({ citations }: { citations: Citation[] }) {
  return (
    <section className="flex gap-5 border-t border-line px-7 py-3 sm:px-8">
      <div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-[#edf3fb] text-brand-navy"><BookOpen size={24} /></div>
      <div className="min-w-0 flex-1 pt-0.5">
        <h3 className="mb-2 text-[14px] font-bold">Source</h3>
        <div className="space-y-2">{citations.map((citation) => <SourceCard key={citation.id} citation={citation} />)}</div>
      </div>
    </section>
  );
}
