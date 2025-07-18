<script lang="ts" setup>
import { ref, computed, reactive } from 'vue'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_close_outlined from '@/assets/svg/operate/ope-close.svg'
import icon_down_outlined from '@/assets/svg/icon_down_outlined.svg'
import Card from './Card.vue'

import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const keywords = ref('')
const activeStep = ref(0)
const dialogFormVisible = ref(false)
const ruleConfigvVisible = ref(false)
const editRule = ref(0)
const termFormRef = ref()
const columnFormRef = ref()
const drawerTitle = ref('')
const dialogTitle = ref('')
const tableData = ref<any[]>([])
const ruleList = ref<any[]>([
  {
    id: 1,
    num: '10',
    type: '90',
    name: 'jkjkj',
  },
])
const form = reactive({
  name: '',
  id: '',
})
const tableColumnData = ref<any[]>([])
const searchColumn = ref('')

const columnForm = reactive({
  name: '',
  id: '',
  dataTable: '',
  datasource: '',
})

const options = ref<any[]>([])
const ruleListWithSearch = computed(() => {
  if (!keywords.value) return ruleList.value
  return ruleList.value.filter((ele) =>
    ele.name.toLowerCase().includes(keywords.value.toLowerCase())
  )
})
const setDrawerTitle = () => {
  if (activeStep.value === 0) {
    drawerTitle.value = t('permission.add_rule_group')
  } else {
    if (editRule.value === 1) {
      drawerTitle.value = t('permission.set_permission_rule')
    }

    if (editRule.value === 2) {
      drawerTitle.value = t('permission.select_restricted_user')
    }
  }
}

const userTypeList = [
  {
    name: t('permission.row_permission'),
    value: 1,
  },
  {
    name: t('permission.column_permission'),
    value: 0,
  },
]

const handleAddPermission = (val: any) => {
  if (val === 1) {
    handleRowPermission()
  } else {
    handleColumnPermission(null)
  }
}

const handleRowPermission = () => {
  console.log('handleRowPermission')
}
const handleColumnPermission = (row: any) => {
  dialogFormVisible.value = true
  dialogTitle.value = row?.id
    ? t('permission.edit_column_permission')
    : t('permission.add_column_permission')
}
const beforeClose = () => {
  ruleConfigvVisible.value = false
  activeStep.value = 0
}
const handleSearch = () => {}
const editHandler = (row: any) => {
  editRule.value = 0
  setDrawerTitle()
  ruleConfigvVisible.value = true
  console.log('row', row)
}
const handleEditRule = (row: any) => {
  editRule.value = 1
  setDrawerTitle()
  console.log(row)
}
const deleteHandler = (row: any) => {
  console.log(row)
}
const setUser = (row: any) => {
  editRule.value = 2
  setDrawerTitle()
  console.log(row)
}

const rules = {
  name: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('permission.rule_group_name'),
      trigger: 'blur',
    },
  ],
}

const closeForm = () => {
  dialogFormVisible.value = false
}

const saveHandler = () => {}

const columnRules = {
  name: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('permission.rule_name'),
      trigger: 'blur',
    },
  ],

  dataTable: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('permission.rule_group_name'),
      trigger: 'blur',
    },
  ],
}
</script>

