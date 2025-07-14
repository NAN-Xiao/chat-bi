<script lang="ts" setup>
import { ref, computed, onMounted } from 'vue'
import { workspaceList, workspaceUserList } from '@/api/workspace'
import icon_form_outlined from '@/assets/svg/icon_form_outlined.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
// import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import assigned from '@/assets/svg/icon_assigned_outlined.svg'
// import rename from '@/assets/svg/icon_rename_outlined.svg'
// import icon_member from '@/assets/svg/icon_member.svg'
import SuccessFilled from '@/assets/svg/gou_icon.svg'
import CircleCloseFilled from '@/assets/svg/icon_ban_filled.svg'
import { useI18n } from 'vue-i18n'
import ParamsForm from './ParamsForm.vue'

interface Table {
  name: string
  host: string
  port: string
  username: string
  password: string
  database: string
  extraJdbc: string
  dbSchema: string
  filename: string
  sheets: string
  mode: string
  timeout: string
  configuration: string
  id: number
}

const props = withDefaults(
  defineProps<{
    info: Table
  }>(),
  {
    info: () => ({
      name: '-',
      host: '-',
      port: '-',
      username: '-',
      password: '-',
      database: '-',
      extraJdbc: '-',
      dbSchema: '-',
      filename: '-',
      sheets: '-',
      mode: '-',
      timeout: '-',
      configuration: '-',
      id: 0,
    }),
  }
)
const { t } = useI18n()
const paramsFormRef = ref()
const tableList = ref([] as any[])
const keywords = ref('')
const tableListWithSearch = computed(() => {
  if (!keywords.value) return tableList.value
  return tableList.value.filter((ele) =>
    ele.name.toLowerCase().includes(keywords.value.toLowerCase())
  )
})
const currentTable = ref<any>({})

const init = () => {
  workspaceList().then((res) => {
    tableList.value = res
  })
}
onMounted(() => {
  init()
})
const tableComment = ref('')
const fieldDialog = ref<boolean>(false)
const tableDialog = ref<boolean>(false)
const fieldComment = ref('')
const currentField = ref<any>({})
const fieldList = ref<any>([])

const handleSelectTableList = () => {
  paramsFormRef.value.open(props.info)
}

const clickTable = (table: any) => {
  currentTable.value = table
  workspaceUserList({ oid: table.id }, 1, 10).then((res) => {
    fieldList.value = res
    //   datasourceApi.previewData(props.info.id, buildData()).then((res) => {
    //     previewData.value = res
    //   })
  })
}

const closeTable = () => {
  tableDialog.value = false
}
const editTable = () => {
  tableComment.value = currentTable.value.custom_comment
  tableDialog.value = true
}
const saveTable = () => {
  currentTable.value.custom_comment = tableComment.value
  //   datasourceApi.saveTable(currentTable.value).then(() => {
  //     closeTable()
  //     ElMessage({
  //       message: t('common.save_success'),
  //       type: 'success',
  //       showClose: true,
  //     })
  //   })
}
const closeField = () => {
  fieldDialog.value = false
}

const refresh = () => {
  //   datasourceApi.tableList(props.info.id).then((res) => {
  //     tableList.value = res
  //     if (!currentTable.value.name) return
  //     const nameArr = tableList.value.map((ele: any) => ele.name)
  //     if (!nameArr.includes(currentTable.value.name)) {
  //       currentTable.value = {}
  //     }
  //   })
}

const saveField = () => {
  currentField.value.custom_comment = fieldComment.value
  //   datasourceApi.saveField(currentField.value).then(() => {
  //     closeField()
  //     ElMessage({
  //       message: t('common.save_success'),
  //       type: 'success',
  //       showClose: true,
  //     })
  //   })
}

const editField = (row: any) => {
  currentField.value = row
  fieldComment.value = currentField.value.custom_comment
  fieldDialog.value = true
}
</script>

