import api from './client'
import type { EvalReport } from '../types'

export async function runEval(kbId: string, testQuestions?: string[]): Promise<EvalReport> {
  const { data } = await api.post('/eval/run', { kb_id: kbId, test_questions: testQuestions })
  return data
}

export async function getEvalReport(kbId: string): Promise<EvalReport> {
  const { data } = await api.get(`/eval/report/${kbId}`)
  return data
}
