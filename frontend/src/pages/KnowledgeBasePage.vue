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
        <a-button v-if="authStore.isAdmin" @click="$router.push(`/eval/${kbId}`)">
          <template #icon><FundOutlined /></template>
          评估报告
        </a-button>
        <a-select
          v-model:value="uploadTagsList"
          mode="multiple"
          placeholder="文档标签（留空继承知识库）"
          style="width: 240px;"
          :options="tagOptions"
        />
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
          <template v-if="column.key === 'tags'">
            <template v-if="record.tags">
              <a-tag color="orange" v-for="t in record.tags.split(',').filter(Boolean)" :key="t" size="small">{{ t }}</a-tag>
            </template>
            <span v-else style="color: #bbb;">无标签</span>
            <a-button v-if="authStore.isAdmin" type="link" size="small" @click="openTagEdit(record)" style="padding: 0; margin-left: 4px;">
              <EditOutlined style="font-size: 12px;" />
            </a-button>
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

    <!-- 文档标签编辑弹窗 -->
    <a-modal
      v-model:open="tagEditVisible"
      title="编辑文档标签"
      @ok="handleTagSave"
      okText="保存"
      cancelText="取消"
    >
      <a-form layout="vertical" style="margin-top: 16px;">
        <a-form-item label="文档">
          <a-input :value="tagEditDoc?.filename" disabled />
        </a-form-item>
        <a-form-item label="标签">
          <a-select
            v-model:value="tagEditList"
            mode="multiple"
            placeholder="选择标签"
            style="width: 100%;"
            :options="tagOptions"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { MessageOutlined, FundOutlined, UploadOutlined, SyncOutlined, EditOutlined } from '@ant-design/icons-vue'
import type { Document } from '../types'
import { getKB, type KnowledgeBase } from '../api/kb'
import { uploadDocs, listDocs, deleteDoc } from '../api/document'
import { listTags } from '../api/tags'
import { useAuthStore } from '../stores/authStore'
import api from '../api/client'

const route = useRoute()
const authStore = useAuthStore()
const kbId = route.params.id as string
const kb = ref<KnowledgeBase | null>(null)
const docs = ref<Document[]>([])
const uploading = ref(false)
const uploadTagsList = ref<string[]>([])
const tagOptions = ref<{ label: string; value: string }[]>([])

// 标签编辑
const tagEditVisible = ref(false)
const tagEditDoc = ref<Document | null>(null)
const tagEditList = ref<string[]>([])

const columns = [
  { title: '文件名', dataIndex: 'filename', key: 'name', ellipsis: true },
  { title: '类型', dataIndex: 'file_type', key: 'type', width: 80 },
  { title: '大小', key: 'size', width: 90 },
  { title: '标签', dataIndex: 'tags', key: 'tags', width: 140 },
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
  try {
    const tags = await listTags()
    tagOptions.value = tags.map(t => ({ label: t.name, value: t.name }))
  } catch { /* 加载失败不影响 */ }
})

async function refreshDocs() {
  const res = await listDocs(kbId)
  docs.value = res.items
}

async function handleUpload(file: File) {
  uploading.value = true
  try {
    const tags = uploadTagsList.value.join(',') || undefined
    await uploadDocs(kbId, [file], tags)
    message.success(`${file.name} 上传成功，正在解析中...`)
    uploadTagsList.value = []
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

function openTagEdit(doc: Document) {
  tagEditDoc.value = doc
  tagEditList.value = doc.tags ? doc.tags.split(',').filter(Boolean) : []
  tagEditVisible.value = true
}

async function handleTagSave() {
  if (!tagEditDoc.value) return
  try {
    const tags = tagEditList.value.join(',') || ''
    await api.put(`/kb/${kbId}/docs/${tagEditDoc.value.id}`, { tags })
    message.success('标签已更新')
    tagEditVisible.value = false
    await refreshDocs()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '更新失败')
  }
}
</script>

<style scoped>
:deep(.ant-table) {
  font-size: 13px;
}
</style>
