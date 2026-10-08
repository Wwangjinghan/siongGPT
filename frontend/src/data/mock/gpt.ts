import type {
  KnowledgeAnswer,
  RelatedKnowledgeItem,
  RelatedQuestion,
  RelatedSystem,
} from "@/types/knowledge";

export const mockAnswer: KnowledgeAnswer = {
  id: "answer-supplier-payment-001",
  question: "What documents are required before submitting a supplier payment request?",
  askedAt: "Just now",
  verificationStatus: "VERIFIED",
  verificationLabel: "Verified from approved company knowledge",
  introduction: "Before submitting a supplier payment request, the following documents and information are required:",
  requirements: [
    "Supplier invoice (original or soft copy)",
    "Approved PO or quotation",
    "Delivery Order or supporting document (e.g. service report, completion certificate)",
    "Project / cost code",
    "Required approval record (e.g. department head or project manager approval)",
  ],
  recommendedActions: [
    "Check that the invoice and PO information match",
    "Confirm all supporting documents are attached",
    "Verify project code and approval status",
    "Contact Finance if anything is missing",
  ],
  citations: [
    {
      id: "citation-finance-sop-24",
      title: "Finance SOP · Supplier Payment",
      category: "Finance SOP",
      version: "Version 2.4",
      updatedAt: "Updated Sep 2026",
      description: "Procedure for processing supplier payments, required documents and approval workflow.",
      documentUrl: "#source-finance-sop",
    },
  ],
};

export const mockRelatedKnowledge: RelatedKnowledgeItem[] = [
  {
    id: "supplier-payment-sop",
    title: "Supplier Payment SOP",
    department: "Finance",
    documentType: "SOP",
    version: "Version 2.4",
    updatedAt: "Updated Sep 2026",
    fileType: "PDF",
    documentUrl: "#supplier-payment-sop",
  },
  {
    id: "payment-checklist",
    title: "Payment Supporting Document Checklist",
    department: "Finance",
    documentType: "Form",
    version: "Version 1.3",
    updatedAt: "Updated Aug 2026",
    fileType: "XLS",
    documentUrl: "#payment-checklist",
  },
];

export const mockRelatedSystems: RelatedSystem[] = [
  { id: "finance", name: "Finance System", description: "Process payments and check status", url: "#finance-system", icon: "finance" },
  { id: "project", name: "Project System", description: "View project details and cost codes", url: "#project-system", icon: "project" },
  { id: "supplier", name: "Supplier Portal", description: "Supplier information and records", url: "#supplier-portal", icon: "supplier" },
];

export const mockRelatedQuestions: RelatedQuestion[] = [
  { id: "po-mismatch", question: "What if the PO amount does not match the invoice?" },
  { id: "approval", question: "Who needs to approve the payment?" },
  { id: "processing-time", question: "How long does a supplier payment take to process?" },
  { id: "without-po", question: "Can I submit a payment request without a PO?" },
  { id: "status", question: "Where can I check the payment status?" },
];
