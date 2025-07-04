<script lang="ts" setup>
import { ref, computed, shallowRef, reactive, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import icon_admin_outlined from '@/assets/svg/icon_admin_outlined.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import icon_Azure_OpenAI_colorful from '@/assets/model/icon_Azure_OpenAI_colorful.png'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_close_outlined from '@/assets/svg/operate/ope-close.svg'
import ModelList from './ModelList.vue'
import ModelListSide from './ModelListSide.vue'
import ModelForm from './ModelForm.vue'
import { modelApi } from '@/api/system'
import Card from './Card.vue'
import { getModelTypeName } from '@/entity/CommonEntity.ts'
import { useI18n } from 'vue-i18n'

interface Model {
  name: string
  type: string
  baseModle: string
  id?: string
}

const { t } = useI18n()
const keywords = ref('')
const defaultModelKeywords = ref('')
const modelConfigvVisible = ref(false)
const editModel = ref(false)
const activeStep = ref(0)
const activeName = ref('')
const modelFormRef = ref()

const state = reactive({
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
const modelList = shallowRef([] as Model[])
const defaultModelList = shallowRef([
  {
    img: icon_Azure_OpenAI_colorful,
    name: '千帆大模型-chinese',
  },
] as (Model & { img: string })[])

const currentDefaultModel = ref('')
const modelListWithSearch = computed(() => {
  if (!keywords.value) return modelList.value
  return modelList.value.filter((ele) =>
    ele.name.toLowerCase().includes(keywords.value.toLowerCase())
  )
})
const beforeClose = () => {
  modelConfigvVisible.value = false
  ElMessage.success(t('model.set_successfully'))
  // ElMessageBox.confirm(t('model.system_default_model', { msg: msg}), {
  //   confirmButtonType: 'primary',
  //   tip: t('model.operate_with_caution'),
  //   confirmButtonText: t('datasource.confirm'),
  //   cancelButtonText: t('common.cancel'),
  //   customClass: 'confirm-no_icon',
  //   autofocus: false,
  // })
  // ElMessageBox.confirm(t('model.system_default_model', { msg: msg}), {
  //   confirmButtonType: 'danger',
  //   confirmButtonText: t('dashboard.delete'),
  //   cancelButtonText: t('common.cancel'),
  //   customClass: 'confirm-no_icon',
  //   autofocus: false,
  // })
}
const defaultModelListWithSearch = computed(() => {
  if (!defaultModelKeywords.value) return defaultModelList.value
  return defaultModelList.value.filter((ele) =>
    ele.name.toLowerCase().includes(defaultModelKeywords.value.toLowerCase())
  )
})

const handleDefaultModelChange = (item: any) => {
  currentDefaultModel.value = item.name
}

const formatKeywords = (item: string) => {
  if (!defaultModelKeywords.value) return item
  return item.replaceAll(
    defaultModelKeywords.value,
    `<span class="isSearch">${defaultModelKeywords.value}</span>`
  )
}

const handleEditModel = (id: any) => {
  activeStep.value = 1
  modelApi.query(id).then((res: any) => {
    modelConfigvVisible.value = true
    nextTick(() => {
      modelFormRef.value.initForm({ ...res, temperature: res.temperature * 100 })
    })
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

const clickModel = (ele: any) => {
  activeStep.value = 1
  activeName.value = ele.name
}

const clickModelSide = (ele: any) => {
  activeName.value = ele.name
}

const cancel = () => {
  beforeClose()
}

const preStep = () => {
  activeStep.value = 0
}

const saveModel = () => {
  modelFormRef.value.submit()
}

const search = () => {
  modelApi.pager(state.pageInfo.currentPage, state.pageInfo.pageSize).then((res: any) => {
    modelList.value = res.items
    state.pageInfo.total = res.total
  })
}
search()

const submit = (item: any) => {
  if (!item.id) {
    modelApi.add(item).then(() => {
      beforeClose()
      search()
      ElMessage({
        type: 'success',
        message: 'Add completed',
      })
    })
    return
  }
  modelApi.edit(item).then(() => {
    beforeClose()
    search()
    ElMessage({
      type: 'success',
      message: 'Edit completed',
    })
  })
}
</script>

<template>
  <div class="model-config">
    <div class="model-methods">
      <span class="title">{{ t('model.ai_model_configuration') }}</span>
      <div class="button-input">
        <el-input
          v-model="keywords"
          clearable
          style="width: 240px; margin-right: 12px"
          :placeholder="$t('datasource.search')"
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined class="svg-icon" />
            </el-icon>
          </template>
        </el-input>

        <el-popover popper-class="system-default_model" placement="bottom">
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
                :class="currentDefaultModel === ele.name && 'isActive'"
                @click="handleDefaultModelChange(ele)"
              >
                <img :src="ele.img" width="24px" height="24px" />
                <div class="model-name" v-html="formatKeywords(ele.name)"></div>
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

        <el-button type="primary">
          <template #icon>
            <icon_add_outlined></icon_add_outlined>
          </template>
          {{ t('model.add_model') }}
        </el-button>
      </div>
    </div>
    <EmptyBackground
      v-if="!!keywords && !modelListWithSearch.length"
      :description="$t('datasource.relevant_content_found')"
      img-type="tree"
    />

    <div v-else class="card-content">
      <Card
        v-for="ele in modelListWithSearch"
        :id="ele.id"
        :key="ele.id"
        :name="ele.name"
        :modle-type="getModelTypeName(ele.type)"
        :base-modle="ele.baseModle"
        @edit="handleEditModel"
        @del="deleteHandler"
      ></Card>
    </div>
    <el-drawer
      v-model="modelConfigvVisible"
      :close-on-click-modal="false"
      size="calc(100% - 100px)"
      modal-class="model-drawer-fullscreen"
      direction="btt"
      :before-close="beforeClose"
      :show-close="false"
    >
      <template #header="{ close }">
        <span style="white-space: nowrap">{{ t('model.add_model') }}</span>
        <div v-if="!editModel" class="flex-center" style="width: 100%">
          <el-steps custom style="max-width: 500px; flex: 1" :active="activeStep" align-center>
            <el-step>
              <template #title> {{ t('model.select_supplier') }} </template>
            </el-step>
            <el-step>
              <template #title> {{ t('model.add_model') }} </template>
            </el-step>
          </el-steps>
        </div>
        <el-icon style="cursor: pointer" @click="close">
          <icon_close_outlined></icon_close_outlined>
        </el-icon>
      </template>
      <ModelList v-if="activeStep === 0" @click-model="clickModel"></ModelList>
      <ModelListSide
        v-if="activeStep === 1"
        :active-name="activeName"
        @click-model="clickModelSide"
      ></ModelListSide>
      <ModelForm
        v-if="activeStep === 1"
        ref="modelFormRef"
        :active-name="activeName"
        @submit="submit"
      ></ModelForm>
      <template #footer>
        <el-button secondary @click="cancel"> {{ $t('common.cancel') }} </el-button>
        <el-button secondary @click="preStep"> {{ $t('ds.previous') }} </el-button>
        <el-button type="primary" @click="saveModel"> {{ $t('common.save') }} </el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.model-config {
  height: calc(100% - 16px);
  .model-methods {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    .title {
      font-weight: 500;
      font-size: 20px;
      line-height: 28px;
    }
  }

  .card-content {
    display: flex;
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
    }
    .popover-item {
      height: 32px;
      display: flex;
      align-items: center;
      padding-left: 12px;
      padding-right: 8px;
      margin-bottom: 2px;
      position: relative;
      border-radius: 4px;
      cursor: pointer;
      &:not(.empty):hover {
        background: #1f23291a;
      }

      &.empty {
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        color: #8f959e;
        cursor: default;
      }

      .model-name {
        margin-left: 8px;
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
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

.model-drawer-fullscreen {
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
