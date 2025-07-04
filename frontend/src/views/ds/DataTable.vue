<script lang="ts" setup>
import { ref, computed, onMounted } from 'vue'
import { datasourceApi } from '@/api/datasource'
import icon_right_outlined from '@/assets/svg/icon_right_outlined.svg'
import icon_form_outlined from '@/assets/svg/icon_form_outlined.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import edit from '@/assets/svg/icon_edit_outlined.svg'
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
const total = ref(1000)
const showNum = ref(100)
const currentTable = ref<any>({})
const ds = ref<any>({})
const btnSelect = ref('q')

const init = () => {
  datasourceApi.getDs(props.info.id).then((res) => {
    ds.value = res
    fieldList.value = []
    datasourceApi.tableList(props.info.id).then((res) => {
      tableList.value = res
    })
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
const previewData = ref<any>({})
const fieldList = ref<any>([])

const buildData = () => {
  return { table: currentTable.value, fields: fieldList.value }
}

const handleSelectTableList = () => {
  paramsFormRef.value.open(props.info)
}

const clickTable = (table: any) => {
  currentTable.value = table
  datasourceApi.fieldList(table.id).then((res) => {
    fieldList.value = res
    datasourceApi.previewData(props.info.id, buildData()).then((res) => {
      previewData.value = res
    })
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
  datasourceApi.saveTable(currentTable.value).then(() => {
    closeTable()
    ElMessage({
      message: t('common.save_success'),
      type: 'success',
      showClose: true,
    })
  })
}
const closeField = () => {
  fieldDialog.value = false
}

const refresh = () => {
  datasourceApi.tableList(props.info.id).then((res) => {
    tableList.value = res
    if (!currentTable.value.table_name) return
    const nameArr = tableList.value.map((ele: any) => ele.table_name)
    if (!nameArr.includes(currentTable.value.table_name)) {
      currentTable.value = {}
    }
  })
}

const saveField = () => {
  currentField.value.custom_comment = fieldComment.value
  datasourceApi.saveField(currentField.value).then(() => {
    closeField()
    ElMessage({
      message: t('common.save_success'),
      type: 'success',
      showClose: true,
    })
  })
}

const editField = (row: any) => {
  currentField.value = row
  fieldComment.value = currentField.value.custom_comment
  fieldDialog.value = true
}

const changeStatus = (row: any) => {
  currentField.value = row
  datasourceApi.saveField(currentField.value).then(() => {
    closeField()
    ElMessage({
      message: t('common.save_success'),
      type: 'success',
      showClose: true,
    })
  })
}
</script>

<template>
  <div class="data-table no-padding">
    <div class="info">
      {{ $t('ds.title') }}
      <el-icon size="12">
        <icon_right_outlined></icon_right_outlined>
      </el-icon>
      <div class="name">{{ info.name }}</div>
    </div>
    <div class="content">
      <div class="side-list">
        <div class="select-table_top">
          {{ $t('ds.tables') }}

          <el-tooltip effect="dark" :content="$t('ds.form.choose_tables')" placement="top">
            <el-icon size="18" @click="handleSelectTableList">
              <icon_form_outlined></icon_form_outlined>
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
            :key="ele.table_name"
            class="model"
            :class="currentTable.table_name === ele.table_name && 'isActive'"
            @click="clickTable(ele)"
          >
            <el-icon size="16">
              <icon_form_outlined></icon_form_outlined>
            </el-icon>
            <span class="name">{{ ele.table_name }}</span>
          </div>
          <EmptyBackground
            v-if="!!keywords && !tableListWithSearch.length"
            :description="$t('datasource.relevant_content_found')"
            img-type="tree"
            style="width: 100%; margin-top: 100px"
          />
        </div>
      </div>

      <div v-if="currentTable.table_name" class="info-table">
        <div class="table-name">
          <div class="name">{{ currentTable.table_name }}</div>
          <div class="notes">
            {{ $t('about.remark') }}:
            {{ currentTable.custom_comment || '-' }}
            <el-icon style="margin-left: 8px; cursor: pointer" size="16" @click="editTable">
              <edit></edit>
            </el-icon>
          </div>
        </div>
        <div class="table-content">
          <div class="btn-select">
            <el-button :class="[btnSelect === 'd' && 'is-active']" text @click="btnSelect = 'd'">
              {{ t('ds.table_schema') }}
            </el-button>
            <el-button :class="[btnSelect === 'q' && 'is-active']" text @click="btnSelect = 'q'">
              {{ t('ds.preview') }}
            </el-button>
          </div>

          <div class="preview-or-schema">
            <el-table v-if="btnSelect === 'd'" :data="fieldList" style="width: 100%">
              <el-table-column prop="field_name" :label="t('datasource.field_name')" width="180" />
              <el-table-column prop="field_type" :label="t('datasource.field_type')" width="180" />
              <el-table-column prop="field_comment" :label="t('about.remark')" />
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
                        <edit></edit>
                      </el-icon>
                    </el-tooltip>
                  </div>
                </template>
              </el-table-column>
              <el-table-column :label="t('datasource.enabled_status')" width="180">
                <template #default="scope">
                  <div style="display: flex; align-items: center">
                    <el-switch
                      v-model="scope.row.checked"
                      size="small"
                      @change="changeStatus(scope.row)"
                    />
                  </div>
                </template>
              </el-table-column>
            </el-table>
            <template v-else>
              <div class="preview-num">
                {{ t('ds.pieces_in_total', { msg: total, ms: showNum }) }}
              </div>
              <el-table :data="previewData.data" style="width: 100%; height: 600px">
                <el-table-column
                  v-for="(c, index) in previewData.fields"
                  :key="index"
                  :prop="c"
                  :label="c"
                />
              </el-table>
            </template>
          </div>
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
      :placeholder="$t('datasource.please_enter')"
      v-model="tableComment"
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
      :placeholder="$t('datasource.please_enter')"
      v-model="fieldComment"
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
.data-table {
  height: 100%;
  .info {
    height: 56px;
    width: 100%;
    padding-left: 20px;
    display: flex;
    align-items: center;
    font-family: PingFang SC;
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
    color: #646a73;
    border-bottom: 1px solid #1f232926;

    .name {
      color: #1f2329;
    }
  }
  .content {
    height: calc(100% - 56px);
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

        .ed-icon:hover {
          cursor: pointer;
          color: var(--ed-color-primary);
        }
      }

      .ed-input {
        margin: 8px;
      }

      .list-content {
        height: calc(100% - 100px);
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

        .btn-select {
          height: 32px;
          padding-left: 4px;
          padding-right: 4px;
          display: inline-flex;
          background: #ffffff;
          align-items: center;
          border: 1px solid #d0d3d6;
          border-radius: 4px;

          .is-active {
            background: #1cba901a;
          }

          .ed-button:not(.is-active) {
            color: #1f2329;
          }
          .ed-button.is-text {
            height: 24px;
            width: auto;
            padding: 0 8px;
            line-height: 24px;
          }
          .ed-button + .ed-button {
            margin-left: 4px;
          }
        }

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
}
</style>
