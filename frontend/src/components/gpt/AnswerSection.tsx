import { Sparkles } from "lucide-react";

interface AnswerSectionProps {
  introduction: string;
  requirements: string[];
}

export function AnswerSection({ introduction, requirements }: AnswerSectionProps) {
  return (
    <section className="flex gap-5 border-t border-line px-7 py-3 sm:px-8">
      <div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-[#e4f6ea] text-brand-navy">
        <Sparkles size={25} fill="currentColor" />
      </div>
      <div className="min-w-0 pt-0.5 text-[13px] leading-[1.45]">
        <h3 className="mb-1.5 text-[14px] font-bold">Answer</h3>
        <p>{introduction}</p>
        <ul className="mt-2 space-y-1">
          {requirements.map((requirement, index) => (
            <li key={requirement} className="flex items-start gap-3">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-[#e8edf5] text-xs font-semibold text-brand-navy">{index + 1}</span>
              <span className="pt-0.5">{requirement}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
