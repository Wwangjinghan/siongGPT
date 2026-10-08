import { CircleCheck, UserRound } from "lucide-react";
import type { KnowledgeAnswer } from "@/types/knowledge";

type UserQuestionCardProps = Pick<KnowledgeAnswer, "question" | "askedAt" | "verificationLabel">;

export function UserQuestionCard({ question, askedAt, verificationLabel }: UserQuestionCardProps) {
  return (
    <section className="flex gap-5 px-7 pb-4 pt-4 sm:px-8">
      <div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-[#e7edff] text-[#315ee8]">
        <UserRound size={26} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="mb-1.5 text-[13px] font-semibold">User Question</p>
            <h2 className="max-w-[720px] text-[22px] font-extrabold leading-[1.22] tracking-[-.02em] text-brand-navy">{question}</h2>
          </div>
          <time className="shrink-0 pt-1 text-xs text-muted-blue">{askedAt}</time>
        </div>
        <div className="mt-2 inline-flex items-center gap-2 rounded-lg bg-brand-green-light px-2.5 py-1 text-[12px] text-[#24754e]">
          <CircleCheck size={18} fill="#258b57" className="text-white" />
          {verificationLabel}
        </div>
      </div>
    </section>
  );
}
