import type { SourceDoc } from '../types'

export interface SSEEvent {
  event: string
  data: string
}

/**
 * SSE 流式问答请求
 * @returns 一个可取消的 fetch 对象
 */
export function askStream(
  kbId: string,
  question: string,
  topK: number = 5,
  sessionId?: string,
): { abort: () => void; promise: Promise<void> } {
  const controller = new AbortController()

  const promise = new Promise<void>((resolve, reject) => {
    const token = localStorage.getItem('mp_auth_token')
    fetch('/api/v1/qa/ask', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ kb_id: kbId, question, top_k: topK, stream: true, session_id: sessionId }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          reject(new Error(`HTTP ${response.status}`))
          return
        }

        const reader = response.body?.getReader()
        if (!reader) {
          reject(new Error('No response body'))
          return
        }

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          let currentEvent = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              const data = line.slice(6).trim()
              _dispatchSSE(currentEvent, data)
            }
          }
        }
        resolve()
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          reject(err)
        }
      })
  })

  return { abort: () => controller.abort(), promise }
}

/** SSE 事件分发 — 外部订阅者绑定 */
const _listeners: Record<string, Array<(data: string) => void>> = {
  token: [],
  sources: [],
  done: [],
  error: [],
}

function _dispatchSSE(event: string, data: string) {
  ;(_listeners[event] || []).forEach(fn => fn(data))
}

export function onSSE(event: string, fn: (data: string) => void) {
  if (!_listeners[event]) _listeners[event] = []
  _listeners[event].push(fn)
}

export function offSSE(event: string, fn: (data: string) => void) {
  if (!_listeners[event]) return
  _listeners[event] = _listeners[event].filter(f => f !== fn)
}

export async function getHistory(kbId: string): Promise<{ total: number; items: any[] }> {
  const { data } = await (await import('./client')).default.get(`/qa/history/${kbId}`)
  return data
}

export async function deleteSession(kbId: string, sessionId: string): Promise<void> {
  await (await import('./client')).default.delete(`/qa/session/${kbId}/${sessionId}`)
}
