export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Document {
  id: string;
  filename: string;
  status: "pending" | "ocr_processing" | "ocr_completed" | "embedding" | "ready" | "failed";
  pages: number | null;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citation_map: CitationMap | null;
  confidence_score: number | null;
  hallucination_flag: boolean;
  created_at: string;
}

export interface CitationMap {
  sources: CitationSource[];
  law_refs: LawReference[];
  case_refs: CaseReference[];
  total_citations: number;
}

export interface CitationSource {
  ref: string;
  ref_number: string;
  chunk_id: string | null;
  document_id: string | null;
  page_number: number | null;
}

export interface LawReference {
  law: string;
  article: string;
}

export interface CaseReference {
  chamber: string;
  date: string;
  case_no: string;
}

export interface PromptTemplate {
  slug: string;
  category: string;
  display_name_tr: string;
  display_name_en: string;
  description_tr: string;
  requires_rag: boolean;
  citation_required: boolean;
  billable: boolean;
  tags: string[];
}

export interface ChatResponse {
  answer: string;
  citation_map: CitationMap;
  confidence_score: number;
  hallucination_flag: boolean;
  flagged_claims: string[];
  sources: SourceChunk[];
}

export interface SourceChunk {
  chunk_id: string;
  document_id: string;
  page: number | null;
  text_snippet: string;
  similarity: number;
}
