"use client";

import { useState } from "react";
import { MoreHorizontal, Share2, ThumbsDown, ThumbsUp } from "lucide-react";
import { cn } from "@/lib/utils";

type Feedback = "helpful" | "not-helpful" | null;

export function AnswerFeedback() {
  const [feedback, setFeedback] = useState<Feedback>(null);
  return (
    <footer className="flex min-h-[50px] items-center border-t border-line px-7 text-[12px] sm:px-8">
      <span className="mr-3 text-muted-blue">Was this answer helpful?</span>
      <div className="flex gap-2">
        <button type="button" onClick={() => setFeedback("helpful")} aria-pressed={feedback === "helpful"} aria-label="Helpful" className={cn("focus-ring rounded-lg border border-line p-2 hover:bg-slate-50", feedback === "helpful" && "border-brand-green bg-brand-green-light text-brand-green")}><ThumbsUp size={16} /></button>
        <button type="button" onClick={() => setFeedback("not-helpful")} aria-pressed={feedback === "not-helpful"} aria-label="Not helpful" className={cn("focus-ring rounded-lg border border-line p-2 hover:bg-slate-50", feedback === "not-helpful" && "border-red-300 bg-red-50 text-red-600")}><ThumbsDown size={16} /></button>
      </div>
      <div className="ml-auto flex items-center gap-1">
        <button type="button" className="focus-ring flex items-center gap-2 rounded-lg px-3 py-2 hover:bg-slate-50"><Share2 size={16} /> <span className="hidden sm:inline">Share</span></button>
        <span className="h-7 w-px bg-line" />
        <button type="button" className="focus-ring rounded-lg p-2 hover:bg-slate-50" aria-label="More answer actions"><MoreHorizontal size={19} /></button>
      </div>
    </footer>
  );
}
