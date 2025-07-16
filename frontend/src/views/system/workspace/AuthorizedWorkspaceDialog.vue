<template>
  <el-dialog
    v-model="centerDialogVisible"
    :title="$t('workspace.add_member')"
    modal-class="authorized-workspace"
    width="840"
  >
    <p class="mb-8 lighter">{{ $t('workspace.member_type') }}</p>
    <el-radio-group v-model="listType">
      <el-radio :value="0">{{ $t('workspace.ordinary_member') }}</el-radio>
      <el-radio :value="1">{{ $t('workspace.administrator') }}</el-radio>
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
                <el-icon size="28">
                  <avatar_personal></avatar_personal>
                </el-icon>
                <span class="ml-4"> {{ space.name }}</span>
                <span class="account">({{ space.account }})</span>
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
            <el-icon size="28">
              <avatar_personal></avatar_personal>
            </el-icon>
            <span class="ml-4 lighter">{{ ele.name }}</span>
            <span class="account">({{ ele.account }})</span>
          </div>
          <el-button text>
            <el-icon size="16" @click="clearWorkspace(ele)"><Close /></el-icon>
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
import { workspaceOptionUserList, workspaceUwsCreate } from '@/api/workspace'
import avatar_personal from '@/assets/svg/avatar_personal.svg'
import Close from '@/assets/svg/icon_close_outlined_w.svg'
import Search from '@/assets/svg/icon_search-outline_outlined.svg'
import type { CheckboxValueType } from 'element-plus-secondary'
const checkAll = ref(false)
const isIndeterminate = ref(false)
const checkedWorkspace = ref<any[]>([])
const workspace = ref<any[]>([])
const listType = ref(0)
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
let oid: any = null

const open = async (id: any) => {
  loading.value = true
  oid = id
  const systemWorkspaceList = await workspaceOptionUserList({ oid }, 1, 1000)
  workspace.value = systemWorkspaceList.items as any
  loading.value = false
  centerDialogVisible.value = true
}
const emits = defineEmits(['refresh'])
const handleConfirm = () => {
  workspaceUwsCreate({
    uid_list: checkedWorkspace.value.map((ele: any) => ele.id),
    oid,
    weight: listType.value,
  }).then(() => {
    centerDialogVisible.value = false
    emits('refresh')
  })
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

  .checkbox-group-block {
    .ed-checkbox,
    .ed-checkbox__label,
    .flex {
      width: 100%;
      height: 44px;
    }

    .flex {
      align-items: center;
      .account {
        color: #8f959e;
      }
    }
  }

  .border {
    border: 1px solid #dee0e3;
  }

  .w-full {
    width: 100%;

    .flex-between {
      height: 44px;
    }
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
