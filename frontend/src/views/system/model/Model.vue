<script lang="ts" setup>
import { ref, computed, shallowRef, reactive, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import icon_admin_outlined from '@/assets/svg/icon_admin_outlined.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_close_outlined from '@/assets/svg/operate/ope-close.svg'
import Card from './Card.vue'
import ModelForm from './ModelForm.vue'
import { modelApi } from '@/api/system'
import { getModelTypeName } from '@/entity/CommonEntity.ts'
import { useI18n } from 'vue-i18n'
import { get_supplier } from '@/entity/supplier'
import { highlightKeyword } from '@/utils/xss'

interface Model {
  name: string
  model_type: string
  base_model: string
  id?: string
  default_model: boolean
  supplier: number
  usage_count?: number
  total_tokens?: number
}

const { t } = useI18n()
const keywords = ref('')
const defaultModelKeywords = ref('')
const modelConfigvVisible = ref(false)
const searchLoading = ref(false)
const editModel = ref(false)
const modelFormRef = ref()
reactive({
  form: {
    id: '',
    name: '',
    model_type: 0,
    api_key: '',
    api_domain: '',
  },
  selectedIds: [],
})
const modelList = shallowRef([] as Model[])

const modelListWithSearch = computed(() => {
  if (!keywords.value) return modelList.value
  return modelList.value.filter((ele) =>
    ele.name.toLowerCase().includes(keywords.value.toLowerCase())
  )
})
const beforeClose = () => {
  modelConfigvVisible.value = false
}
const defaultModelListWithSearch = computed(() => {
  let tempModelList = modelList.value
  if (defaultModelKeywords.value) {
    tempModelList = tempModelList.filter((ele) =>
      ele.name.toLowerCase().includes(defaultModelKeywords.value.toLowerCase())
    )
  }
  return tempModelList.map((item: any) => {
    item['supplier_item'] = get_supplier(item.supplier)
    return item
  })
})

const saveModelPayload = async (payload: any | any[]) => {
  const items = Array.isArray(payload) ? payload : [payload]
  if (!items.length) return
  const res = await modelApi.queryAll()
  const selectedNames = items.map((item: any) => item.name)
  const duplicateSelectedNames = selectedNames.filter(
    (name: string, index: number) => selectedNames.indexOf(name) !== index
  )
  if (duplicateSelectedNames.length) {
    ElMessage.error(t('model.duplicate_model_names', { names: duplicateSelectedNames.join(', ') }))
    return
  }
  const duplicateNames = items
    .filter((item: any) =>
      res.some((ele: any) => String(ele.id) !== String(item.id || '') && ele.name === item.name)
    )
    .map((item: any) => item.name)
  if (duplicateNames.length) {
    ElMessage.error(t('model.duplicate_model_names', { names: duplicateNames.join(', ') }))
    return
  }

  if (items.length > 1 || !items[0].id) {
    await Promise.all(items.map((item: any) => modelApi.add(item)))
    beforeClose()
    search()
    ElMessage({
      type: 'success',
      message: t('model.add_models_success', { count: items.length }),
    })
    return
  }

  await modelApi.edit(items[0])
  beforeClose()
  search()
  ElMessage({
    type: 'success',
    message: t('common.save_success'),
  })
}

const handleDefaultModelChange = (item: any) => {
  const current_default_node = modelList.value.find((ele: Model) => ele.default_model)
  if (current_default_node?.id === item.id) {
    return
  }
  ElMessageBox.confirm(t('model.system_default_model', { msg: item.name }), {
    confirmButtonType: 'primary',
    tip: t('model.operate_with_caution'),
    confirmButtonText: t('datasource.confirm'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
    callback: (val: string) => {
      if (val === 'confirm') {
        modelApi.setDefault(item.id).then(() => {
          ElMessage.success(t('model.set_successfully'))
          search()
        })
      }
    },
  })
}

const formatKeywords = (item: string) => {
  // Use XSS-safe highlight function
  return highlightKeyword(item, defaultModelKeywords.value, 'isSearch')
}
const handleAddModel = () => {
  editModel.value = false
  modelConfigvVisible.value = true
  nextTick(() => {
    modelFormRef.value?.initForm()
  })
}
const handleEditModel = (row: any) => {
  editModel.value = true
  modelApi.query(row.id).then((res: any) => {
    modelConfigvVisible.value = true
    nextTick(() => {
      modelFormRef.value.initForm({ ...res })
    })
  })
}

const handleDefault = (row: any) => {
  if (row.default_model) return
  ElMessageBox.confirm(t('model.system_default_model', { msg: row.name }), {
    confirmButtonType: 'primary',
    tip: t('model.operate_with_caution'),
    confirmButtonText: t('datasource.confirm'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
    callback: (val: string) => {
      if (val === 'confirm') {
        modelApi.setDefault(row.id).then(() => {
          ElMessage.success(t('model.set_successfully'))
          search()
        })
      }
    },
  })
}

const deleteHandler = (item: any) => {
  if (item.default_model) {
    ElMessageBox.confirm(t('model.del_default_tip', { msg: item.name }), {
      confirmButtonType: 'primary',
      tip: t('model.del_default_warn'),
      showConfirmButton: false,
      confirmButtonText: t('datasource.confirm'),
      cancelButtonText: t('datasource.got_it'),
      customClass: 'confirm-no_icon',
      autofocus: false,
      callback: (val: string) => {
        console.info(val)
      },
    })
    return
  }
  ElMessageBox.confirm(t('model.del_warn_tip', { msg: item.name }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('dashboard.delete'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
    callback: (value: string) => {
      if (value === 'confirm') {
        modelApi.delete(item.id).then(() => {
          ElMessage({
            type: 'success',
            message: t('dashboard.delete_success'),
          })
          search()
        })
      }
    },
  })
}

const cancel = () => {
  beforeClose()
}

const saveModel = () => {
  modelFormRef.value.submitModel()
}
const search = () => {
  searchLoading.value = true
  modelApi
    .queryAll()
    .then((res: any) => {
      modelList.value = res
    })
    .finally(() => {
      searchLoading.value = false
    })
}
search()

const submit = (item: any) => {
  saveModelPayload(item)
}

const modelTypeText = (row: Model) => {
  const modelType = getModelTypeName(row.model_type)
  return modelType.startsWith('modelType.') ? t(modelType) : modelType || '-'
}
</script>

<template>
  <div class="zhishu-table-container professional-container">
    <div class="tool-left">
      <span class="page-title">{{ t('model.ai_model_configuration') }}</span>
      <div class="search-bar">
        <el-input
          v-model="keywords"
          clearable
          class="model-search-input"
          :placeholder="$t('datasource.search')"
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined class="svg-icon" />
            </el-icon>
          </template>
        </el-input>

        <el-popover popper-class="system-default_model" placement="bottom-end">
          <template #reference>
            <el-button secondary>
              <template #icon>
                <icon_admin_outlined></icon_admin_outlined>
              </template>
              {{ t('model.system_default_model_de') }}
            </el-button></template
          >
          <div class="popover">
            <el-input
              v-model="defaultModelKeywords"
              clearable
              style="width: 100%; margin-right: 12px"
              :placeholder="t('datasource.search_by_name')"
            >
              <template #prefix>
                <el-icon>
                  <icon_searchOutline_outlined class="svg-icon" />
                </el-icon>
              </template>
            </el-input>
            <div class="popover-content">
              <div
                v-for="ele in defaultModelListWithSearch"
                :key="ele.name"
                class="popover-item"
                :class="ele.default_model && 'isActive'"
                @click="handleDefaultModelChange(ele)"
              >
                <img :src="ele.supplier_item.icon" width="24px" height="24px" />
                <div class="model-name ellipsis" v-html="formatKeywords(ele.name)"></div>
                <el-icon size="16" class="done">
                  <icon_done_outlined></icon_done_outlined>
                </el-icon>
              </div>
              <div v-if="!defaultModelListWithSearch.length" class="popover-item empty">
                {{ t('model.relevant_results_found') }}
              </div>
            </div>
          </div>
        </el-popover>

        <el-button type="primary" @click="handleAddModel">
          <template #icon>
            <icon_add_outlined></icon_add_outlined>
          </template>
          {{ t('model.add_model') }}
        </el-button>
      </div>
    </div>

    <div v-loading="searchLoading" class="model-card-area">
      <template v-if="modelListWithSearch.length">
        <el-row :gutter="16" class="model-card-row">
          <el-col
            v-for="item in modelListWithSearch"
            :key="item.id || item.name"
            :xs="24"
            :sm="12"
            :md="12"
            :lg="8"
            :xl="6"
            class="model-card-col"
          >
            <Card
              :name="item.name"
              :model-type="modelTypeText(item)"
              :base-model="item.base_model || '-'"
              :id="item.id"
              :is-default="item.default_model"
              :supplier="item.supplier"
              @default="handleDefault(item)"
              @edit="handleEditModel(item)"
              @del="deleteHandler"
            />
          </el-col>
        </el-row>
      </template>
      <EmptyBackground
        v-else-if="!searchLoading"
        class="model-card-empty"
        :description="
          keywords ? $t('datasource.relevant_content_found') : $t('common.no_model_yet')
        "
        img-type="tree"
      />
    </div>
    <el-drawer
      v-model="modelConfigvVisible"
      :close-on-click-modal="false"
      size="640px"
      modal-class="model-drawer-right"
      direction="rtl"
      destroy-on-close
      :before-close="beforeClose"
      :show-close="false"
    >
      <template #header="{ close }">
        <span style="white-space: nowrap">{{
          editModel
            ? $t('dashboard.edit') + $t('common.empty') + t('model.ai_model_configuration')
            : t('model.add_model')
        }}</span>
        <el-icon class="ed-dialog__headerbtn mrt" style="cursor: pointer" @click="close">
          <icon_close_outlined></icon_close_outlined>
        </el-icon>
      </template>
      <ModelForm
        v-if="modelConfigvVisible"
        ref="modelFormRef"
        :edit-model="editModel"
        @submit="submit"
      ></ModelForm>
      <template #footer>
        <el-button secondary @click="cancel"> {{ $t('common.cancel') }} </el-button>
        <el-button type="primary" @click="saveModel"> {{ $t('common.save') }} </el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.zhishu-table-container {
  width: 100%;
  height: 100%;
  position: relative;

  .tool-left {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    gap: 16px;

    .page-title {
      flex: 0 0 auto;
      font-weight: 500;
      font-size: 20px;
      line-height: 28px;
      white-space: nowrap;
    }
  }

  .search-bar {
    flex: 0 0 auto;
    display: flex;
    align-items: center;

    .model-search-input {
      width: 240px;
      margin-right: 12px;
    }
  }

  .model-card-area {
    box-sizing: border-box;
    width: calc(100% + 24px);
    min-height: 160px;
    max-height: calc(100vh - 156px);
    margin: -8px -12px 0;
    padding: 8px 12px 28px;
    overflow-x: hidden;
    overflow-y: auto;

    .model-card-row {
      width: auto;
    }

    .model-card-col {
      margin-bottom: 24px;
    }

    .model-card-empty {
      min-height: 220px;
      background: #ffffff;
      border: 1px solid var(--workspace-border, #e2eaf4);
      border-radius: 8px;
    }
  }

  @media (max-width: 720px) {
    .tool-left {
      align-items: stretch;
      flex-direction: column;
    }

    .search-bar {
      flex-wrap: wrap;
      justify-content: flex-start;

      .model-search-input {
        width: 100%;
        margin-right: 0;
      }
    }
  }
}
</style>

<style lang="less">
.system-default_model.system-default_model {
  padding: 4px 0;
  width: 325px !important;
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border: 1px solid #dee0e3;
  .ed-input {
    .ed-input__wrapper {
      box-shadow: none;
    }

    border-bottom: 1px solid #1f232926;
  }

  .popover {
    .popover-content {
      padding: 4px;
      max-height: 300px;
      overflow-y: auto;
    }
    .popover-item {
      height: 36px;
      display: flex;
      align-items: center;
      padding-left: 12px;
      padding-right: 8px;
      margin-bottom: 2px;
      position: relative;
      border-radius: 6px;
      cursor: pointer;
      &:not(.empty):hover {
        background: #1f23291a;
      }

      &.empty {
        font-weight: 400;
        font-size: 15px;
        line-height: 24px;
        color: #8f959e;
        cursor: default;
      }

      .model-name {
        margin-left: 8px;
        font-weight: 400;
        font-size: 15px;
        line-height: 24px;
        max-width: 220px;
      }

      .done {
        margin-left: auto;
        display: none;
      }

      .isSearch {
        color: var(--ed-color-primary);
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

.model-drawer-right {
  .ed-drawer__body {
    padding: 0;
  }
  .is-process .ed-step__line {
    background-color: var(--ed-color-primary);
  }
}
.confirm-no_icon {
  border-radius: 12px;
  padding: 24px;
  .tip {
    margin-top: 24px;
  }
}
</style>
