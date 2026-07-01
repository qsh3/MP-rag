// 类型定义

export interface Tag {
  id: string
  name: string
}

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  document_count: number
  chunk_count: number
  created_at: string
  ragflow_dataset_id?: string
}

export interface Document {
  id: string
  filename: string
  file_type: string
  file_size: number
  status: string
  chunk_count: number
  created_at: string
  kb_id: string
  tags: string
}

export interface SourceDoc {
  doc_name: string
  doc_id: string
  chunk_text: string
  score: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceDoc[]
  timestamp: string
}

export interface AskResponse {
  answer: string
  sources: SourceDoc[]
  kb_id: string
  question: string
}

export interface EvalMetric {
  name: string
  score: number
  description: string
  review_score?: number | null
}

export interface ReviewDetail {
  reviewed: boolean
  review_status: string
  reviewed_count: number
  avg_review_scores: Record<string, number>
  reason: string
  adjustments: string[]
}

export interface EvalReport {
  kb_id: string
  kb_name: string
  sample_count: number
  metrics: EvalMetric[]
  new_evaluated?: number
  created_at: string
  review?: ReviewDetail | null
}

export interface EvalDetailItem {
  id: string
  question: string
  answer: string
  contexts: string[]
  faithfulness: number | null
  answer_relevancy: number | null
  context_precision: number | null
  reviewed: number
  review_faithfulness: number | null
  review_answer_relevancy: number | null
  review_context_precision: number | null
  review_reason: string
  review_changes: string[]
  eval_raw: Record<string, any>       // 评估者完整推理
  review_raw: Record<string, any>     // 复审者完整推理
  created_at: string
}

export interface HealthStatus {
  status: string
  ragflow: string
  deepseek: string
  mysql: string
  qdrant: string
}

// 用户认证
export interface UserInfo {
  id: string
  username: string
  role: string
  tags: string
  is_active: number
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: UserInfo
}
