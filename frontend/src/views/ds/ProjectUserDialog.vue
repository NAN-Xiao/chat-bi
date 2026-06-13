<template>
  <el-dialog
    v-model="visible"
    :title="$t('datasource.project_authorization')"
    modal-class="project-user-dialog"
    width="840"
  >
    <p class="lighter project-name">
      {{ $t('datasource.project_authorization_desc', { msg: project?.name || '' }) }}
    </p>
    <div v-loading="loading" class="flex border project-user-picker">
      <div class="p-16 border-r">
        <el-input
          v-model="search"
          :validate-event="false"
          :placeholder="$t('datasource.search')"
          style="width: 364px; margin-left: 16px"
          clearable
        >
          <template #prefix>
            <el-icon>
              <Search></Search>
            </el-icon>
          </template>
        </el-input>
        <div class="mt-8 max-height-list">
          <el-checkbox
            v-if="usersWithKeywords.length"
            v-model="checkAll"
            class="mb-8"
            style="margin-left: 16px"
            :indeterminate="isIndeterminate"
            @change="handleCheckAllChange"
          >
            {{ $t('datasource.select_all') }}
          </el-checkbox>
          <el-checkbox-group
            v-model="checkedUsers"
            class="checkbox-group-block"
            @change="handleCheckedUsersChange"
          >
            <el-checkbox
              v-for="user in usersWithKeywords"
              :key="user.id"
              :label="user.name"
              :value="user"
              class="hover-bg"
            >
              <div class="flex">
                <el-icon size="28">
                  <avatar_personal></avatar_personal>
                </el-icon>
                <span class="ml-4 ellipsis" style="max-width: 40%" :title="user.name">
                  {{ user.name }}
                </span>
                <span class="account ellipsis" style="max-width: 40%" :title="user.account">
                  ({{ user.account }})
                </span>
              </div>
            </el-checkbox>
          </el-checkbox-group>
        </div>
      </div>
      <div class="p-16 w-full">
        <div class="flex-between mb-16" style="margin: 0 16px">
          <span class="lighter">
            {{ $t('workspace.selected_2_people', { msg: selectedUsers.length }) }}
          </span>

          <el-button text @click="clearAll">
            {{ $t('workspace.clear') }}
          </el-button>
        </div>
        <div
          v-for="user in selectedUsers"
          :key="user.id"
          style="margin: 0 16px; position: relative"
          class="flex-between align-center hover-bg_select"
        >
          <div
            :title="`${user.name}(${user.account})`"
            class="flex align-center ellipsis"
            style="width: 100%"
          >
            <el-icon size="28">
              <avatar_personal></avatar_personal>
            </el-icon>
            <span class="ml-4 lighter ellipsis" style="max-width: 40%" :title="user.name">
              {{ user.name }}
            </span>
            <span class="account ellipsis" style="max-width: 40%" :title="user.account">
              ({{ user.account }})
            </span>
          </div>
          <el-button class="close-btn" text>
            <el-icon size="16" @click="removeUser(user)"><Close /></el-icon>
          </el-button>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button secondary @click="visible = false">
        {{ $t('common.cancel') }}
      </el-button>
      <el-button type="primary" :loading="saving" @click="handleConfirm">
        {{ $t('common.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus-secondary'
import type { CheckboxValueType } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'
import { datasourceApi } from '@/api/datasource'
import { userApi } from '@/api/user'
import avatar_personal from '@/assets/svg/avatar_personal.svg'
import Close from '@/assets/svg/icon_close_outlined_w.svg'
import Search from '@/assets/svg/icon_search-outline_outlined.svg'

const { t } = useI18n()
const visible = ref(false)
const loading = ref(false)
const saving = ref(false)
const search = ref('')
const project = ref<any>(null)
const users = ref<any[]>([])
const selectedUsers = ref<any[]>([])
const checkedUsers = ref<any[]>([])
const checkAll = ref(false)
const isIndeterminate = ref(false)

const usersWithKeywords = computed(() => {
  const keyword = search.value.toLowerCase()
  if (!keyword) return users.value
  return users.value.filter((user: any) =>
    [user.name, user.account, user.email].some((value: string) =>
      String(value || '').toLowerCase().includes(keyword)
    )
  )
})

const syncCheckedState = () => {
  const selectedIds = new Set(selectedUsers.value.map((user: any) => user.id))
  checkedUsers.value = usersWithKeywords.value.filter((user: any) => selectedIds.has(user.id))
  const checkedCount = checkedUsers.value.length
  checkAll.value = usersWithKeywords.value.length > 0 && checkedCount === usersWithKeywords.value.length
  isIndeterminate.value = checkedCount > 0 && checkedCount < usersWithKeywords.value.length
}

watch(search, syncCheckedState)

const handleCheckAllChange = (val: CheckboxValueType) => {
  const visibleIds = new Set(usersWithKeywords.value.map((user: any) => user.id))
  if (val) {
    const selectedMap = new Map(selectedUsers.value.map((user: any) => [user.id, user]))
    usersWithKeywords.value.forEach((user: any) => selectedMap.set(user.id, user))
    selectedUsers.value = Array.from(selectedMap.values())
  } else {
    selectedUsers.value = selectedUsers.value.filter((user: any) => !visibleIds.has(user.id))
  }
  syncCheckedState()
}

const handleCheckedUsersChange = (value: CheckboxValueType[]) => {
  const visibleIds = new Set(usersWithKeywords.value.map((user: any) => user.id))
  const selectedMap = new Map(
    selectedUsers.value
      .filter((user: any) => !visibleIds.has(user.id))
      .map((user: any) => [user.id, user])
  )
  ;(value as any[]).forEach((user: any) => selectedMap.set(user.id, user))
  selectedUsers.value = Array.from(selectedMap.values())
  syncCheckedState()
}

const open = async (row: any) => {
  project.value = row
  visible.value = true
  loading.value = true
  search.value = ''
  checkedUsers.value = []
  selectedUsers.value = []
  checkAll.value = false
  isIndeterminate.value = false
  try {
    const [userPage, projectUsers] = await Promise.all([
      userApi.pager('', 1, 1000),
      datasourceApi.users(row.id),
    ])
    users.value = (userPage?.items || []).filter((user: any) => Number(user.id) !== 1)
    const authorizedIds = new Set((projectUsers?.user_ids || []).map((id: any) => Number(id)))
    selectedUsers.value = users.value.filter((user: any) => authorizedIds.has(Number(user.id)))
    syncCheckedState()
  } finally {
    loading.value = false
  }
}

const removeUser = (user: any) => {
  selectedUsers.value = selectedUsers.value.filter((item: any) => item.id !== user.id)
  syncCheckedState()
}

const clearAll = () => {
  selectedUsers.value = []
  syncCheckedState()
}

const emits = defineEmits(['refresh'])

const handleConfirm = () => {
  if (!project.value?.id) return
  saving.value = true
  datasourceApi
    .updateUsers(project.value.id, {
      user_ids: selectedUsers.value.map((user: any) => Number(user.id)),
    })
    .then(() => {
      ElMessage.success(t('common.save_success'))
      visible.value = false
      emits('refresh')
    })
    .finally(() => {
      saving.value = false
    })
}

defineExpose({
  open,
})
</script>

<style lang="less">
.project-user-dialog {
  .project-name {
    margin-bottom: 12px;
  }

  .project-user-picker {
    height: 428px;
    border-radius: 6px;
  }

  .mb-8 {
    margin-bottom: 8px;
  }

  .ed-checkbox {
    margin-right: 0;
    position: relative;
  }

  .hover-bg,
  .hover-bg_select {
    &:hover {
      &::after {
        content: '';
        height: 44px;
        width: calc(100% + 34px);
        background: #1f23291a;
        position: absolute;
        border-radius: 6px;
        top: 50%;
        transform: translateY(-50%);
        left: -8px;
        z-index: 1;
      }
    }
  }

  .hover-bg_select {
    &:hover {
      &::after {
        width: calc(100% + 16px);
      }
    }
  }

  .p-16 {
    padding: 16px 0;
  }

  .lighter {
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
  }

  .checkbox-group-block {
    margin: 0 16px;

    .ed-checkbox,
    .ed-checkbox__label,
    .flex {
      width: 96%;
      height: 44px;
    }

    .flex {
      align-items: center;

      .account {
        color: #8f959e;
      }
    }
  }

  .close-btn {
    position: relative;
    z-index: 10;
    height: 24px;
    line-height: 24px;

    &:hover,
    &:active,
    &:focus {
      background: #1f23291a !important;
    }
  }

  .border {
    border: 1px solid #dee0e3;
  }

  .w-full {
    height: 100%;
    width: 50%;
    overflow-y: auto;

    .flex-between {
      height: 44px;
    }
  }

  .mt-8 {
    margin-top: 8px;
  }

  .max-height-list {
    max-height: calc(100% - 24px);
    overflow-y: auto;
  }

  .align-center {
    align-items: center;
  }

  .flex-between {
    display: flex;
    justify-content: space-between;
  }

  .ml-4 {
    margin-left: 4px;
  }

  .flex {
    display: flex;
  }

  .border-r {
    border-right: 1px solid #dee0e3;
    width: 50%;
    overflow: hidden;
  }
}
</style>