<template>
  <div class="permission">
    <div class="tool-left">
      <span class="page-title">{{ $t('workspace.permission_configuration') }}</span>
      <div>
        <el-input
          v-model="keywords"
          style="width: 240px; margin-right: 12px"
          :placeholder="$t('permission.search_rule_group')"
          @keyup.enter="handleSearch"
          @blur="handleSearch"
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined />
            </el-icon>
          </template>
        </el-input>

        <el-button type="primary" @click="editHandler(null)">
          <template #icon>
            <icon_add_outlined></icon_add_outlined>
          </template>
          {{ $t('permission.add_rule_group') }}
        </el-button>
      </div>
    </div>

    <EmptyBackground
      v-if="!!keywords && !ruleListWithSearch.length"
      :description="$t('datasource.relevant_content_found')"
      img-type="tree"
    />

    <div v-else class="card-content">
      <Card
        v-for="ele in ruleListWithSearch"
        :id="ele.id"
        :key="ele.id"
        :name="ele.name"
        :type="ele.type"
        :num="ele.num"
        @edit="handleEditRule(ele)"
        @del="deleteHandler(ele)"
        @set-user="setUser(ele)"
      ></Card>
    </div>
    <el-drawer
      v-model="ruleConfigvVisible"
      :close-on-click-modal="false"
      size="calc(100% - 100px)"
      modal-class="permission-drawer-fullscreen"
      direction="btt"
      :before-close="beforeClose"
      :show-close="false"
    >
      <template #header="{ close }">
        <span style="white-space: nowrap">{{ drawerTitle }}</span>
        <div v-if="!editRule" class="flex-center" style="width: 100%">
          <el-steps custom style="max-width: 500px; flex: 1" :active="activeStep" align-center>
            <el-step>
              <template #title> {{ $t('permission.set_permission_rule') }} </template>
            </el-step>
            <el-step>
              <template #title> {{ $t('permission.select_restricted_user') }} </template>
            </el-step>
          </el-steps>
        </div>
        <el-icon style="cursor: pointer" @click="close">
          <icon_close_outlined></icon_close_outlined>
        </el-icon>
      </template>

      <div class="drawer-content">
        <div class="title">
          {{ $t('ds.form.base_info') }}
        </div>

        <el-form
          ref="termFormRef"
          :model="form"
          label-width="180px"
          label-position="top"
          :rules="rules"
          class="form-content_error"
        >
          <el-form-item prop="name" :label="t('permission.rule_group_name')">
            <el-input
              v-model="form.name"
              :placeholder="
                $t('datasource.please_enter') +
                $t('common.empty') +
                $t('permission.rule_group_name')
              "
              autocomplete="off"
            />
          </el-form-item>

          <el-form-item class="add-permission_form">
            <template #label>
              <div
                style="
                  width: 100%;
                  display: flex;
                  align-items: center;
                  justify-content: space-between;
                "
              >
                {{ t('permission.permission_rule') }}

                <el-popover popper-class="system-permission_user" placement="bottom">
                  <template #reference>
                    <el-button class="add-btn" type="primary">
                      {{ $t('model.add') }}
                      <el-icon style="margin-left: 4px" size="16">
                        <icon_down_outlined></icon_down_outlined>
                      </el-icon>
                    </el-button>
                  </template>
                  <div class="popover">
                    <div class="popover-content">
                      <div
                        v-for="ele in userTypeList"
                        :key="ele.name"
                        class="popover-item"
                        @click="handleAddPermission(ele.value)"
                      >
                        <div class="model-name">{{ ele.name }}</div>
                      </div>
                    </div>
                  </div>
                </el-popover>
              </div>
            </template>
            <div class="table-content">
              <el-table
                :empty-text="$t('permission.no_rule')"
                :data="tableData"
                style="width: 100%"
              >
                <el-table-column prop="name" :label="$t('permission.rule_name')" />
                <el-table-column prop="type" :label="$t('permission.type')" />
                <el-table-column prop="datasource" :label="$t('permission.data_source')" />
                <el-table-column prop="data_table" :label="$t('permission.data_table')" />
                <el-table-column fixed="right" width="150" :label="$t('ds.actions')">
                  <template #default="scope">
                    <el-tooltip
                      :offset="14"
                      effect="dark"
                      :content="$t('datasource.edit')"
                      placement="top"
                    >
                      <el-icon class="action-btn" size="16" @click="editHandler(scope.row)">
                        <IconOpeEdit></IconOpeEdit>
                      </el-icon>
                    </el-tooltip>

                    <el-tooltip
                      :offset="14"
                      effect="dark"
                      :content="$t('dashboard.delete')"
                      placement="top"
                    >
                      <el-icon class="action-btn" size="16" @click="deleteHandler(scope.row)">
                        <IconOpeDelete></IconOpeDelete>
                      </el-icon>
                    </el-tooltip>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-form-item>
        </el-form>
      </div>
    </el-drawer>

    <el-drawer
      v-model="dialogFormVisible"
      :title="dialogTitle"
      destroy-on-close
      size="896px"
      modal-class="column-form_drawer"
      :before-close="closeForm"
    >
      <el-form
        ref="columnFormRef"
        :model="columnForm"
        label-width="180px"
        label-position="top"
        :rules="columnRules"
        class="form-content_error"
      >
        <el-form-item prop="name" :label="t('permission.rule_name')">
          <el-input
            v-model="columnForm.name"
            :placeholder="
              $t('datasource.please_enter') + $t('common.empty') + $t('permission.rule_name')
            "
            autocomplete="off"
          />
        </el-form-item>
        <el-form-item prop="dataTable" :label="t('permission.data_table')">
          <el-select
            v-model="columnForm.datasource"
            style="width: 416px"
            :placeholder="
              $t('datasource.Please_select') + $t('common.empty') + $t('permission.data_source')
            "
          >
            <el-option v-for="item in options" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
          <el-select
            v-model="columnForm.dataTable"
            style="width: 416px; margin-left: auto"
            :disabled="!columnForm.datasource"
            :placeholder="
              $t('datasource.Please_select') + $t('common.empty') + $t('permission.data_table')
            "
          >
            <el-option v-for="item in options" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('permission.set_rule')">
          <el-input
            v-model="searchColumn"
            :placeholder="$t('permission.search_rule_group')"
            autocomplete="off"
            ><template #prefix>
              <el-icon>
                <icon_searchOutline_outlined />
              </el-icon> </template
          ></el-input>
        </el-form-item>
      </el-form>
      <div class="table-content">
        <el-table
          :empty-text="$t('permission.no_fields_yet')"
          :data="tableColumnData"
          style="width: 100%"
        >
          <el-table-column prop="name" :label="$t('datasource.field_name')" />
          <el-table-column prop="type" :label="$t('datasource.field_notes')" />
          <el-table-column fixed="right" width="150" :label="$t('ds.actions')">
            <template #default="scope">
              <el-switch v-model="scope.row.checked" size="small" />
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="closeForm">{{ $t('common.cancel') }}</el-button>
          <el-button type="primary" @click="saveHandler">
            {{ $t('common.save') }}
          </el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.permission {
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

  .card-content {
    display: flex;
    flex-wrap: wrap;
    max-height: calc(100% - 40px);
    overflow-y: auto;
  }
}
</style>

