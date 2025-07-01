<script lang="ts" setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import arrow_down from '@/assets/svg/arrow-down.svg'
import dashboard_info from '@/assets/svg/dashboard-info.svg'
import icon_edit_outlined from '@/assets/svg/icon_edit_outlined.svg'
import icon_delete from '@/assets/svg/icon_delete.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import ParamsForm from './ParamsForm.vue'
import { modelTypeOptions } from '@/entity/CommonEntity.ts'

withDefaults(
  defineProps<{
    activeName: string
  }>(),
  {
    activeName: '',
  }
)

interface Options {
  label: string
  value: string
}

interface ParamsForm {
  name: string
  id: string
}

const modelForm = reactive({
  id: '',
  name: '',
  type: 0,
  api_key: '',
  endpoint: '',
  max_context_window: 0,
  temperature: 0,
  status: false,
  description: '',
})
let isCreate = false
const modelRef = ref()
const paramsFormRef = ref()
const advancedSetting = ref([] as ParamsForm[])
const modelList = ref([] as Options[])
const paramsFormDrawer = ref(false)
const advancedSettingExpand = ref(false)

const handleParamsEdite = (ele?: any) => {
  isCreate = false
  paramsFormDrawer.value = true
  nextTick(() => {
    paramsFormRef.value.initForm(ele)
  })
}

const handleParamsCreate = () => {
  isCreate = true
  paramsFormDrawer.value = true
  nextTick(() => {
    paramsFormRef.value.initForm()
  })
}

const handleParamsDel = (item: any) => {
  advancedSetting.value = advancedSetting.value.filter((ele) => ele.name !== item.name)
}

const rules = {
  type: [
    {
      required: true,
      message: 'type',
      trigger: 'change',
    },
  ],
  endpoint: [{ required: true, message: 'endpoint', trigger: 'blur' }],
  modelName: [{ required: true, message: '请选择基础模型', trigger: 'blur' }],
  name: [{ required: true, message: '请给基础模型设置一个名称', trigger: 'blur' }],
  api_key: [{ required: true, message: 'api_key', trigger: 'blur' }],
}

onMounted(() => {
  setTimeout(() => {
    modelRef.value.clearValidate()
  }, 100)
})

const addParams = () => {
  paramsFormRef.value.submit()
}

const submit = (item: any) => {
  if (isCreate) {
    advancedSetting.value.push({ ...item })
    cancel()
    return
  }
  for (const key in advancedSetting.value) {
    const element = advancedSetting.value[key]
    if (element.id === item.id) {
      Object.assign(element, { ...item })
    }
  }

  cancel()
}

const cancel = () => {
  paramsFormDrawer.value = false
}

const initForm = (item: any) => {
  modelForm.id = ''
  modelRef.value.clearValidate()
  Object.assign(modelForm, { ...item })
}
const emits = defineEmits(['submit'])

const submitModle = () => {
  modelRef.value.validate((res: any) => {
    if (res) {
      emits('submit', {
        ...modelForm,
        temperature: modelForm.temperature / 100,
        advancedSetting: [...advancedSetting.value],
      })
    }
  })
}

defineExpose({
  initForm,
  submitModle,
})
</script>

