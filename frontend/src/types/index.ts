// 类型定义

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
}

export interface EvalReport {
  kb_id: string
  kb_name: string
  sample_count: number
  metrics: EvalMetric[]
  created_at: string
}

export interface HealthStatus {
  status: string
  ragflow: string
  deepseek: string
  mysql: string
  qdrant: string
}
