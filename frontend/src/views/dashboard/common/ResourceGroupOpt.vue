<script lang="ts" setup>
import folder from '@/assets/svg/folder.svg'
import { type SQTreeNode } from '@/views/dashboard/utils/treeNode'
import { computed, reactive, ref } from 'vue'
import { saveDashboardResource } from '@/views/dashboard/utils/canvasUtils.ts'
import { dashboardApi } from '@/api/dashboard.ts'
import { useI18n } from 'vue-i18n'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { useUserStore } from '@/stores/user'

const { t } = useI18n()
const datasourceContext = useDatasourceContextStore()
const userStore = useUserStore()
const emits = defineEmits(['finish'])
const resource = ref(null)
const state = reactive({
  id: null,
  opt: null,
  placeholder: '',
  nodeType: 'folder',
  parentSelect: false,
  resourceFormNameLabel: t('dashboard.dashboard_name'),
  dialogTitle: '',
  tData: [],
  tDataSource: [],
  nameList: [],
  targetInfo: null,
  attachParams: null,
  datasource: null as number | string | null | undefined,
  platformTemplateList: [] as any[],
})

const getTitle = (opt: string) => {
  switch (opt) {
    case 'newLeaf':
      return t('dashboard.new_dashboard')
    case 'newFolder':
      return t('dashboard.new_folder')
    case 'rename':
      return t('dashboard.rename_dashboard')
    default:
      return
  }
}

const getResourceNewName = (opt: string) => {
  switch (opt) {
    case 'newLeaf':
      return 'New Dashboard'
    case 'newFolder':
      return 'New Folder'
    default:
      return
  }
}

const getTree = async () => {
  await datasourceContext.loadDatasources()
  const params = { node_type: 'folder', datasource: state.datasource || datasourceContext.datasourceId }
  dashboardApi.list_resource(params).then((res) => {
    state.tData = res || []
    state.tDataSource = [...state.tData]
  })
}

const optInit = (params: any) => {
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  state.dialogTitle = getTitle(params.opt)
  state.opt = params.opt
  state.id = params.id
  state.parentSelect = params.parentSelect
  state.targetInfo = params.data
  state.nodeType = params.nodeType || 'folder'
  state.datasource = params.datasource || datasourceContext.datasourceId
  state.placeholder = params.placeholder || ''
  resourceDialogShow.value = true
  resourceForm.name = params.name ?? getResourceNewName(params.opt)
  resourceForm.pid = params.pid || 'root'
  resourceForm.createMode =
    canCreateFromTemplate.value && !canCreateBlankDashboard.value ? 'template' : 'blank'
  resourceForm.templateId = ''
  if (params.parentSelect) {
    getTree()
  }
  if (params.opt === 'newLeaf' && canCreateFromTemplate.value) {
    loadPlatformTemplates()
  }
}

const resourceDialogShow = ref(false)
const loading = ref(false)
const resourceForm = reactive({
  id: null,
  pid: '',
  pName: '',
  name: 'New Dashboard',
  createMode: 'blank',
  templateId: '',
})

const resourceFormRules = ref({
  name: [
    {
      required: true,
      min: 1,
      max: 64,
      message: t('dashboard.length_limit64'),
      trigger: 'change',
    },
  ],
  pid: [
    {
      required: true,
      message: 'Please select',
      trigger: 'blur',
    },
  ],
  templateId: [
    {
      required: true,
      message: t('dashboard.select_platform_template'),
      trigger: 'change',
    },
  ],
})

const resetForm = () => {
  state.dialogTitle = ''
  state.placeholder = ''
  state.platformTemplateList = []
  resourceForm.name = ''
  resourceForm.pid = ''
  resourceForm.createMode = 'blank'
  resourceForm.templateId = ''
  resourceDialogShow.value = false
}

const propsTree = {
  value: 'id',
  label: 'name',
  children: 'children',
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  isLeaf: (node) => !node.children?.length,
}

const showPid = false
const isNewDashboard = computed(() => state.opt === 'newLeaf')
const canCreateBlankDashboard = computed(() => datasourceContext.canCreateDashboard === true)
const canCreateFromTemplate = computed(() => userStore.isPlatformWorkspaceDelegate && isNewDashboard.value)
const isTemplateCreateMode = computed(
  () => canCreateFromTemplate.value && resourceForm.createMode === 'template'
)

const activeRules = computed(() => {
  const rules: Record<string, any> = {
    name: resourceFormRules.value.name,
    pid: resourceFormRules.value.pid,
  }
  if (isTemplateCreateMode.value) {
    rules.templateId = resourceFormRules.value.templateId
  }
  return rules
})

const loadPlatformTemplates = async () => {
  loading.value = true
  try {
    const res = await dashboardApi.platform_template_list({
      requestOptions: { silent: true },
    })
    state.platformTemplateList = Array.isArray(res) ? res : []
  } finally {
    loading.value = false
  }
}

const onCreateModeChange = () => {
  if (isTemplateCreateMode.value && !state.platformTemplateList.length) {
    loadPlatformTemplates()
  }
}

const onTemplateChange = (templateId: string) => {
  const template = state.platformTemplateList.find((item: any) => String(item.id) === String(templateId))
  if (!template) return
  resourceForm.name = template.name || resourceForm.name
}

