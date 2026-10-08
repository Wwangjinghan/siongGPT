"use client";

import { useState } from "react";
import { MainContent } from "@/components/layout/MainContent";
import { ContextPanel } from "@/components/layout/ContextPanel";
import { KnowledgeSearchBar } from "@/components/gpt/KnowledgeSearchBar";
import { AnswerCard } from "@/components/gpt/AnswerCard";
import { RelatedKnowledge } from "@/components/gpt/RelatedKnowledge";
import { RelatedSystems } from "@/components/gpt/RelatedSystems";
import { RelatedQuestions } from "@/components/gpt/RelatedQuestions";
import { mockAnswer, mockRelatedKnowledge, mockRelatedQuestions, mockRelatedSystems } from "@/data/mock/gpt";

export default function GptPage() {
  const [query, setQuery] = useState("");

  function submitQuery() {
    if (!query.trim()) return;
    console.info("Mock knowledge query submitted:", query.trim());
  }

  function selectRelatedQuestion(question: string) {
    setQuery(question);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className="mx-auto grid w-full max-w-[1600px] grid-cols-1 gap-7 p-5 xl:grid-cols-[minmax(600px,880px)_minmax(380px,448px)] 2xl:gap-7 2xl:px-9">
      <MainContent className="space-y-2.5">
        <KnowledgeSearchBar value={query} onChange={setQuery} onSubmit={submitQuery} />
        <AnswerCard answer={mockAnswer} />
      </MainContent>
      <ContextPanel className="space-y-3.5">
        <RelatedKnowledge items={mockRelatedKnowledge} />
        <RelatedSystems systems={mockRelatedSystems} />
        <RelatedQuestions questions={mockRelatedQuestions} onQuestionClick={selectRelatedQuestion} />
      </ContextPanel>
    </div>
  );
}
