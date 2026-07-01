<template>
  <div class="page-container">
    <div class="page-header">
      <a-space>
        <a-button @click="$router.push('/')">← 返回</a-button>
        <h1>标签管理</h1>
      </a-space>
    </div>

    <a-space style="margin-bottom: 16px;">
      <a-input
        v-model:value="newTagName"
        placeholder="输入新标签名"
        style="width: 200px;"
        :maxlength="50"
        @pressEnter="handleCreate"
      />
      <a-button type="primary" @click="handleCreate" :loading="creating">
        <template #icon><PlusOutlined /></template>
        新建标签
      </a-button>
    </a-space>

    <a-table
      :dataSource="tags"
      :columns="columns"
      rowKey="id"
      size="middle"
      :pagination="{ pageSize: 50 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'actions'">
          <a-popconfirm
            title="确定删除此标签？删除后不会影响已有文档的标签。"
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

    <a-empty v-if="!loading && tags.length === 0" description="暂无标签，请创建" style="margin-top: 60px;" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { listTags, createTag, deleteTag } from '../api/tags'
import type { Tag } from '../types'

const tags = ref<Tag[]>([])
const newTagName = ref('')
const creating = ref(false)
const loading = ref(false)

const columns = [
  { title: '标签名', dataIndex: 'name', key: 'name' },
  { title: '操作', key: 'actions', width: 100 },
]

onMounted(async () => {
  loading.value = true
  try {
    tags.value = await listTags()
  } finally {
    loading.value = false
  }
})

async function handleCreate() {
  const name = newTagName.value.trim()
  if (!name) { message.warning('请输入标签名'); return }
  creating.value = true
  try {
    await createTag(name)
    message.success(`标签「${name}」已创建`)
    newTagName.value = ''
    tags.value = await listTags()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '创建失败')
  } finally {
    creating.value = false
  }
}

async function handleDelete(id: string) {
  await deleteTag(id)
  message.success('已删除')
  tags.value = await listTags()
}
</script>
