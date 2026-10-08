import type { KnowledgeAnswer } from "@/types/knowledge";
import { UserQuestionCard } from "./UserQuestionCard";
import { AnswerSection } from "./AnswerSection";
import { RecommendedActions } from "./RecommendedActions";
import { AnswerSources } from "./AnswerSources";
import { AnswerFeedback } from "./AnswerFeedback";

export function AnswerCard({ answer }: { answer: KnowledgeAnswer }) {
  return (
    <article className="card-shadow overflow-hidden rounded-xl border border-line bg-white">
      <UserQuestionCard question={answer.question} askedAt={answer.askedAt} verificationLabel={answer.verificationLabel} />
      <AnswerSection introduction={answer.introduction} requirements={answer.requirements} />
      <RecommendedActions actions={answer.recommendedActions} />
      <AnswerSources citations={answer.citations} />
      <AnswerFeedback />
    </article>
  );
}
