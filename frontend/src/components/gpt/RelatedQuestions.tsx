import { ChevronRight, CircleHelp } from "lucide-react";
import type { RelatedQuestion } from "@/types/knowledge";
import { PanelCard } from "./PanelCard";

interface RelatedQuestionsProps {
  questions: RelatedQuestion[];
  onQuestionClick: (question: string) => void;
}

export function RelatedQuestions({ questions, onQuestionClick }: RelatedQuestionsProps) {
  return (
    <PanelCard title="Related Questions" icon={CircleHelp} viewAll>
      <ul className="px-4 py-1">
        {questions.map((item) => (
          <li key={item.id} className="border-b border-line last:border-0">
            <button type="button" onClick={() => onQuestionClick(item.question)} className="focus-ring flex w-full items-center gap-2 rounded-sm py-2 text-left text-[11px] font-medium text-action hover:text-blue-800">
              <span className="min-w-0 flex-1">{item.question}</span><ChevronRight size={16} className="shrink-0 text-brand-navy" />
            </button>
          </li>
        ))}
      </ul>
    </PanelCard>
  );
}
