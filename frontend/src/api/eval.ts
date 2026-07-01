import api from './client'
import type { EvalReport } from '../types'

export async function runEval(kbId: string, testQuestions?: string[]): Promise<EvalReport> {
  const { data } = await api.post('/eval/run', { kb_id: kbId, test_questions: testQuestions })
  return data
}

export async function runReview(kbId: string, maxSamples?: number): Promise<EvalReport> {
  const { data } = await api.post('/eval/review', { kb_id: kbId, max_samples: maxSamples || 10 })
  return data
}

export async function getEvalReport(kbId: string): Promise<EvalReport> {
  const { data } = await api.get(`/eval/report/${kbId}`)
  return data
}

export async function getEvalDetails(kbId: string, limit?: number): Promise<{ total: number; items: any[] }> {
  const { data } = await api.get(`/eval/details/${kbId}`, { params: { limit: limit || 20 } })
  return data
}

export async function clearEvalRecords(kbId: string): Promise<{ deleted: number }> {
  const { data } = await api.delete(`/eval/records/${kbId}`)
  return data
}
