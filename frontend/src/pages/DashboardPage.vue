<template>
  <div class="page-container">
    <div class="page-header">
      <h1>知识库管理</h1>
      <a-button type="primary" @click="showCreate = true">
        <template #icon><PlusOutlined /></template>
        新建知识库
      </a-button>
    </div>

    <a-spin :spinning="store.loading">
      <a-row v-if="store.knowledgeBases.length" :gutter="[16, 16]">
        <a-col v-for="kb in store.knowledgeBases" :key="kb.id" :xs="24" :sm="12" :lg="8">
          <a-card class="dashboard-card" :title="kb.name" :bordered="false" hoverable @click="$router.push(`/kb/${kb.id}`)">
            <p style="color: #8c8c8c; min-height: 36px; font-size: 13px; line-height: 1.6;">
              {{ kb.description || '暂无描述' }}
            </p>

            <a-space style="margin-bottom: 12px;">
              <a-tag color="processing">{{ kb.document_count }} 个文档</a-tag>
              <a-tag color="success">{{ kb.chunk_count }} 个分块</a-tag>
            </a-space>

            <div style="display: flex; gap: 8px; border-top: 1px solid #f0f0f0; padding-top: 12px;">
              <a-button type="primary" size="small" block @click.stop="$router.push(`/qa/${kb.id}`)">
                <template #icon><MessageOutlined /></template>
                问答
              </a-button>
              <a-button v-if="authStore.isAdmin" size="small" block @click.stop="$router.push(`/eval/${kb.id}`)">
                <template #icon><FundOutlined /></template>
                评估
              </a-button>
              <a-button v-if="authStore.isAdmin" size="small" block @click.stop="openEdit(kb)">
                <template #icon><EditOutlined /></template>
                编辑
              </a-button>
              <a-button v-if="authStore.isAdmin" size="small" danger block @click.stop="handleDelete(kb)">
                <template #icon><DeleteOutlined /></template>
                删除
              </a-button>
            </div>
          </a-card>
        </a-col>
      </a-row>

      <a-empty
        v-if="!store.loading && store.knowledgeBases.length === 0"
        description="暂无知识库，点击上方按钮创建"
        style="margin-top: 80px;"
      />
    </a-spin>

    <!-- 新建/编辑知识库弹窗 -->
    <a-modal
      v-model:open="showCreate"
      :title="editingKB ? '编辑知识库' : '新建知识库'"
      @ok="handleCreate"
      @cancel="editingKB = null"
      :confirmLoading="creating"
      :okText="editingKB ? '保存' : '确认创建'"
      cancelText="取消"
    >
      <a-form :model="form" layout="vertical" style="margin-top: 16px;">
        <a-form-item label="知识库名称" required>
          <a-input
            v-model:value="form.name"
            placeholder="例如：技术文档库、产品手册"
            :maxlength="50"
            @pressEnter="handleCreate"
          />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea
            v-model:value="form.description"
            placeholder="简要描述知识库的用途和内容范围"
            :rows="3"
            :maxlength="200"
            showCount
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  PlusOutlined, EditOutlined,
  MessageOutlined,
  FundOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { useAppStore } from '../stores/appStore'
import { useAuthStore } from '../stores/authStore'
import { createKB, updateKB, deleteKB } from '../api/kb'
import type { KnowledgeBase } from '../types'

const store = useAppStore()
const authStore = useAuthStore()
const showCreate = ref(false)
const creating = ref(false)
const form = ref({ name: '', description: '' })
const editingKB = ref<KnowledgeBase | null>(null)

onMounted(async () => {
  await store.fetchKBs()
})

async function handleCreate() {
  if (!form.value.name.trim()) {
    message.warning('请输入知识库名称')
    return
  }
  creating.value = true
  try {
    if (editingKB.value) {
      await updateKB(editingKB.value.id, form.value.name.trim(), form.value.description.trim())
      message.success('知识库已更新')
    } else {
      await createKB(form.value.name.trim(), form.value.description.trim())
      message.success('知识库创建成功')
    }
    showCreate.value = false
    editingKB.value = null
    form.value = { name: '', description: '' }
    await store.fetchKBs()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '操作失败')
  } finally {
    creating.value = false
  }
}

function openEdit(kb: KnowledgeBase) {
  editingKB.value = kb
  form.value = { name: kb.name, description: kb.description }
  showCreate.value = true
}

async function handleDelete(kb: KnowledgeBase) {
  if (kb.document_count > 0) {
    message.warning('请先删除知识库中的所有文档，再删除知识库')
    return
  }
  Modal.confirm({
    title: `确认删除「${kb.name}」？`,
    content: '此操作不可恢复，删除后知识库及其配置将永久移除。',
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await deleteKB(kb.id)
        message.success('知识库已删除')
        await store.fetchKBs()
      } catch (e: any) {
        message.error('删除失败')
      }
    },
  })
}
</script>
