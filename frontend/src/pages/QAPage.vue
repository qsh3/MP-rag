<template>
  <div style="display: flex; height: calc(100vh - 48px);">
    <!-- 左侧：对话历史 -->
    <div style="width: 240px; border-right: 1px solid #e8e8e8; display: flex; flex-direction: column; background: #fafafa;">
      <div style="padding: 12px;">
        <a-button type="primary" block @click="newChat">
          <template #icon><PlusOutlined /></template>
          新对话
        </a-button>
      </div>
      <div style="flex: 1; overflow-y: auto; padding: 0 8px 8px;">
        <div
          v-if="sessions.length === 0"
          style="text-align: center; color: #bfbfbf; padding: 32px 16px; font-size: 13px;"
        >
          暂无对话历史
        </div>
        <div
          v-for="sid in sessions"
          :key="sid"
          :class="['session-item', { active: sid === currentSessionId }]"
          @click="loadSession(sid)"
        >
          <div style="overflow: hidden; flex: 1;">
            <div class="session-title">{{ sessionTitles[sid] || '新对话' }}</div>
            <div class="session-time">{{ sessionTimes[sid] }}</div>
          </div>
          <a-popconfirm
            title="删除此对话？"
            @confirm.stop="handleDeleteSession(sid)"
            ok-text="删除"
            cancel-text="取消"
            placement="right"
          >
            <DeleteOutlined class="session-delete" @click.stop />
          </a-popconfirm>
        </div>
      </div>
    </div>

    <!-- 右侧：对话区 -->
    <div style="flex: 1; display: flex; flex-direction: column; min-width: 0; background: #f5f5f5;">
      <!-- 顶部 -->
      <div style="padding: 12px 20px; background: #fff; border-bottom: 1px solid #e8e8e8; display: flex; align-items: center;">
        <a-space>
          <a-button type="text" @click="$router.back()">
            <template #icon><ArrowLeftOutlined /></template>
          </a-button>
          <span style="font-size: 15px; font-weight: 600;">{{ kbName }} · 智能问答</span>
        </a-space>
      </div>

      <!-- 消息列表 -->
      <div ref="chatContainer" class="chat-area">
        <div v-for="msg in messages" :key="msg.id" style="display: flex; flex-direction: column;">
          <!-- 用户消息 -->
          <div v-if="msg.role === 'user'" style="display: flex; justify-content: flex-end; margin-bottom: 12px;">
            <div class="chat-bubble-user">{{ msg.content }}</div>
          </div>
          <!-- AI 回复 -->
          <div v-else class="chat-bubble-ai">
            <div class="ai-content">{{ assistantContent[msg.id] || '思考中...' }}</div>
            <!-- 来源引用 -->
            <div v-if="msg.sources?.length" style="margin-top: 12px;">
              <a-divider style="margin: 8px 0; font-size: 12px; color: #8c8c8c;">
                参考来源
              </a-divider>
              <div
                v-for="(src, idx) in msg.sources"
                :key="idx"
                class="source-item"
              >
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <strong style="font-size: 12px;">{{ src.doc_name }}</strong>
                  <a-tag size="small" color="blue">相关度 {{ (src.score * 100).toFixed(0) }}%</a-tag>
                </div>
                <p class="source-text">{{ src.chunk_text?.substring(0, 200) }}{{ src.chunk_text?.length > 200 ? '...' : '' }}</p>
              </div>
            </div>
          </div>
        </div>
        <a-empty v-if="messages.length === 0" description="输入问题开始对话" style="margin-top: 80px;" />
      </div>

      <!-- 输入区 -->
      <div class="input-area">
        <a-textarea
          v-model:value="question"
          placeholder="输入你的问题，按 Enter 发送，Shift+Enter 换行"
          :rows="2"
          :disabled="asking"
          @pressEnter="(e: KeyboardEvent) => { if (!e.shiftKey) { e.preventDefault(); handleAsk() } }"
        />
        <div class="input-toolbar">
          <a-space>
            <span style="font-size: 12px; color: #8c8c8c;">检索数量:</span>
            <a-input-number v-model:value="topK" :min="1" :max="20" size="small" style="width: 64px;" />
          </a-space>
          <a-button type="primary" @click="handleAsk" :loading="asking" :disabled="!question.trim()">
            发送
          </a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined, DeleteOutlined, ArrowLeftOutlined } from '@ant-design/icons-vue'
import { getKB } from '../api/kb'
import { askStream, getHistory, deleteSession, onSSE, offSSE } from '../api/qa'
import type { ChatMessage, SourceDoc } from '../types'

const route = useRoute()
const kbId = route.params.kbId as string
const kbName = ref('')
const question = ref('')
const topK = ref(5)
const asking = ref(false)
const messages = ref<ChatMessage[]>([])
const assistantContent = reactive<Record<string, string>>({})
const chatContainer = ref<HTMLElement | null>(null)
const currentSessionId = ref('')
const sessions = ref<string[]>([])
const sessionTitles = reactive<Record<string, string>>({})
const sessionTimes = reactive<Record<string, string>>({})

let currentMsgId = ''

