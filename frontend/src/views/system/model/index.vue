<template>
  <div class="sqlbot-table-container professional-container">
    <div class="sqlbot-tool">
      <div class="tool-left">
        <el-input
          v-model="keyword"
          class="sqlbot-search"
          placeholder="Search"
          @keyup.enter.native="handleSearch"
        >
          <template #prefix>
            <el-icon class="el-input__icon"><IconSearch /></el-icon>
          </template>
        </el-input>
      </div>
      <div class="tool-right">
        <div class="tool-btn secondary-btn" @click="batchEnableHandler">
          <el-icon><IconEnable /></el-icon>
          <span>Batch Enable</span>
        </div>
        <div class="tool-btn secondary-btn" @click="batchDisableHandler">
          <el-icon><IconDisable /></el-icon>
          <span>Batch Disable</span>
        </div>
        <div class="tool-btn primary-btn" @click="openDialog">
          <el-icon><IconOpeAdd /></el-icon>
          <span>Add Model</span>
        </div>
      </div>
    </div>
    <div class="sqlbot-table">
      <el-table
        :data="state.tableData"
        style="width: 100%"
        row-key="id"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column prop="name" label="Model Name" width="280" />
        <el-table-column prop="type" label="Model Type" width="280">
          <template #default="scope">
            <span>{{ getModelTypeName(scope.row.type) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="api_key" label="API KEY" width="280">
          <template #default="scope">
            <div class="user-status-container" :class="[scope.row.api_key ? 'active' : 'disabled']">
              <span>{{ scope.row.api_key ? 'Configured' : 'Not Configured' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="Status" width="180">
          <template #default="scope">
            <div class="user-status-container" :class="[scope.row.status ? 'active' : 'disabled']">
              <el-icon>
                <SuccessFilled v-if="scope.row.status" />
                <CircleCloseFilled v-else />
              </el-icon>
              <span>{{ scope.row.status ? 'Enabled' : 'Disabled' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="create_time" label="Create time" min-width="180">
          <template #default="scope">
            <span>{{ formatTimestamp(scope.row.create_time, 'YYYY-MM-DD HH:mm:ss') }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="Actions" width="120" fixed="right">
          <template #default="scope">
            <div class="table-operate">
              <div class="opt-btn" @click="editHandler(scope.row.id)">
                <el-icon><IconOpeEdit /></el-icon>
              </div>
              <div class="opt-btn" @click="deleteHandler(scope.row.id)">
                <el-icon><IconOpeDelete /></el-icon>
              </div>
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
          :pager-count="5"
          layout="total, sizes, prev, pager, next, jumper"
          :total="state.pageInfo.total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>
  </div>

  <el-dialog
    v-model="dialogFormVisible"
    title="Add Ai Model"
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
      <el-form-item label="Model Name">
        <el-input v-model="state.form.name" autocomplete="off" />
      </el-form-item>

      <el-form-item label="Model Type">
        <el-select v-model="state.form.type" placeholder="Please select a type">
          <el-option
            v-for="item in modelTypeOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
          <!-- <el-option label="domain1" value="0" />
          <el-option label="domain2" value="1" />
          <el-option label="domain3" value="2" /> -->
        </el-select>
      </el-form-item>

      <el-form-item label="API KEY">
        <el-input
          v-model="state.form.api_key"
          type="password"
          show-password
          placeholder="Please input password"
        />
      </el-form-item>

      <el-form-item label="API Endpoint URL">
        <el-input v-model="state.form.endpoint" placeholder="Please input endpoint" />
      </el-form-item>

      <!--      <el-form-item label="Maximum Context Window" >
        <el-input v-model="state.form.max_context_window" type="number" placeholder="Please input max_context_window" />
      </el-form-item>

      <el-form-item label="Temperature" >
        <el-slider v-model="state.form.temperature" :format-tooltip="formatTooltip" />
      </el-form-item>-->

      <el-form-item label="Model Status">
        <el-checkbox v-model="state.form.status" label="" size="large" />
      </el-form-item>

      <el-form-item label="Description">
        <el-input v-model="state.form.description" type="textarea" />
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
import { ref, reactive, onMounted } from 'vue'
import IconEnable from '@/assets/svg/operate/ope-enable.svg'
import IconDisable from '@/assets/svg/operate/ope-disable.svg'
import IconOpeAdd from '@/assets/svg/operate/ope-add.svg'

import { SuccessFilled, CircleCloseFilled, Search as IconSearch } from '@element-plus/icons-vue'
import IconOpeEdit from '@/assets/svg/operate/ope-edit.svg'
import IconOpeDelete from '@/assets/svg/operate/ope-delete.svg'
import { modelApi } from '@/api/system'
import { formatTimestamp } from '@/utils/date'
import { modelTypeOptions, getModelTypeName } from '@/entity/CommonEntity.ts'
const keyword = ref('')
const dialogFormVisible = ref(false)
const termFormRef = ref()
const state = reactive({
  tableData: [],
  form: {
    id: '',
    name: '',
    type: 0,
    api_key: '',
    endpoint: '',
    max_context_window: 0,
    temperature: 0,
    status: false,
    description: '',
  },
  pageInfo: {
    currentPage: 1,
    pageSize: 20,
    total: 0,
  },
  selectedIds: [],
})
onMounted(() => {
  search()
})
const handleSearch = (e: any) => {
  console.log('search', e)
}
const editHandler = (id: any) => {
  modelApi.query(id).then((res: any) => {
    state.form = res
    state.form.temperature = state.form.temperature * 100
    dialogFormVisible.value = true
  })
}
const deleteHandler = (id: any) => {
  ElMessageBox.confirm('Are you sure to delete?', 'Warning', {
    confirmButtonText: 'OK',
    cancelButtonText: 'Cancel',
    type: 'warning',
  })
    .then(() => {
      modelApi.delete(id).then(() => {
        ElMessage({
          type: 'success',
          message: 'Delete completed',
        })
        search()
      })
    })
    .catch(() => {
      ElMessage({
        type: 'info',
        message: 'Delete canceled',
      })
    })
}

const openDialog = () => {
  dialogFormVisible.value = true
}
const resetForm = () => {
  if (!termFormRef.value) return
  state.form = {
    id: '',
    name: '',
    type: 0,
    api_key: '',
    endpoint: '',
    max_context_window: 0,
    temperature: 0,
    status: false,
    description: '',
  }
}

const closeForm = () => {
  dialogFormVisible.value = false
}
const onFormClose = () => {
  resetForm()
  dialogFormVisible.value = false
}

const search = () => {
  modelApi.pager(state.pageInfo.currentPage, state.pageInfo.pageSize).then((res: any) => {
    state.tableData = res.items
    state.pageInfo.total = res.total
  })
}
const addTerm = () => {
  const param: any = {
    ...state.form,
  }
  delete param.id
  param.temperature = param.temperature / 100
  modelApi.add(param).then(() => {
    dialogFormVisible.value = false
    search()
    ElMessage({
      type: 'success',
      message: 'Add completed',
    })
  })
}
const editTerm = () => {
  const param = state.form
  param.temperature = param.temperature / 100
  modelApi.edit(state.form).then((res: any) => {
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
const handleSelectionChange = (rows: any) => {
  state.selectedIds = rows.map((item: any) => item.id)
}

const batchDisableHandler = () => {
  if (state.selectedIds.length === 0) {
    ElMessage({
      type: 'warning',
      message: 'Please select at least one item',
    })
    return
  }
  const param = {
    ids: state.selectedIds,
    status: false,
  }

  ElMessageBox.confirm('Are you sure to execute this operation?', 'Warning', {
    confirmButtonText: 'OK',
    cancelButtonText: 'Cancel',
    type: 'warning',
  })
    .then(() => {
      modelApi.status(param).then(() => {
        search()
        ElMessage({
          type: 'success',
          message: 'Batch disable completed',
        })
      })
    })
    .catch(() => {
      ElMessage({
        type: 'info',
        message: 'Execute canceled',
      })
    })
}
const batchEnableHandler = () => {
  if (state.selectedIds.length === 0) {
    ElMessage({
      type: 'warning',
      message: 'Please select at least one item',
    })
    return
  }
  const param = {
    ids: state.selectedIds,
    status: true,
  }
  modelApi.status(param).then(() => {
    search()
    ElMessage({
      type: 'success',
      message: 'Batch enable completed',
    })
  })
}
</script>

<style lang="less" scoped>
.sqlbot-table-container {
  width: 100%;
  height: 100%;
  .sqlbot-tool {
    height: 42px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background-color: var(--white);
    padding: 16px 20px;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    margin-bottom: 20px;
    .tool-left {
      display: flex;
      align-items: center;
      .sqlbot-search {
        width: 300px;
        --el-input-inner-height: 40px !important;
        --el-input-border-radius: 24px;
        --el-input-bg-color: #f5f7fa;
        --el-input-border-color: #e5e8ed;
      }
    }
    .tool-right {
      display: flex;
      align-items: center;
      column-gap: 12px;
      height: 35px;
      .secondary-btn {
        background: #f5f5f5;
        color: #333;
        border: 1px solid #ddd;
      }
      .primary-btn {
        background: var(--el-color-primary);
        color: white;
      }
      .tool-btn {
        display: flex;
        align-items: center;
        padding: 6px 16px;
        border-radius: 4px;
        cursor: pointer;
        outline: none;
        font-weight: 500;
        transition: all 0.3s;
        font-size: 14px;
        gap: 6px;
        &:hover {
          background-color: #f1f3f4;
        }
        &.default {
          color: #2d2e31;
          font-weight: 500;
          font-size: 14px;
          i {
            width: 20px;
            height: 20px;
          }
        }
      }
    }
  }
  .sqlbot-table {
    border-radius: 6px;
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
      /* border-left: 1px solid var(--el-table-border-color);
      border-right: 1px solid var(--el-table-border-color); */
    }
    .table-operate {
      display: flex;
      justify-content: flex-end;
      gap: 8px;

      .opt-btn {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #5f6368;
        cursor: pointer;
        transition: all 0.2s;
        background-color: #f1f3f4;
        border: none;
        font-size: 18px;
        &:hover {
          background-color: #e8f0fe;
          color: var(--el-color-primary);
        }
      }
    }
    .pagination-container {
      display: flex;
      justify-content: end;
      align-items: center;
      margin-top: 20px;
      background-color: var(--white);
      padding: 16px 20px;
      border-radius: 8px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
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
  column-gap: 8px;
  font-size: 14px;
  color: #606266;
  padding: 4px 8px;
  width: fit-content;
  border-radius: 4px;
  &.active {
    background-color: #e6f7ee;
    color: #389e0d;
  }
  &.disabled {
    background-color: #fff1f0;
    color: #cf1322;
  }
}
</style>
