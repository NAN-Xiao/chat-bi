<script lang="ts" setup>
import folder from '@/assets/svg/folder.svg'
import {type SQTreeNode} from '@/views/dashboard/utils/treeNode'
import {ref, reactive, computed} from 'vue'
import {saveDashboardResource} from "@/views/dashboard/utils/canvasUtils.ts";
import {dashboardApi} from "@/api/dashboard.ts";
import _ from "lodash";

const emits = defineEmits(['finish'])
const state = reactive({
  id: null,
  opt: null,
  placeholder: '',
  nodeType: 'folder',
  parentSelect: false,
  resourceFormNameLabel: 'Name',
  dialogTitle: '',
  tData: [],
  tDataSource: [],
  nameList: [],
  targetInfo: null,
  attachParams: null
})

const getTitle = (opt: string) => {
  switch (opt) {
    case 'newLeaf':
      return 'New Dashboard'
    case 'newFolder':
      return 'New Folder'
    case 'rename':
      return 'Rename'
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
  const params = {node_type: 'folder'}
  dashboardApi.list_resource(params).then((res) => {
    state.tData = res || []
    state.tDataSource = [...state.tData]
  })
}

const optInit = (params: any) => {
  // @ts-ignore
  state.dialogTitle = getTitle(params.opt)
  state.opt = params.opt
  state.id = params.id
  state.parentSelect = params.parentSelect
  state.targetInfo = params.data
  state.nodeType = params.nodeType || 'folder'
  resourceDialogShow.value = true
  // @ts-ignore
  resourceForm.name = params.name || getResourceNewName(params.opt)
  resourceForm.pid = params.pid || 'root'
  if (params.parentSelect) {
    getTree()
  }
}

const resourceDialogShow = ref(false)
const loading = ref(false)
const resourceForm = reactive({
  id: null,
  pid: '',
  pName: '',
  name: 'New Dashboard'
})

const resourceFormRules = ref({
      name: [
        {
          required: true,
          message: state.placeholder,
          trigger: 'change'
        },
        {
          required: true,
          message: state.placeholder,
          trigger: 'blur'
        },
        {
          min: 1,
          max: 64,
          message: 'Chart limit 1-64',
          trigger: 'change'
        },
        {required: true, trigger: 'blur'}
      ],
      pid: [
        {
          required: true,
          message: 'Please select',
          trigger: 'blur'
        }
      ]
    }
)

const resetForm = () => {
  state.dialogTitle = ''
  resourceForm.name = ''
  resourceForm.pid = ''
  resourceDialogShow.value = false
}

const propsTree = {
  value: 'id',
  label: 'name',
  children: 'children',
  // @ts-ignore
  isLeaf: node => !node.children?.length
}

const showPid = computed(() => {
  return state.opt && ['newLeaf'].includes(state.opt) && state.parentSelect
})

const saveResource = () => {
  const params = {
    id: state.id,
    node_type: state.nodeType,
    name: resourceForm.name,
    opt: state.opt,
    pid: resourceForm.pid,
    type: 'dashboard',
    level: state.nodeType === 'folder' ? 0 : 1,
  }
  saveDashboardResource(params, function (rsp: any) {
    const messageTips = state.opt === 'rename' ? 'Update Success' : 'Save Success'
    ElMessage({
      type: 'success',
      message: messageTips,
    })
    emits('finish', {opt: state.opt, resourceId: rsp.id})
    resetForm()
  })
}

const nodeClick = (data: SQTreeNode) => {
  resourceForm.pid = data.id as string
  resourceForm.pName = data.name as string
}

const filterMethod = (value: any) => {
  // @ts-ignore
  state.tData = state.tDataSource.filter(item => item.name.includes(value))
}

defineExpose({
  optInit
})

</script>

<template>
  <el-dialog
      class="create-dialog"
      :title="state.dialogTitle"
      v-model="resourceDialogShow"
      width="420px"
      :before-close="resetForm"
      @submit.prevent
  >
    <el-form
        v-loading="loading"
        label-position="top"
        require-asterisk-position="right"
        ref="resource"
        :model="resourceForm"
        :rules="resourceFormRules"
    >
      <el-form-item :label="state.resourceFormNameLabel" prop="name">
        <el-input
            @keydown.stop
            @keyup.stop
            :placeholder="state.placeholder"
            v-model="resourceForm.name"
        />
      </el-form-item>
      <el-form-item v-if="showPid" :label="'Folder'" prop="pid">
        <el-tree-select
            style="width: 100%"
            @keydown.stop
            @keyup.stop
            v-model="resourceForm.pid"
            :data="state.tData"
            :props="propsTree"
            @node-click="nodeClick"
            :filter-method="filterMethod"
            :render-after-expand="false"
            filterable
        >
          <template #default="{ data: { name } }">
            <span class="custom-tree-node">
              <el-icon>
                <Icon name="dv-folder"><folder class="svg-icon custom-tree-folder"/></Icon>
              </el-icon>
              <span :title="name">{{ name }}</span>
            </span>
          </template>
        </el-tree-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button secondary @click="resetForm()">Cancel</el-button>
      <el-button type="primary" @click="saveResource()">Confirm</el-button>
    </template>
  </el-dialog>
</template>

<style lang="less" scoped>
.tree-content {
  width: 552px;
  height: 380px;
  border: 1px solid #dee0e3;
  border-radius: 4px;
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
  color: rgb(255, 198, 10)
}
</style>
