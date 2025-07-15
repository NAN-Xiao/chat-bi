<template>
  <el-dialog
    v-model="centerDialogVisible"
    :title="$t('workspace.add_member')"
    modal-class="authorized-workspace"
    width="840"
  >
    <p class="mb-8 lighter">{{ $t('workspace.member_type') }}</p>
    <el-radio-group v-model="listType">
      <el-radio value="0">{{ $t('workspace.ordinary_member') }}</el-radio>
      <el-radio value="1">{{ $t('workspace.administrator') }}</el-radio>
    </el-radio-group>
    <p class="mb-8 lighter mt-16">{{ $t('workspace.select_member') }}</p>
    <div v-loading="loading" class="flex border" style="height: 428px; border-radius: 6px">
      <div class="p-16 border-r">
        <el-input
          v-model="search"
          :validate-event="false"
          :placeholder="$t('datasource.search')"
          style="width: 364px"
          clearable
        >
          <template #prefix>
            <el-icon>
              <Search></Search>
            </el-icon>
          </template>
        </el-input>
        <div class="mt-8">
          <el-checkbox
            v-if="!search"
            v-model="checkAll"
            class="mb-8"
            :indeterminate="isIndeterminate"
            @change="handleCheckAllChange"
          >
            {{ $t('datasource.select_all') }}
          </el-checkbox>
          <el-checkbox-group
            v-model="checkedWorkspace"
            class="checkbox-group-block"
            @change="handleCheckedWorkspaceChange"
          >
            <el-checkbox
              v-for="space in workspaceWithKeywords"
              :key="space.id"
              :label="space.name"
              :value="space"
            >
              <div class="flex">
                <img :src="avatar_personal" width="28px" height="28px" />
                <span class="ml-4"> {{ space.name }}</span>
              </div>
            </el-checkbox>
          </el-checkbox-group>
        </div>
      </div>
      <div class="p-16 w-full">
        <div class="flex-between mb-16">
          <span class="lighter">
            {{ $t('workspace.selected_2_people', { msg: checkedWorkspace.length }) }}
          </span>

          <el-button text @click="clearWorkspaceAll">
            {{ $t('workspace.clear') }}
          </el-button>
        </div>
        <div v-for="ele in checkedWorkspace" :key="ele.name" class="flex-between">
          <div class="flex align-center">
            <img :src="avatar_personal" width="28px" height="28px" />
            <span class="ml-4 lighter">{{ ele.name }}</span>
          </div>
          <el-button text>
            <el-icon :size="18" @click="clearWorkspace(ele)"><Close /></el-icon>
          </el-button>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="centerDialogVisible = false"> {{ $t('common.cancel') }}</el-button>
      <el-button v-if="!checkedWorkspace.length" disabled type="info">{{
        $t('model.add')
      }}</el-button>
      <el-button v-else type="primary" @click="handleConfirm"> {{ $t('model.add') }} </el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, computed } from 'vue'

import avatar_personal from '@/assets/workspace/avatar_personal.png'
import Close from '@/assets/svg/icon_close_outlined.svg'
import Search from '@/assets/svg/icon_search-outline_outlined.svg'
import type { CheckboxValueType } from 'element-plus-secondary'
const checkAll = ref(false)
const isIndeterminate = ref(true)
const checkedWorkspace = ref<any[]>([])
const workspace = ref<any[]>([])
const listType = ref('0')
const search = ref('')
const loading = ref(false)
const centerDialogVisible = ref(false)

const workspaceWithKeywords = computed(() => {
  return workspace.value.filter((ele: any) => (ele.name as string).includes(search.value))
})
const handleCheckAllChange = (val: CheckboxValueType) => {
  checkedWorkspace.value = val ? workspace.value : []
  isIndeterminate.value = false
  if (!val) {
    clearWorkspaceAll()
  }
}
const handleCheckedWorkspaceChange = (value: CheckboxValueType[]) => {
  const checkedCount = value.length
  checkAll.value = checkedCount === workspace.value.length
  isIndeterminate.value = checkedCount > 0 && checkedCount < workspace.value.length
}

const open = async () => {
  loading.value = true
  // const [authList, systemWorkspaceList] = await Promise.all([
  //   authorizationApi[`getSharedAuthorization${type}`](id),
  //   workspaceApi.getSystemWorkspaceList(),
  // ])
  // workspace.value = systemWorkspaceList.data as any
  // listType.value = (authList.data || {}).authentication_type || 'WHITE_LIST'
  // let workspace_id_list = (authList.data || {}).workspace_id_list || []
  // checkedWorkspace.value = workspace.value.filter((ele) => workspace_id_list.includes(ele.id))
  // handleCheckedWorkspaceChange(checkedWorkspace.value)
  // loading.value = false
  // centerDialogVisible.value = true
}

const handleConfirm = () => {
  // authorizationApi[`postSharedAuthorization${currentType}`](knowledge_id, {
  //   workspace_id_list: checkedWorkspace.value.map((ele: any) => ele.id),
  //   authentication_type: listType.value,
  // }).then(() => {
  //   centerDialogVisible.value = false
  // })
}

const clearWorkspace = (val: any) => {
  checkedWorkspace.value = checkedWorkspace.value.filter((ele: any) => ele.id !== val.id)
}

const clearWorkspaceAll = () => {
  checkedWorkspace.value = []
  handleCheckedWorkspaceChange([])
}

defineExpose({
  open,
})
</script>
<style lang="less">
.authorized-workspace {
  .mb-8 {
    margin-bottom: 8px;
  }

  .mt-16 {
    margin-top: 16px;
  }

  .p-16 {
    padding: 16px;
  }

  .lighter {
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
  }

  .border {
    border: 1px solid #dee0e3;
  }

  .w-full {
    width: 100%;
  }

  .mt-8 {
    margin-top: 8px;
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
  }
}
</style>
