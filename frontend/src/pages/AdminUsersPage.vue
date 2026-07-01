<template>
  <div class="page-container">
    <div class="page-header">
      <a-space>
        <a-button @click="$router.push('/')">← 返回</a-button>
        <h1>用户管理</h1>
      </a-space>
    </div>

    <a-table
      :dataSource="users"
      :columns="columns"
      rowKey="id"
      size="middle"
      :pagination="{ pageSize: 50 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'role'">
          <a-tag :color="record.role === 'admin' ? 'gold' : 'default'">{{ record.role }}</a-tag>
        </template>
        <template v-if="column.key === 'tags'">
          <template v-if="record.tags">
            <a-tag v-for="t in record.tags.split(',').filter(Boolean)" :key="t" color="blue" size="small">{{ t }}</a-tag>
          </template>
          <span v-else style="color: #bbb;">无标签</span>
        </template>
        <template v-if="column.key === 'is_active'">
          <a-tag :color="record.is_active ? 'success' : 'error'">{{ record.is_active ? '启用' : '禁用' }}</a-tag>
        </template>
        <template v-if="column.key === 'actions'">
          <a-button type="link" size="small" @click="openEdit(record)">编辑</a-button>
          <a-popconfirm
            title="确定删除此用户？"
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

    <!-- 编辑弹窗 -->
    <a-modal
      v-model:open="editVisible"
      title="编辑用户"
      @ok="handleSave"
      okText="保存"
      cancelText="取消"
    >
      <a-form layout="vertical" style="margin-top: 16px;">
        <a-form-item label="用户名">
          <a-input :value="editForm.username" disabled />
        </a-form-item>
        <a-form-item label="角色">
          <a-select v-model:value="editForm.role" style="width: 100%;">
            <a-select-option value="user">普通用户</a-select-option>
            <a-select-option value="admin">管理员</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="标签">
          <a-select
            v-model:value="editForm.tagsList"
            mode="multiple"
            placeholder="选择权限标签"
            style="width: 100%;"
            :options="tagOptions"
          />
        </a-form-item>
        <a-form-item label="状态">
          <a-select v-model:value="editForm.is_active" style="width: 100%;">
            <a-select-option :value="1">启用</a-select-option>
            <a-select-option :value="0">禁用</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { listUsers, updateUser, deleteUser } from '../api/admin'
import { listTags } from '../api/tags'
import type { UserInfo, Tag } from '../types'

const users = ref<UserInfo[]>([])
const allTags = ref<Tag[]>([])
const tagOptions = ref<{ label: string; value: string }[]>([])
const editVisible = ref(false)
const editForm = ref({ id: '', username: '', role: 'user', tagsList: [] as string[], is_active: 1 })

const columns = [
  { title: '用户名', dataIndex: 'username', key: 'username' },
  { title: '角色', key: 'role', width: 80 },
  { title: '标签', key: 'tags', width: 200 },
  { title: '状态', key: 'is_active', width: 80 },
  { title: '操作', key: 'actions', width: 140 },
]

onMounted(async () => {
  await refresh()
  allTags.value = await listTags()
  tagOptions.value = allTags.value.map(t => ({ label: t.name, value: t.name }))
})

async function refresh() {
  users.value = await listUsers()
}

function openEdit(user: UserInfo) {
  editForm.value = {
    id: user.id,
    username: user.username,
    role: user.role,
    tagsList: user.tags ? user.tags.split(',').filter(Boolean) : [],
    is_active: user.is_active,
  }
  editVisible.value = true
}

async function handleSave() {
  try {
    await updateUser(editForm.value.id, {
      role: editForm.value.role,
      tags: editForm.value.tagsList.join(',') || '',
      is_active: editForm.value.is_active,
    })
    message.success('已保存')
    editVisible.value = false
    await refresh()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  }
}

async function handleDelete(id: string) {
  try {
    await deleteUser(id)
    message.success('已删除')
    await refresh()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '删除失败')
  }
}
</script>