const copyTemplateToWorkspace = () => {
  loading.value = true
  dashboardApi
    .platform_template_copy_to_workspace({
      template_id: resourceForm.templateId,
      name: resourceForm.name,
    })
    .then((rsp: any) => {
      ElMessage({
        type: 'success',
        message: t('dashboard.platform_template_use_success'),
      })
      emits('finish', {
        opt: state.opt,
        resourceId: rsp.id,
      })
      resetForm()
    })
    .finally(() => {
      loading.value = false
    })
}

const saveResource = () => {
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  resource.value?.validate((result) => {
    if (result) {
      if (isTemplateCreateMode.value) {
        copyTemplateToWorkspace()
        return
      }
      if (isNewDashboard.value && !canCreateBlankDashboard.value) {
        ElMessage.warning(t('chat.no_dashboard_create_permission'))
        return
      }
      const params = {
        id: state.id,
        node_type: state.nodeType,
        name: resourceForm.name,
        opt: state.opt,
        pid: resourceForm.pid,
        datasource: state.datasource || datasourceContext.datasourceId,
        type: 'dashboard',
        level: state.nodeType === 'folder' ? 0 : 1,
      }
      saveDashboardResource(params, function (rsp: any) {
        const messageTips = t('common.save_success')
        ElMessage({
          type: 'success',
          message: messageTips,
        })
        emits('finish', {
          opt: state.opt,
          resourceId: rsp.id,
        })
        resetForm()
      })
    }
  })
}

const nodeClick = (data: SQTreeNode) => {
  resourceForm.pid = data.id as string
  resourceForm.pName = data.name as string
}

const filterMethod = (value: any) => {
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  state.tData = state.tDataSource.filter((item) => item.name.includes(value))
}

defineExpose({
  optInit,
})
</script>

<template>
  <el-dialog
    v-model="resourceDialogShow"
    class="create-dialog"
    :title="state.dialogTitle"
    width="420px"
    :before-close="resetForm"
    append-to-body
    @submit.prevent
  >
    <el-form
      ref="resource"
      v-loading="loading"
      label-position="top"
      require-asterisk-position="right"
      :model="resourceForm"
      :rules="activeRules"
      class="last"
      @submit.prevent
    >
      <el-form-item
        v-if="canCreateFromTemplate"
        :label="t('dashboard.dashboard_create_mode')"
        prop="createMode"
      >
        <el-radio-group v-model="resourceForm.createMode" @change="onCreateModeChange">
          <el-radio value="blank" :disabled="!canCreateBlankDashboard">
            {{ t('dashboard.blank_dashboard') }}
          </el-radio>
          <el-radio value="template">{{ t('dashboard.create_from_platform_template') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item
        v-if="isTemplateCreateMode"
        :label="t('dashboard.platform_template_mark')"
        required
        prop="templateId"
      >
        <el-select
          v-model="resourceForm.templateId"
          filterable
          class="template-select"
          :placeholder="t('dashboard.select_platform_template')"
          @change="onTemplateChange"
          @keydown.stop
          @keyup.stop
        >
          <el-option
            v-for="item in state.platformTemplateList"
            :key="item.id"
            :label="item.name"
            :value="item.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="state.resourceFormNameLabel" prop="name">
        <el-input
          v-model="resourceForm.name"
          :placeholder="state.placeholder"
          clearable
          @keydown.stop
          @keyup.stop
        />
      </el-form-item>
      <el-form-item v-if="showPid" :label="'Folder'" prop="pid">
        <el-tree-select
          v-model="resourceForm.pid"
          style="width: 100%"
          :data="state.tData"
          :props="propsTree"
          :filter-method="filterMethod"
          :render-after-expand="false"
          filterable
          @keydown.stop
          @keyup.stop
          @node-click="nodeClick"
        >
          <template #default="{ data: { name } }">
            <span class="custom-tree-node">
              <el-icon>
                <Icon name="dv-folder"><folder class="svg-icon custom-tree-folder" /></Icon>
              </el-icon>
              <span :title="name">{{ name }}</span>
            </span>
          </template>
        </el-tree-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button secondary @click="resetForm()">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" @click="saveResource()">{{ t('common.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<style lang="less" scoped>
.tree-content {
  width: 552px;
  height: 380px;
  border: 1px solid #dee0e3;
  border-radius: 6px;
  padding: 8px;
  overflow-y: auto;

  .empty-search {
    width: 100%;
    margin-top: 57px;
    display: flex;
    flex-direction: column;
    align-items: center;

    img {
      width: 100px;
      height: 100px;
      margin-bottom: 8px;
    }

    span {
      font-family: var(--de-custom_font, 'PingFang');
      font-size: 14px;
      font-weight: 400;
      line-height: 22px;
      color: #646a73;
    }
  }
}

.custom-tree-node {
  display: flex;
  align-items: center;

  span {
    margin-left: 8.75px;
    width: 120px;
    white-space: nowrap;
    text-overflow: ellipsis;
    overflow: hidden;
  }
}

.custom-tree-folder {
  color: rgb(255, 198, 10);
}

.template-select {
  width: 100%;
}
</style>
