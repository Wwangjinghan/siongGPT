export type VerificationStatus = "VERIFIED" | "PARTIALLY_VERIFIED" | "INSUFFICIENT_EVIDENCE";

export interface Citation {
  id: string;
  title: string;
  category: string;
  version: string;
  updatedAt: string;
  description: string;
  documentUrl: string;
}

export interface KnowledgeAnswer {
  id: string;
  question: string;
  askedAt: string;
  verificationStatus: VerificationStatus;
  verificationLabel: string;
  introduction: string;
  requirements: string[];
  recommendedActions: string[];
  citations: Citation[];
}

export interface RelatedKnowledgeItem {
  id: string;
  title: string;
  department: string;
  documentType: string;
  version: string;
  updatedAt: string;
  fileType: "PDF" | "XLS" | "DOC";
  documentUrl: string;
}

export interface RelatedSystem {
  id: string;
  name: string;
  description: string;
  url: string;
  icon: "finance" | "project" | "supplier";
}

export interface RelatedQuestion {
  id: string;
  question: string;
}