<template>
  <div class="model-form">
    <div class="model-name">{{ activeName }}</div>
    <div class="form-content">
      <el-form
        ref="modelRef"
        :rules="rules"
        label-position="top"
        :model="modelForm"
        style="width: 100%"
      >
        <el-form-item class="custom-require flex-inline" prop="name">
          <template #label
            ><span class="custom-require_danger">模型名称</span>
            <el-tooltip effect="dark" content="自定义的模型名称" placement="right">
              <el-icon style="margin-left: 4px" size="16">
                <dashboard_info></dashboard_info>
              </el-icon>
            </el-tooltip>
          </template>
          <el-input v-model="modelForm.name" />
        </el-form-item>
        <el-form-item prop="type" label="模型类型">
          <el-select v-model="modelForm.type" style="width: 100%">
            <el-option
              v-for="item in modelTypeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item class="custom-require" prop="modelName">
          <template #label
            ><span class="custom-require_danger">基础模型</span>
            <span class="enter">列表中未列出的模型，直接输入模型名称，回车即可添加</span>
          </template>
          <el-select v-model="modelForm.type" style="width: 100%">
            <el-option
              v-for="item in modelList"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item prop="endpoint" label="API 域名">
          <el-input v-model="modelForm.endpoint" />
        </el-form-item>
        <el-form-item prop="api_key" label="API Key">
          <el-input type="password" show-password v-model="modelForm.api_key" />
        </el-form-item>
      </el-form>
      <div
        @click="advancedSettingExpand = !advancedSettingExpand"
        class="advance-setting"
        :class="advancedSettingExpand && 'expand'"
      >
        高级设置
        <el-icon size="16">
          <arrow_down></arrow_down>
        </el-icon>
      </div>
      <div v-if="advancedSettingExpand" class="model-params">
        模型参数
        <span @click="handleParamsCreate" class="add">
          <el-icon size="16">
            <icon_add_outlined></icon_add_outlined>
          </el-icon>
          添加
        </span>
      </div>

      <div v-if="advancedSettingExpand" class="params-table">
        <el-table :data="advancedSetting" style="width: 100%">
          <el-table-column prop="params" label="参数" width="280" />
          <el-table-column prop="name" label="显示名称" width="280" />
          <el-table-column prop="value" label="参数值" />
          <el-table-column fixed="right" width="80" class-name="operation-column_text" label="操作">
            <template #default="scope">
              <el-button text @click="handleParamsEdite(scope.row)" type="primary">
                <el-icon size="16">
                  <icon_edit_outlined></icon_edit_outlined>
                </el-icon>
              </el-button>
              <el-button text @click="handleParamsDel(scope.row)" type="primary">
                <el-icon size="16">
                  <icon_delete></icon_delete>
                </el-icon>
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
    <el-drawer :size="600" v-model="paramsFormDrawer" title="添加参数">
      <ParamsForm @submit="submit" ref="paramsFormRef"></ParamsForm>
      <template #footer>
        <el-button @click="cancel" secondary> 取消 </el-button>
        <el-button @click="addParams" type="primary"> 添加 </el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.model-form {
  width: calc(100% - 280px);
  position: absolute;
  right: 0;
  top: 56px;
  height: 100%;
  .model-name {
    height: 56px;
    width: 100%;
    padding-left: 24px;
    border-bottom: 1px solid #1f232926;
    font-weight: 500;
    font-size: 16px;
    line-height: 24px;
    display: flex;
    align-items: center;
  }
  .form-content {
    width: 800px;
    margin: 0 auto;
    padding-top: 24px;

    .ed-form-item--default {
      margin-bottom: 16px;

      &.is-error {
        margin-bottom: 40px;
      }
    }

    :deep(
      .custom-require.ed-form-item.is-required:not(.is-no-asterisk).asterisk-right
        > .ed-form-item__label:after
    ) {
      display: none;
    }

    :deep(.flex-inline .ed-form-item__label) {
      display: inline-flex;
      align-items: center;
    }

    .enter {
      font-weight: 400;
      font-size: 14px;
      line-height: 22px;
      color: #ff8800;
      margin-left: 8px;
    }

    .custom-require_danger::after {
      color: var(--ed-color-danger);
      content: '*';
      margin-left: 2px;
    }

    .advance-setting {
      display: flex;
      align-items: center;
      font-weight: 500;
      font-size: 14px;
      line-height: 22px;
      cursor: pointer;

      .ed-icon {
        margin-left: 8px;
      }

      &.expand {
        .ed-icon {
          transform: rotate(180deg);
        }
      }
    }

    .model-params {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-weight: 400;
      font-size: 14px;
      line-height: 22px;
      margin: 16px 0 8px 0;

      .add {
        display: flex;
        align-items: center;
        cursor: pointer;
      }

      .ed-icon {
        margin-right: 4px;
      }
    }

    .params-table {
      border-radius: 6px;
      border: 1px solid #dee0e3;
      border-top: none;
      border-bottom: none;
    }

    .operation-column_text {
      .ed-button {
        color: #646a73;
        height: 24px;
      }
      .ed-button:not(.is-disabled):hover {
        background: #1f23291a;
      }
      .ed-button + .ed-button {
        margin-left: 4px;
      }
    }
  }
}
</style>