<style lang="less">
.permission-drawer-fullscreen {
  .title {
    font-weight: 500;
    font-size: 16px;
    line-height: 24px;
    margin-top: 8px;
    margin-bottom: 16px;
  }

  .drawer-content {
    width: 800px;
    margin: 0 auto;
    height: calc(100% - 20px);

    .add-btn:hover {
      .ed-icon {
        transform: rotate(180deg);
      }
    }
    .add-permission_form {
      .ed-form-item__label {
        width: 100%;
        padding-right: 0;
      }

      .table-content {
        width: 100%;
        margin-top: 16px;
        border: 1px solid #1f232926;
        border-top: none;
        border-radius: 6px;
        overflow: hidden;
        max-height: calc(100vh - 400px);
        .ed-table__empty-text {
          padding-top: 0;
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
    }
  }
}

.column-form_drawer {
  .table-content {
    width: 100%;
    margin-top: 16px;
    border: 1px solid #1f232926;
    border-top: none;
    border-radius: 6px;
    overflow: hidden;
    max-height: calc(100vh - 400px);
    .ed-table__empty-text {
      padding-top: 0;
    }
  }
}

.system-permission_user.system-permission_user {
  padding: 0;
  width: 120px !important;
  min-width: 120px !important;
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border: 1px solid #dee0e3;

  .popover {
    .popover-content {
      padding: 4px;
      position: relative;
      &::after {
        position: absolute;
        content: '';
        left: 0;
        top: 40px;
        width: 100%;
        height: 1px;
        background: #1f232926;
      }
    }
    .popover-item {
      height: 32px;
      display: flex;
      align-items: center;
      padding-left: 12px;
      padding-right: 8px;
      position: relative;
      border-radius: 4px;
      cursor: pointer;
      &:hover {
        background: #1f23291a;
      }

      &:nth-child(2) {
        margin: 9px 0 0 0;
      }

      .model-name {
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
      }

      .done {
        margin-left: auto;
        display: none;
      }

      &.isActive {
        color: var(--ed-color-primary);

        .done {
          display: block;
        }
      }
    }
  }
}
</style>
