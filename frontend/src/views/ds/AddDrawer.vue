<script lang="ts" setup>
import { ref, nextTick } from 'vue'
import { datasourceApi } from '@/api/datasource'
import { useI18n } from 'vue-i18n'
import icon_close_outlined from '@/assets/svg/operate/ope-close.svg'
import DatasourceList from './DatasourceList.vue'
import DatasourceListSide from './DatasourceListSide.vue'
import DatasourceForm from './DatasourceForm.vue'

const { t } = useI18n()
const datasourceConfigVisible = ref(false)
const activeStep = ref(0)
const currentType = ref('')
const editDatasource = ref(false)
const activeName = ref('')
const activeType = ref('')
const datasourceFormRef = ref()

const beforeClose = () => {
  datasourceConfigVisible.value = false
  activeStep.value = 0
  datasourceApi.cancelRequests()
}
const clickDatasource = (ele: any) => {
  activeStep.value = 1
  activeName.value = ele.name
  activeType.value = ele.type
}

const clickDatasourceSide = (ele: any) => {
  activeName.value = ele.name
  activeType.value = ele.type
}

const emits = defineEmits(['search'])

const refresh = () => {
  activeName.value = ''
  activeStep.value = 0
  activeType.value = ''
  datasourceConfigVisible.value = false
  emits('search')
}

const handleEditDatasource = (res: any) => {
  activeStep.value = 1
  datasourceConfigVisible.value = true
  editDatasource.value = true
  currentType.value = res.type_name
  nextTick(() => {
    datasourceFormRef.value.initForm(res)
  })
}

const handleAddDatasource = () => {
  editDatasource.value = false
  datasourceConfigVisible.value = true
}

const changeActiveStep = (val: number) => {
  activeStep.value = val > 2 ? 2 : val
}

defineExpose({
  handleEditDatasource,
  handleAddDatasource,
})
</script>

<template>
  <el-drawer
    v-model="datasourceConfigVisible"
    :close-on-click-modal="false"
    destroy-on-close
    size="calc(100% - 100px)"
    modal-class="datasource-drawer-fullscreen"
    direction="btt"
    :before-close="beforeClose"
    :show-close="false"
  >
    <template #header="{ close }">
      <span style="white-space: nowrap">{{
        editDatasource
          ? t('datasource.mysql_data_source', { msg: currentType })
          : $t('datasource.new_data_source')
      }}</span>
      <div v-if="!editDatasource" class="flex-center" style="width: 100%">
        <el-steps custom style="max-width: 800px; flex: 1" :active="activeStep" align-center>
          <el-step>
            <template #title> {{ $t('ds.form.choose_database_type') }} </template>
          </el-step>
          <el-step>
            <template #title> {{ $t('datasource.configuration_information') }} </template>
          </el-step>
          <el-step>
            <template #title> {{ $t('ds.form.choose_tables') }} </template>
          </el-step>
        </el-steps>
      </div>
      <el-icon class="ed-dialog__headerbtn mrt" style="cursor: pointer" @click="close">
        <icon_close_outlined></icon_close_outlined>
      </el-icon>
    </template>
    <DatasourceList v-if="activeStep === 0" @click-datasource="clickDatasource"></DatasourceList>
    <DatasourceListSide
      v-if="activeStep === 1 && !editDatasource"
      :active-name="activeName"
      @click-datasource="clickDatasourceSide"
    ></DatasourceListSide>
    <DatasourceForm
      v-if="[1, 2].includes(activeStep)"
      ref="datasourceFormRef"
      :is-data-table="false"
      :active-step="activeStep"
      :active-name="activeName"
      :active-type="activeType"
      @refresh="refresh"
      @close="beforeClose"
      @change-active-step="changeActiveStep"
    ></DatasourceForm>
  </el-drawer>
</template>

<style lang="less">
.datasource-drawer-fullscreen {
  color-scheme: var(--theme-color-scheme);

  .ed-drawer,
  .ed-drawer__header,
  .ed-drawer__body,
  .ed-drawer__footer {
    background: var(--workspace-card-bg) !important;
    color: var(--workspace-text-primary) !important;
  }

  .ed-drawer__header {
    border-bottom: 1px solid var(--workspace-border);
    margin-bottom: 0;
    padding: 12px 16px;
  }

  .ed-drawer__body {
    padding: 0 !important;
    background: var(--workspace-card-bg) !important;
    color: var(--workspace-text-primary) !important;
  }

  .ed-drawer__footer {
    border-top: 1px solid var(--workspace-border);
  }

  .ed-drawer__title,
  .datasouce-list,
  .model-list_side,
  .model-form,
  .select-data_table {
    color: var(--workspace-text-primary) !important;
  }

  .ed-dialog__headerbtn,
  .mrt,
  .ed-drawer__close,
  .ed-drawer__close-btn {
    color: var(--workspace-text-secondary) !important;
  }

  .is-process .ed-step__line {
    background-color: var(--ed-color-primary) !important;
  }

  .ed-step__title,
  .ed-step__head {
    color: var(--workspace-text-secondary) !important;
  }

  .ed-step__head.is-process,
  .ed-step__title.is-process,
  .ed-step__head.is-finish,
  .ed-step__title.is-finish {
    color: var(--ed-color-primary) !important;
  }

  .ed-form-item__label,
  .ed-radio,
  .ed-checkbox,
  .ed-checkbox__label,
  .ed-radio__label,
  .ed-switch__label {
    color: var(--workspace-text-primary) !important;
  }

  .datasouce-list {
    .title {
      color: var(--workspace-text-primary) !important;
    }

    .model {
      background: var(--workspace-card-bg) !important;
      border-color: var(--workspace-border) !important;
      color: var(--workspace-text-primary) !important;

      &:hover {
        background: var(--workspace-panel-bg) !important;
        box-shadow: 0 6px 24px 0 #1f232914 !important;
      }
    }
  }

  .model-list_side {
    background: var(--workspace-card-bg) !important;
    border-right-color: var(--workspace-border) !important;

    .model {
      color: var(--workspace-text-primary) !important;

      &:hover {
        background: var(--workspace-control-bg) !important;
      }

      &.isActive {
        background: var(--theme-primary-soft-bg) !important;
        color: var(--theme-accent-text) !important;
      }
    }
  }

  .model-form {
    background: var(--workspace-card-bg) !important;
    color: var(--workspace-text-primary) !important;

    .model-name,
    .select-data_table .title {
      color: var(--workspace-text-primary) !important;
      border-bottom-color: var(--workspace-border) !important;
    }

    .draw-foot {
      background-color: var(--workspace-card-bg) !important;
      border-top-color: var(--workspace-border) !important;
    }

    .pdf-card,
    .select-data_table .container {
      background: var(--workspace-card-bg) !important;
      border-color: var(--workspace-border) !important;
      color: var(--workspace-text-primary) !important;
    }

    .select-data_table .select-all {
      background: var(--workspace-control-bg) !important;
      border-bottom-color: var(--workspace-border) !important;
      color: var(--workspace-text-primary) !important;
    }

    .list-item_primary {
      background: var(--workspace-card-bg) !important;
      color: var(--workspace-text-primary) !important;

      &:hover {
        background: var(--workspace-control-bg) !important;
      }
    }
  }

}
</style>