onMounted(async () => {
  try {
    const kb = await getKB(kbId)
    kbName.value = kb.name
  } catch { kbName.value = kbId }

  await loadSessions()

  onSSE('token', (data) => {
    if (currentMsgId) {
      assistantContent[currentMsgId] = (assistantContent[currentMsgId] || '') + data
      scrollToBottom()
    }
  })

  onSSE('sources', (data) => {
    try {
      const sources = JSON.parse(data) as SourceDoc[]
      const msg = messages.value.find(m => m.id === currentMsgId)
      if (msg) msg.sources = sources
    } catch {}
  })

  onSSE('done', (data) => {
    asking.value = false
    question.value = ''
    currentMsgId = ''
    try {
      const d = JSON.parse(data)
      if (d.session_id && !currentSessionId.value) {
        currentSessionId.value = d.session_id
        loadSessions()
      }
    } catch {}
  })

  onSSE('error', (data) => {
    message.error(`回答出错: ${data}`)
    asking.value = false
    question.value = ''
    if (currentMsgId) {
      assistantContent[currentMsgId] = `[错误] ${data}`
      currentMsgId = ''
    }
  })
})

async function loadSessions() {
  try {
    const result = await getHistory(kbId)
    const seen = new Set<string>()
    sessions.value = []
    for (const item of result.items) {
      const sid = item.session_id || ''
      if (!sid || seen.has(sid)) continue
      seen.add(sid)
      sessions.value.push(sid)
      if (!sessionTitles[sid]) {
        sessionTitles[sid] = item.question?.substring(0, 30) || '新对话'
        sessionTimes[sid] = item.created_at?.substring(0, 16) || ''
      }
    }
  } catch {}
}

async function loadSession(sid: string) {
  currentSessionId.value = sid
  messages.value = []
  Object.keys(assistantContent).forEach(k => delete assistantContent[k])

  try {
    const result = await getHistory(kbId)
    const items = result.items.filter((i: any) => i.session_id === sid).reverse()
    for (const item of items) {
      const uId = item.id + '_u'
      messages.value.push({ id: uId, role: 'user', content: item.question, sources: [], timestamp: item.created_at })
      assistantContent[item.id] = item.answer
      messages.value.push({ id: item.id, role: 'assistant', content: item.answer, sources: item.sources || [], timestamp: item.created_at })
    }
    await nextTick()
    scrollToBottom()
  } catch {}
}

async function handleDeleteSession(sid: string) {
  try {
    await deleteSession(kbId, sid)
    message.success('对话已删除')
    if (currentSessionId.value === sid) {
      newChat()
    }
    await loadSessions()
  } catch {
    message.error('删除失败')
  }
}

function newChat() {
  currentSessionId.value = ''
  messages.value = []
  Object.keys(assistantContent).forEach(k => delete assistantContent[k])
  question.value = ''
}

async function handleAsk() {
  const q = question.value.trim()
  if (!q || asking.value) return

  const msgId = Date.now().toString()
  currentMsgId = msgId

  messages.value.push({ id: msgId + '_u', role: 'user', content: q, sources: [], timestamp: new Date().toISOString() })
  messages.value.push({ id: msgId, role: 'assistant', content: '', sources: [], timestamp: new Date().toISOString() })

  question.value = ''
  asking.value = true
  await nextTick()
  scrollToBottom()

  try {
    askStream(kbId, q, topK.value, currentSessionId.value || undefined)
  } catch (e: any) {
    message.error('请求失败')
    asking.value = false
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}
</script>

<style scoped>
/* ── 会话列表 ── */
.session-item {
  padding: 10px 12px;
  margin-bottom: 4px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: background 0.2s;
}

.session-item:hover {
  background: #e6f4ff;
}

.session-item.active {
  background: #bae0ff;
}

.session-title {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #262626;
}

.session-time {
  font-size: 11px;
  color: #8c8c8c;
  margin-top: 2px;
}

.session-delete {
  color: #bfbfbf;
  font-size: 12px;
  flex-shrink: 0;
  margin-left: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.session-item:hover .session-delete {
  opacity: 1;
}

/* ── 聊天区 ── */
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.chat-bubble-user {
  max-width: 70%;
  background: #1677ff;
  color: #fff;
  padding: 10px 16px;
  border-radius: 12px 4px 12px 12px;
  line-height: 1.6;
  font-size: 14px;
}

.chat-bubble-ai {
  margin-bottom: 20px;
  padding: 14px 18px;
  background: #fff;
  border-radius: 4px 12px 12px 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  max-width: 90%;
}

.ai-content {
  white-space: pre-wrap;
  line-height: 1.8;
  font-size: 14px;
  color: #262626;
}

/* ── 来源引用 ── */
.source-item {
  font-size: 12px;
  color: #595959;
  padding: 8px 10px;
  background: #fafafa;
  border-radius: 4px;
  margin: 6px 0;
  border-left: 3px solid #1677ff;
}

.source-text {
  margin: 4px 0 0;
  color: #8c8c8c;
  font-size: 12px;
  line-height: 1.5;
}

/* ── 输入区 ── */
.input-area {
  padding: 12px 20px;
  background: #fff;
  border-top: 1px solid #e8e8e8;
}

.input-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}
</style>
