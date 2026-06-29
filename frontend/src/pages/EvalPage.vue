<template>
  <div class="page-container">
    <div class="page-header">
      <a-space>
        <a-button @click="$router.back()">← 返回</a-button>
        <h1>{{ kbName }} · 评估报告</h1>
      </a-space>
      <a-button type="primary" @click="handleRunEval" :loading="running" :disabled="running">
        <template #icon><ThunderboltOutlined /></template>
        {{ running ? '评估中...' : '运行 RAGAS 评估' }}
      </a-button>
    </div>

    <!-- 评估进行中提示 -->
    <a-alert
      v-if="running"
      type="info"
      show-icon
      style="margin-bottom: 24px;"
    >
      <template #message>
        <strong>评估正在进行中</strong>
      </template>
      <template #description>
        系统正在调用 LLM 对问答数据进行质量评估，包含忠实度、答案相关性、上下文精确度三项指标。
        根据数据量不同，评估可能需要 <strong>1-3 分钟</strong>，请耐心等待，不要关闭或刷新页面。
      </template>
    </a-alert>

    <a-spin :spinning="loading" tip="加载评估报告...">
      <!-- 评估汇总统计 -->
      <a-row v-if="report?.metrics?.length" :gutter="[16, 16]" style="margin-bottom: 24px;">
        <a-col v-for="m in report.metrics" :key="m.name" :xs="24" :sm="8" :lg="6">
          <a-card :title="metricLabels[m.name] || m.name" size="small" :bordered="false">
            <a-statistic
              :value="(m.score * 100).toFixed(1)"
              suffix="%"
              :value-style="{
                fontSize: '28px',
                fontWeight: 600,
                color: m.score >= 0.7 ? '#52c41a' : m.score >= 0.5 ? '#faad14' : '#ff4d4f'
              }"
            />
            <div style="font-size: 12px; color: #8c8c8c; margin-top: 8px; line-height: 1.5;">
              {{ m.description }}
            </div>
          </a-card>
        </a-col>
      </a-row>

      <!-- 样本统计 -->
      <a-descriptions v-if="report" bordered size="small" :column="2" style="margin-top: 16px;">
        <a-descriptions-item label="评估样本数">
          <strong>{{ report.sample_count }}</strong>
        </a-descriptions-item>
        <a-descriptions-item label="本次新增评估">
          <a-tag v-if="report.new_evaluated > 0" color="blue">{{ report.new_evaluated }} 条</a-tag>
          <span v-else style="color: #8c8c8c;">无新增（全部已有评分）</span>
        </a-descriptions-item>
        <a-descriptions-item label="忠实度 (Faithfulness)">
          答案断言是否可追溯到检索文档
        </a-descriptions-item>
        <a-descriptions-item label="答案相关性 (Answer Relevancy)">
          答案是否直接切题、覆盖问题要点
        </a-descriptions-item>
        <a-descriptions-item label="上下文精确度 (Context Precision)" :span="2">
          检索文档片段的相关性及排名质量（位置加权）
        </a-descriptions-item>
      </a-descriptions>

      <a-divider />

      <!-- 空态 -->
      <a-empty
        v-if="!report || !report.metrics?.length"
        :description="running ? '评估进行中，请稍候...' : '暂无评估报告，点击上方按钮运行评估'"
        style="margin-top: 40px;"
      >
        <template v-if="!running" #children>
          <a-button type="primary" @click="handleRunEval">立即评估</a-button>
        </template>
      </a-empty>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { ThunderboltOutlined } from '@ant-design/icons-vue'
import { getKB } from '../api/kb'
import { runEval, getEvalReport } from '../api/eval'
import type { EvalReport } from '../types'

const route = useRoute()
const kbId = route.params.kbId as string
const kbName = ref('')
const report = ref<EvalReport | null>(null)
const loading = ref(false)
const running = ref(false)

const metricLabels: Record<string, string> = {
  faithfulness: '忠实度',
  answer_relevancy: '答案相关性',
  context_precision: '上下文精确度',
  context_recall: '上下文召回率',
}

onMounted(async () => {
  try {
    const kb = await getKB(kbId)
    kbName.value = kb.name
  } catch {
    kbName.value = kbId
  }

  try {
    loading.value = true
    report.value = await getEvalReport(kbId)
  } catch {
    /* 暂无报告 */
  } finally {
    loading.value = false
  }
})

async function handleRunEval() {
  running.value = true
  try {
    report.value = await runEval(kbId)
    if (report.value?.metrics?.length) {
      message.success(`评估完成，共评估 ${report.value.sample_count} 个样本`)
    } else {
      message.info('评估完成，但暂无评分数据')
    }
  } catch (e: any) {
    message.error(`评估失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
:deep(.ant-statistic-content) {
  font-family: 'SF Mono', 'Consolas', 'Menlo', monospace;
}

:deep(.ant-descriptions-item-label) {
  font-weight: 500;
  color: #666;
}
</style>
