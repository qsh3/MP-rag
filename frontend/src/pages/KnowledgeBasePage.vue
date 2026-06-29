<template>
  <div class="page-container">
    <div class="page-header">
      <a-space>
        <a-button @click="$router.back()">← 返回</a-button>
        <h1>{{ kb?.name || '加载中...' }}</h1>
        <a-tag color="processing">{{ kb?.document_count || 0 }} 个文档</a-tag>
      </a-space>
      <a-space>
        <a-button @click="$router.push(`/qa/${kbId}`)">
          <template #icon><MessageOutlined /></template>
          智能问答
        </a-button>
        <a-button @click="$router.push(`/eval/${kbId}`)">
          <template #icon><FundOutlined /></template>
          评估报告
        </a-button>
        <a-upload
          multiple
          :show-upload-list="false"
          :before-upload="handleUpload"
          :custom-request="() => {}"
        >
          <a-button type="primary">
            <template #icon><UploadOutlined /></template>
            上传文档
          </a-button>
        </a-upload>
      </a-space>
    </div>

    <a-spin :spinning="uploading" tip="正在上传并解析文档，请稍候...">
      <a-table
        :dataSource="docs"
        :columns="columns"
        rowKey="id"
        size="middle"
        :bordered="false"
        :pagination="{ pageSize: 20, showTotal: (t: number) => `共 ${t} 个文档` }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'size'">
            {{ formatSize(record.file_size) }}
          </template>
          <template v-if="column.key === 'status'">
            <a-tag v-if="record.status === 'ready'" color="success">就绪</a-tag>
            <a-tag v-else-if="record.status === 'processing'" color="processing">
              <SyncOutlined :spin="true" style="margin-right: 2px;" />
              处理中
            </a-tag>
            <a-tag v-else-if="record.status === 'error'" color="error">失败</a-tag>
            <a-tag v-else>{{ record.status }}</a-tag>
          </template>
          <template v-if="column.key === 'actions'">
            <a-popconfirm
              title="确定删除此文档？"
              ok-text="确认删除"
              ok-type="danger"
              cancel-text="取消"
              @confirm="handleDelete(record.id)"
            >
              <a-button type="link" danger size="small">删除</a-button>
            </a-popconfirm>
          </template>
        </template>
      </a-table>

      <a-empty
        v-if="!uploading && docs.length === 0"
        description="暂无文档，请上传文档以构建知识库"
        style="margin-top: 60px;"
      />
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { MessageOutlined, FundOutlined, UploadOutlined, SyncOutlined } from '@ant-design/icons-vue'
import type { Document } from '../types'
import { getKB, type KnowledgeBase } from '../api/kb'
import { uploadDocs, listDocs, deleteDoc } from '../api/document'

const route = useRoute()
const kbId = route.params.id as string
const kb = ref<KnowledgeBase | null>(null)
const docs = ref<Document[]>([])
const uploading = ref(false)

const columns = [
  { title: '文件名', dataIndex: 'filename', key: 'name', ellipsis: true },
  { title: '类型', dataIndex: 'file_type', key: 'type', width: 80 },
  { title: '大小', key: 'size', width: 90 },
  { title: '分块数', dataIndex: 'chunk_count', key: 'chunks', width: 80, align: 'center' },
  { title: '状态', key: 'status', width: 110 },
  { title: '操作', key: 'actions', width: 80 },
]

function formatSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

onMounted(async () => {
  kb.value = await getKB(kbId)
  await refreshDocs()
})

async function refreshDocs() {
  const res = await listDocs(kbId)
  docs.value = res.items
}

async function handleUpload(file: File) {
  uploading.value = true
  try {
    await uploadDocs(kbId, [file])
    message.success(`${file.name} 上传成功，正在解析中...`)
    await refreshDocs()
    kb.value = await getKB(kbId)
  } catch (e: any) {
    message.error(`上传失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    uploading.value = false
  }
  return false
}

async function handleDelete(docId: string) {
  await deleteDoc(kbId, docId)
  message.success('文档已删除')
  await refreshDocs()
  kb.value = await getKB(kbId)
}
</script>

<style scoped>
:deep(.ant-table) {
  font-size: 13px;
}
</style>
