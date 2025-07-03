<script lang="ts" setup>
import { ref, computed, shallowRef, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import arrow_down from '@/assets/svg/arrow-down.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import DataTable from './DataTable.vue'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_close_outlined from '@/assets/svg/operate/ope-close.svg'
import DatasourceList from './DatasourceList.vue'
import DatasourceListSide from './DatasourceListSide.vue'
import DatasourceForm from './DatasourceForm.vue'
import { datasourceApi } from '@/api/datasource'
import Card from './Card.vue'
import { dsTypeWithImg } from './js/ds-type'

interface Datasource {
  name: string
  type: string
  img: string
  rate?: string
  id?: string
}

const keywords = ref('')
const defaultDatasourceKeywords = ref('')
const datasourceConfigvVisible = ref(false)
const editDatasource = ref(false)
const activeStep = ref(0)
const activeName = ref('')
const datasourceFormRef = ref()

const datasourceList = shallowRef([] as Datasource[])
const defaultDatasourceList = shallowRef(dsTypeWithImg as (Datasource & { img: string })[])

const currentDefaultDatasource = ref('')
const datasourceListWithSearch = computed(() => {
  if (!keywords.value) return datasourceList.value
  return datasourceList.value.filter((ele) =>
    ele.name.toLowerCase().includes(keywords.value.toLowerCase())
  )
})
const beforeClose = () => {
  datasourceConfigvVisible.value = false
}
const defaultDatasourceListWithSearch = computed(() => {
  if (!defaultDatasourceKeywords.value) return defaultDatasourceList.value
  return defaultDatasourceList.value.filter((ele) =>
    ele.name.toLowerCase().includes(defaultDatasourceKeywords.value.toLowerCase())
  )
})

const handleDefaultDatasourceChange = (item: any) => {
  currentDefaultDatasource.value = item.name
}

const formatKeywords = (item: string) => {
  if (!defaultDatasourceKeywords.value) return item
  return item.replaceAll(
    defaultDatasourceKeywords.value,
    `<span class="isSearch">${defaultDatasourceKeywords.value}</span>`
  )
}

const handleEditDatasource = (res: any) => {
  activeStep.value = 1
  datasourceConfigvVisible.value = true
  editDatasource.value = true
  nextTick(() => {
    datasourceFormRef.value.initForm(res)
  })
}

const handleAddDatasource = () => {
  editDatasource.value = false
  datasourceConfigvVisible.value = true
}

const deleteHandler = (id: any) => {
  ElMessageBox.confirm('Are you sure to delete?', 'Warning', {
    confirmButtonText: 'OK',
    cancelButtonText: 'Cancel',
    type: 'warning',
  })
    .then(() => {
      datasourceApi.delete(id).then(() => {
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

const clickDatasource = (ele: any) => {
  activeStep.value = 1
  activeName.value = ele.name
}

const clickDatasourceSide = (ele: any) => {
  activeName.value = ele.name
  activeStep.value = 1
}

const search = () => {
  datasourceApi.list().then((res: any) => {
    datasourceList.value = res
  })
}
search()

const submit = (item: any) => {
  if (!item.id) {
    datasourceApi.add(item).then(() => {
      beforeClose()
      search()
      ElMessage({
        type: 'success',
        message: 'Add completed',
      })
    })
    return
  }
  datasourceApi.edit(item).then(() => {
    beforeClose()
    search()
    ElMessage({
      type: 'success',
      message: 'Edit completed',
    })
  })
}

const currentDataTable = ref()
const dataTableDetail = (ele: any) => {
  currentDataTable.value = ele
}
</script>

<template>
  <div v-show="!currentDataTable" class="datasource-config">
    <div class="datasource-methods">
      <span class="title">数据源</span>
      <div class="button-input">
        <el-input
          v-model="keywords"
          clearable
          style="width: 240px; margin-right: 12px"
          placeholder="搜索"
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined class="svg-icon" />
            </el-icon>
          </template>
        </el-input>

        <el-popover popper-class="system-default_datasource" placement="bottom">
          <template #reference>
            <el-button secondary>
              全部类型
              <el-icon style="margin-left: 8px">
                <arrow_down></arrow_down>
              </el-icon> </el-button
          ></template>
          <div class="popover">
            <el-input
              v-model="defaultDatasourceKeywords"
              clearable
              style="width: 100%; margin-right: 12px"
              placeholder="通过名称搜索"
            >
              <template #prefix>
                <el-icon>
                  <icon_searchOutline_outlined class="svg-icon" />
                </el-icon>
              </template>
            </el-input>
            <div class="popover-content">
              <div
                v-for="ele in defaultDatasourceListWithSearch"
                :key="ele.name"
                class="popover-item"
                :class="currentDefaultDatasource === ele.name && 'isActive'"
                @click="handleDefaultDatasourceChange(ele)"
              >
                <img :src="ele.img" width="24px" height="24px" />
                <div class="datasource-name" v-html="formatKeywords(ele.name)"></div>
                <el-icon size="16" class="done">
                  <icon_done_outlined></icon_done_outlined>
                </el-icon>
              </div>
              <div v-if="!defaultDatasourceListWithSearch.length" class="popover-item empty">
                没有找到相关结果
              </div>
            </div>
          </div>
        </el-popover>

        <el-button type="primary" @click="handleAddDatasource">
          <template #icon>
            <icon_add_outlined></icon_add_outlined>
          </template>
          新建数据源
        </el-button>
      </div>
    </div>
    <EmptyBackground
      v-if="!!keywords && !datasourceListWithSearch.length"
      :description="'没有找到相关内容'"
      img-type="tree"
    />

    <div v-else class="card-content">
      <Card
        v-for="ele in datasourceListWithSearch"
        :id="ele.id"
        :key="ele.id"
        :name="ele.name"
        :type="ele.type"
        :rate="ele.rate"
        @edit="handleEditDatasource(ele)"
        @del="deleteHandler"
        @data-table-detail="dataTableDetail(ele)"
      ></Card>
    </div>
    <el-drawer
      v-model="datasourceConfigvVisible"
      :close-on-click-modal="false"
      size="calc(100% - 100px)"
      modal-class="datasource-drawer-fullscreen"
      direction="btt"
      :before-close="beforeClose"
      :show-close="false"
    >
      <template #header="{ close }">
        <span style="white-space: nowrap">新建数据源</span>
        <div v-if="!editDatasource" class="flex-center" style="width: 100%">
          <el-steps custom style="max-width: 500px; flex: 1" :active="activeStep" align-center>
            <el-step>
              <template #title> 选择数据源 </template>
            </el-step>
            <el-step>
              <template #title> 配置信息 </template>
            </el-step>
            <el-step>
              <template #title> 选择数据表 </template>
            </el-step>
          </el-steps>
        </div>
        <el-icon style="cursor: pointer" @click="close">
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
        :active-step="activeStep"
        :active-name="activeName"
        @submit="submit"
        @change-active-step="(val: number) => (activeStep = val)"
      ></DatasourceForm>
    </el-drawer>
  </div>
  <DataTable v-if="currentDataTable" :info="currentDataTable"></DataTable>
</template>

<style lang="less" scoped>
.datasource-config {
  height: calc(100% - 16px);
  .datasource-methods {
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
    flex-wrap: wrap;
  }
}
</style>

<style lang="less">
.system-default_datasource.system-default_datasource {
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

      .datasource-name {
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

.datasource-drawer-fullscreen {
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
