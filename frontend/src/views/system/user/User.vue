<template>
  <div class="sqlbot-table-container professional-container">
    <div class="tool-left">
      <span class="page-title">{{ $t('user.user_management') }}</span>
      <div class="search-bar">
        <el-input
          v-model="keyword"
          style="width: 240px; margin-right: 12px"
          :placeholder="$t('user.name_account_email')"
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined />
            </el-icon>
          </template>
        </el-input>

        <el-button secondary>
          <template #icon>
            <iconFilter></iconFilter>
          </template>
          {{ $t('user.filter') }}
        </el-button>
        <el-button secondary>
          <template #icon>
            <ccmUpload></ccmUpload>
          </template>
          {{ $t('user.batch_import') }}
        </el-button>
        <el-button type="primary">
          <template #icon>
            <icon_add_outlined></icon_add_outlined>
          </template>
          {{ $t('user.add_users') }}
        </el-button>
      </div>
    </div>
    <div class="sqlbot-table">
      <el-table
        ref="multipleTableRef"
        @selection-change="handleSelectionChange"
        :data="state.tableData"
        style="width: 100%"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column prop="name" :label="$t('user.name')" width="280" />
        <el-table-column prop="account" :label="$t('user.account')" width="280" />
        <el-table-column prop="status" :label="$t('user.user_status')" width="180">
          <template #default="scope">
            <div class="user-status-container" :class="[scope.row.status ? 'active' : 'disabled']">
              <el-icon size="16">
                <SuccessFilled v-if="scope.row.status" />
                <CircleCloseFilled v-else />
              </el-icon>
              <span>{{ $t(`user.${scope.row.status ? 'enabled' : 'disabled'}`) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="email" :label="$t('user.email')" width="280" />
        <el-table-column prop="phone" :label="$t('user.phone_number')" width="280" />
        <el-table-column prop="user_source" :label="$t('user.user_source')" width="280" />
        <el-table-column prop="workspace" :label="$t('user.workspace')" width="280" />

        <el-table-column prop="create_time" width="180" sortable :label="$t('user.creation_time')">
          <template #default="scope">
            <span>{{ formatTimestamp(scope.row.create_time) }}</span>
          </template>
        </el-table-column>
        <el-table-column fixed="right" width="150" :label="$t('ds.actions')">
          <template #default="scope">
            <div class="table-operate">
              <el-switch v-model="scope.row.checked" size="small" />
              <div class="line"></div>
              <el-tooltip
                :offset="14"
                effect="dark"
                :content="$t('datasource.edit')"
                placement="top"
              >
                <el-icon class="action-btn" size="16" @click="editHandler(scope.row.id)">
                  <IconOpeEdit></IconOpeEdit>
                </el-icon>
              </el-tooltip>

              <el-tooltip
                :offset="14"
                effect="dark"
                :content="$t('datasource.edit')"
                placement="top"
              >
                <el-icon class="action-btn" size="16" @click="editHandler(scope.row.id)">
                  <IconLock></IconLock>
                </el-icon>
              </el-tooltip>

              <el-tooltip
                :offset="14"
                effect="dark"
                :content="$t('dashboard.delete')"
                placement="top"
              >
                <el-icon class="action-btn" size="16" @click="deleteHandler(scope.row.id)">
                  <IconOpeDelete></IconOpeDelete>
                </el-icon>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="state.pageInfo.currentPage"
          v-model:page-size="state.pageInfo.pageSize"
          :page-sizes="[10, 20, 30]"
          :background="true"
          layout="total, sizes, prev, pager, next, jumper"
          :total="state.pageInfo.total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>

    <div class="bottom-select">
      <el-checkbox
        v-model="checkAll"
        :indeterminate="isIndeterminate"
        @change="handleCheckAllChange"
      >
        {{ $t('datasource.select_all') }}
      </el-checkbox>

      <button class="danger-button">{{ $t('dashboard.delete') }}</button>

      <span class="selected">{{
        $t('user.selected_2_items', { msg: multipleSelectionAll.length })
      }}</span>

      <el-button text>
        {{ $t('common.cancel') }}
      </el-button>
    </div>
  </div>

  <el-dialog
    v-model="dialogFormVisible"
    title="Add Terminology"
    destroy-on-close
    width="500"
    class="sqlbot-dialog"
    @close="onFormClose"
  >
    <el-form
      ref="termFormRef"
      :model="state.form"
      label-width="180px"
      label-position="top"
      class="sqlbot-form"
      size="large"
    >
      <el-form-item label="Account">
        <el-input v-model="state.form.term" autocomplete="off" />
      </el-form-item>
      <el-form-item label="Definition">
        <el-input v-model="state.form.definition" type="textarea" />
      </el-form-item>
      <el-form-item label="Domain">
        <el-select v-model="state.form.domain" placeholder="Please select a domain">
          <el-option label="domain1" value="domain1" />
          <el-option label="domain2" value="domain2" />
          <el-option label="domain3" value="domain3" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="closeForm">Cancel</el-button>
        <el-button type="primary" @click="saveHandler"> save </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
/* import IconOpeUpload from '@/assets/svg/operate/ope-upload.svg';
import IconOpeDownload from '@/assets/svg/operate/ope-download.svg';
import IconOpeAdd from '@/assets/svg/operate/ope-add.svg'; */
import SuccessFilled from '@/assets/svg/gou_icon.svg'
import CircleCloseFilled from '@/assets/svg/icon_ban_filled.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'

import IconLock from '@/assets/svg/icon-key_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'
import IconOpeDelete from '@/assets/svg/icon_delete.svg'
import iconFilter from '@/assets/svg/icon-filter_outlined.svg'
import ccmUpload from '@/assets/svg/icon_ccm-upload_outlined.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import { userApi } from '@/api/auth'
import { formatTimestamp } from '@/utils/date'

const keyword = ref('')
const dialogFormVisible = ref(false)
const termFormRef = ref()
const checkAll = ref(false)
const isIndeterminate = ref(true)
const state = reactive({
  tableData: [],
  form: {
    id: '',
    term: '',
    definition: '',
    domain: '',
  },
  pageInfo: {
    currentPage: 1,
    pageSize: 20,
    total: 0,
  },
})

const multipleTableRef = ref()
const multipleSelectionAll = ref<any[]>([])

const handleSelectionChange = (val: any[]) => {
  const ids = state.tableData.map((ele: any) => ele.id)
  multipleSelectionAll.value = [
    ...multipleSelectionAll.value.filter((ele) => !ids.includes(ele.id)),
    ...val,
  ]
  isIndeterminate.value = !(val.length === 0 || val.length === state.tableData.length)
  checkAll.value = val.length === state.tableData.length
}
const handleCheckAllChange = (val: any) => {
  isIndeterminate.value = false
  handleSelectionChange(val ? state.tableData : [])
  val && handleToggleRowSelection()
  !val && multipleTableRef.value.clearSelection()
}

const handleToggleRowSelection = (check: boolean = true) => {
  let i = 0
  const ids = multipleSelectionAll.value.map((ele: any) => ele.id)
  for (const key in state.tableData) {
    if (ids.includes((state.tableData[key] as any).id)) {
      i += 1
      multipleTableRef.value.toggleRowSelection(state.tableData[key], check)
    }
  }
  checkAll.value = i === state.tableData.length
  isIndeterminate.value = !(i === 0 || i === state.tableData.length)
}
const handleSearch = (e: any) => {
  console.log('search', e)
}
const editHandler = (id: any) => {
  console.log('editHandler', id)
  /* userApi.query(id).then((res: any) => {
    console.log('term detail', res)
    state.form = res
    dialogFormVisible.value = true
  }) */
}
const deleteHandler = (id: any) => {
  console.log('deleteHandler', id)
  ElMessageBox.confirm('Are you sure to delete?', 'Warning', {
    confirmButtonText: 'OK',
    cancelButtonText: 'Cancel',
    type: 'warning',
  })
    .then(() => {
      /* userApi.delete(id).then(() => {
        ElMessage({
          type: 'success',
          message: 'Delete completed',
        })
        search()
      }) */
    })
    .catch(() => {
      ElMessage({
        type: 'info',
        message: 'Delete canceled',
      })
    })
}

/* const openDialog = () => {
  dialogFormVisible.value = true
} */
const resetForm = () => {
  if (!termFormRef.value) return
  Object.keys(state.form).forEach((key) => {
    state.form[key as keyof typeof state.form] = ''
  })
}

const closeForm = () => {
  dialogFormVisible.value = false
}
const onFormClose = () => {
  resetForm()
  dialogFormVisible.value = false
}

const search = () => {
  userApi.pager(state.pageInfo.currentPage, state.pageInfo.pageSize).then((res: any) => {
    state.tableData = res.items
    state.pageInfo.total = res.total

    nextTick(() => {
      handleToggleRowSelection()
    })
  })
}
const addTerm = () => {
  userApi.add(state.form).then(() => {
    dialogFormVisible.value = false
    search()
    ElMessage({
      type: 'success',
      message: 'Add completed',
    })
  })
}
const editTerm = () => {
  userApi.edit(state.form).then((res: any) => {
    console.log('edit term', res)
    dialogFormVisible.value = false
    search()
    ElMessage({
      type: 'success',
      message: 'Edit completed',
    })
  })
}
const saveHandler = () => {
  if (state.form.id) {
    editTerm()
  } else {
    addTerm()
  }
}
const handleSizeChange = (val: number) => {
  state.pageInfo.pageSize = val
  search()
}
const handleCurrentChange = (val: number) => {
  state.pageInfo.currentPage = val
  search()
}
onMounted(() => {
  search()
})
</script>

<style lang="less" scoped>
.sqlbot-table-container {
  width: 100%;
  height: 100%;
  position: relative;
  .bottom-select {
    position: absolute;
    height: 64px;
    width: calc(100% + 48px);
    left: -24px;
    bottom: 0;
    border-top: 1px solid #1f232926;
    display: flex;
    align-items: center;
    padding-left: 24px;

    .danger-button {
      border: 1px solid var(--ed-color-danger);
      color: var(--ed-color-danger);
      border-radius: var(--ed-border-radius-base);
      min-width: 80px;
      height: 32px;
      line-height: 32px;
      text-align: center;
      cursor: pointer;
      margin: 0 16px;
      background-color: transparent;
    }

    .selected {
      font-weight: 400;
      font-size: 14px;
      line-height: 22px;
      color: #646a73;
      margin-right: 12px;
    }
  }
  .tool-left {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;

    .page-title {
      font-weight: 500;
      font-size: 20px;
      line-height: 28px;
    }
  }
  .sqlbot-table {
    border-radius: 6px;
    width: 100%;
    max-height: calc(100vh - 200px);
    :deep(.ed-table) {
      --el-table-header-bg-color: #f5f7fa;
      --el-table-border-color: #ebeef5;
      --el-table-header-text-color: #606266;

      th {
        font-weight: 600;
        height: 48px;
      }

      td {
        height: 52px;
      }
    }
    .table-operate {
      display: flex;
      align-items: center;
      height: 24px;
      line-height: 24px;
      .ed-icon + .ed-icon {
        margin-left: 12px;
      }

      .line {
        margin: 0 10px 0 12px;
        height: 16px;
        width: 1px;
        background-color: #1f232926;
      }

      .ed-icon {
        position: relative;
        cursor: pointer;
        color: #646a73;

        &::after {
          content: '';
          background-color: #1f23291a;
          position: absolute;
          border-radius: 6px;
          width: 24px;
          height: 24px;
          transform: translate(-50%, -50%);
          top: 50%;
          left: 50%;
          display: none;
        }

        &:hover {
          &::after {
            display: block;
          }
        }
      }
    }
    .pagination-container {
      display: flex;
      justify-content: end;
      align-items: center;
      margin-top: 16px;
    }
  }
}
.sqlbot-form {
  width: 100%;
  .ed-form-item {
    margin-bottom: 16px;
    text-align: left;
    label {
      font-size: 14px;
      color: #606266;
    }
  }
}
.sqlbot-dialog {
  width: 500px;

  :deep(.ed-dialog__header) {
    text-align: left !important;
    font-size: 16px;
    background-color: #f5f7fa;
    border-bottom: 1px solid #ebeef5;
    color: #606266;
    font-size: 16px;
  }
}

.user-status-container {
  display: flex;
  align-items: center;
  font-weight: 400;
  font-size: 14px;
  line-height: 22px;

  .ed-icon {
    margin-right: 8px;
  }
}
</style>