<template>
  <div class="workspace no-padding">
    <div class="side-list">
      <div class="select-table_top">
        {{ $t('user.workspace') }}

        <el-tooltip effect="dark" :content="$t('workspace.add_workspace')" placement="top">
          <el-icon size="18" @click="handleSelectTableList">
            <icon_add_outlined></icon_add_outlined>
          </el-icon>
        </el-tooltip>
      </div>
      <el-input
        v-model="keywords"
        clearable
        style="width: 232px"
        :placeholder="$t('datasource.search')"
      >
        <template #prefix>
          <el-icon>
            <icon_searchOutline_outlined class="svg-icon" />
          </el-icon>
        </template>
      </el-input>

      <div class="list-content">
        <div
          v-for="ele in tableListWithSearch"
          :key="ele.name"
          class="model"
          :class="currentTable.name === ele.name && 'isActive'"
          @click="clickTable(ele)"
        >
          <el-icon size="16">
            <icon_form_outlined></icon_form_outlined>
          </el-icon>
          <span class="name">{{ ele.name }}</span>
        </div>
        <div v-if="!!keywords && !tableListWithSearch.length" class="no-result">
          {{ $t('workspace.historical_dialogue') }}
        </div>
      </div>
    </div>

    <div v-if="currentTable.name" class="info-table">
      <div class="table-name">
        <div class="name">{{ currentTable.name }}</div>
        <div class="notes">
          {{ $t('about.remark') }}:
          {{ currentTable.custom_comment || '-' }}
          <el-icon style="margin-left: 8px; cursor: pointer" size="16" @click="editTable">
            <edit></edit>
          </el-icon>
        </div>
      </div>
      <div class="table-content">
        <div class="preview-or-schema">
          <el-table :data="fieldList" style="width: 100%">
            <el-table-column type="selection" width="55" />
            <el-table-column prop="name" :label="$t('user.name')" width="280" />
            <el-table-column prop="account" :label="$t('user.account')" width="280" />
            <el-table-column prop="status" :label="$t('user.user_status')" width="180">
              <template #default="scope">
                <div
                  class="user-status-container"
                  :class="[scope.row.status ? 'active' : 'disabled']"
                >
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
            <el-table-column :label="t('datasource.custom_notes')">
              <template #default="scope">
                <div class="field-comment">
                  <span>{{ scope.row.custom_comment }}</span>
                  <el-tooltip
                    :offset="14"
                    effect="dark"
                    :content="$t('datasource.edit')"
                    placement="top"
                  >
                    <el-icon class="action-btn" size="16" @click="editField(scope.row)">
                      <assigned></assigned>
                    </el-icon>
                  </el-tooltip>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>
  </div>
  <el-dialog
    v-model="tableDialog"
    :title="t('datasource.table_notes')"
    width="600"
    :destroy-on-close="true"
    :close-on-click-modal="false"
    @closed="closeTable"
  >
    <el-input
      v-model="tableComment"
      :placeholder="$t('datasource.please_enter')"
      :rows="3"
      type="textarea"
    />
    <div style="display: flex; justify-content: flex-end; margin-top: 20px">
      <el-button @click="closeTable">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" @click="saveTable">{{ t('common.confirm') }}</el-button>
    </div>
  </el-dialog>

  <el-dialog
    v-model="fieldDialog"
    :title="t('datasource.field_notes')"
    width="600"
    :destroy-on-close="true"
    :close-on-click-modal="false"
    @closed="closeField"
  >
    <el-input
      v-model="fieldComment"
      :placeholder="$t('datasource.please_enter')"
      :rows="3"
      type="textarea"
    />
    <div style="display: flex; justify-content: flex-end; margin-top: 20px">
      <el-button @click="closeField">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" @click="saveField">{{ t('common.confirm') }}</el-button>
    </div>
  </el-dialog>
  <ParamsForm ref="paramsFormRef" @refresh="refresh"></ParamsForm>
</template>

<style lang="less" scoped>
.workspace {
  height: 100%;
  position: relative;
  .side-list {
    width: 280px;
    padding: 8px 16px;
    height: 100%;
    border-right: 1px solid #1f232926;
    .select-table_top {
      height: 40px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px;

      .ed-icon {
        cursor: pointer;
        color: var(--ed-color-primary);
        position: relative;

        &:hover {
          &::after {
            display: block;
          }
        }

        &::after {
          content: '';
          display: none;
          position: absolute;
          width: 26px;
          height: 26px;
          background: #1cba901a;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          border-radius: 6px;
        }
      }
    }

    .ed-input {
      margin: 8px;
    }

    .list-content {
      height: calc(100% - 100px);

      .no-result {
        margin-top: 72px;
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        text-align: center;
        color: #646a73;
      }
      .model {
        width: 100%;
        height: 32px;
        display: flex;
        align-items: center;
        padding-left: 8px;
        border-radius: 4px;
        cursor: pointer;
        .name {
          margin-left: 8px;
          font-weight: 500;
          font-size: 14px;
          line-height: 22px;
        }
        &:hover {
          background: #1f23291a;
        }

        &.isActive {
          background: #1cba901a;
          color: var(--ed-color-primary);
        }
      }
    }
  }
  .info-table {
    position: absolute;
    right: 0;
    top: 0;
    width: calc(100% - 280px);
    .table-name {
      height: 80px;
      padding: 16px 0 0 24px;
      border-bottom: 1px solid #1f232926;

      .name {
        font-weight: 500;
        font-size: 16px;
        line-height: 24px;
      }

      .notes {
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        color: #646a73;
        display: flex;
        align-items: center;
      }
    }

    .table-content {
      padding: 16px 24px;

      .preview-or-schema {
        margin-top: 16px;

        .field-comment {
          height: 24px;
        }
        .ed-icon {
          position: relative;
          cursor: pointer;
          margin-top: 4px;

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

        .preview-num {
          margin: 12px 0;
          font-weight: 400;
          font-size: 14px;
          line-height: 22px;
          color: #646a73;
        }
      }
    }
  }
}
</style>
