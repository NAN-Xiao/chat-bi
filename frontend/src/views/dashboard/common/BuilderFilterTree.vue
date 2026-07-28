<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue'
import BuilderFieldPicker from '@/views/dashboard/common/BuilderFieldPicker.vue'
import type { FieldOption } from './builderFieldPickerOptions'

type FilterLogic = 'and' | 'or'

type FilterNode = {
  id: string
  type?: 'rule' | 'group'
  field: string
  operator: string
  value: string
  logic?: FilterLogic
  children?: FilterNode[]
}

defineOptions({ name: 'BuilderFilterTree' })

const emits = defineEmits<{
  'update:logic': [value: FilterLogic]
}>()

const props = withDefaults(
  defineProps<{
    nodes: FilterNode[]
    logic?: FilterLogic
    fieldOptions: FieldOption[]
    operatorOptions: Array<{ label: string; value: string }>
    schemaLoading?: boolean
    level?: number
    removable?: boolean
    emptyText?: string
    showToolbar?: boolean
    pickerMode?: 'property' | 'filter-property'
    filterPropertyTabs?: Array<'all' | 'event' | 'user'>
  }>(),
  {
    logic: 'and',
    schemaLoading: false,
    level: 0,
    removable: true,
    emptyText: '暂无筛选条件',
    showToolbar: false,
    pickerMode: 'property',
    filterPropertyTabs: () => [],
  }
)

function nodeId(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyRule(): FilterNode {
  return {
    id: nodeId('filter'),
    type: 'rule',
    field: '',
    operator: 'eq',
    value: '',
    logic: 'and',
  }
}

function addRule(target: FilterNode[]) {
  target.push(emptyRule())
}

function removeNode(target: FilterNode[], index: number) {
  target.splice(index, 1)
}

function treeLogic() {
  return props.logic === 'or' ? 'or' : 'and'
}

function connectorLabel() {
  return treeLogic() === 'or' ? '或' : '且'
}

function toggleTreeLogic() {
  emits('update:logic', treeLogic() === 'or' ? 'and' : 'or')
}

function updateNodeLogic(node: FilterNode, value: FilterLogic) {
  node.logic = value
}

function isGroup(node: FilterNode) {
  return node.type === 'group' || Array.isArray(node.children)
}
</script>

<template>
  <div class="builder-filter-tree" :class="{ 'is-nested': level > 0 }">
    <div v-if="nodes.length" class="builder-filter-node-list">
      <button
        v-if="nodes.length > 1"
        type="button"
        class="builder-connector"
        :title="`点击切换为${treeLogic() === 'or' ? '且' : '或'}`"
        @click="toggleTreeLogic"
      >
        {{ connectorLabel() }}
      </button>
      <div
        v-for="(node, index) in nodes"
        :key="node.id"
        class="builder-filter-node"
        :class="{ 'is-group': isGroup(node) }"
      >
        <div v-if="isGroup(node)" class="builder-filter-group">
          <div class="builder-filter-group-head">
            <div class="builder-filter-group-actions">
              <el-button text class="builder-remove-button" @click="removeNode(nodes, index)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
          <BuilderFilterTree
            :nodes="node.children || []"
            :logic="node.logic"
            :field-options="fieldOptions"
            :operator-options="operatorOptions"
            :schema-loading="schemaLoading"
            :level="level + 1"
            :show-toolbar="true"
            :picker-mode="pickerMode"
            :filter-property-tabs="filterPropertyTabs"
            @update:logic="updateNodeLogic(node, $event)"
          />
        </div>
        <div v-else class="builder-filter-row">
          <BuilderFieldPicker
            v-model="node.field"
            class="builder-field-select"
            :mode="pickerMode"
            :options="fieldOptions"
            :filter-property-tabs="filterPropertyTabs"
            :loading="schemaLoading"
            placeholder="字段"
          />
          <el-select v-model="node.operator" class="builder-operator-select" size="small">
            <el-option
              v-for="item in operatorOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
          <el-input
            v-model="node.value"
            class="builder-filter-value"
            size="small"
            clearable
            placeholder="手动输入筛选值"
            @beforeinput.stop
            @keydown.stop
            @keyup.stop
            @paste.stop
          />
          <el-button text class="builder-remove-button" @click="removeNode(nodes, index)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
    </div>
    <div v-else class="builder-empty-row">{{ emptyText }}</div>
    <div v-if="showToolbar" class="builder-filter-toolbar">
      <el-button text class="builder-add-condition" @click="addRule(nodes)">
        <el-icon><Plus /></el-icon>
        <span>筛选条件</span>
      </el-button>
    </div>
  </div>
</template>

<style scoped lang="less">
.builder-filter-tree {
  position: relative;
  padding-left: 26px;
  font-size: 12px;
}

.builder-filter-tree::before {
  content: '';
  position: absolute;
  left: 11px;
  top: 8px;
  bottom: 10px;
  width: 1px;
  background: #d8dde7;
}

.builder-filter-tree.is-nested {
  margin-top: 6px;
}

.builder-filter-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  min-height: 28px;
  margin-top: 6px;
}

.builder-filter-node-list {
  position: relative;
  display: grid;
  gap: 8px;
}

.builder-filter-node {
  position: relative;
  min-width: 0;
}

.builder-connector {
  position: absolute;
  left: -26px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 1;
  display: inline-flex;
  width: 22px;
  height: 22px;
  align-items: center;
  justify-content: center;
  margin-top: 4px;
  padding: 0;
  border: 1px solid #315cff;
  border-radius: 11px;
  background: #fff;
  color: #315cff;
  cursor: pointer;
  font-size: 11px;
  line-height: 1;
  transition: background 0.16s ease, color 0.16s ease, box-shadow 0.16s ease;
}

.builder-connector:hover {
  background: #315cff;
  color: #fff;
  box-shadow: 0 0 0 3px rgba(49, 92, 255, 0.12);
}

.builder-filter-row {
  display: grid;
  grid-template-columns: minmax(150px, 1.15fr) 88px minmax(150px, 1fr) 24px;
  align-items: center;
  gap: 8px;
  min-height: 30px;
}

.builder-filter-group {
  min-width: 0;
  padding: 10px 12px 12px;
  border: 1px solid #e7eaf0;
  border-radius: 6px;
  background: #fafbff;
}

.builder-filter-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-height: 24px;
  margin-bottom: 6px;
}

.builder-filter-group-title {
  color: #2f3848;
  font-size: 12px;
  font-weight: 600;
}

.builder-filter-group-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.builder-field-select,
.builder-filter-value {
  width: 100%;
}

.builder-operator-select {
  width: 88px;
}

.builder-remove-button {
  min-width: 22px;
  height: 22px;
  padding: 0;
  color: #7c8493;
}

.builder-add-condition {
  height: 24px;
  padding: 0 5px;
  color: #315cff;
  font-size: 12px;
}

.builder-add-condition :deep(.ed-icon),
.builder-add-condition :deep(.el-icon) {
  margin-right: 4px;
}

.builder-empty-row {
  padding: 2px 0 2px;
  color: #9aa2af;
  font-size: 12px;
}

.builder-filter-tree :deep(.builder-field-picker-trigger) {
  width: 100%;
}
</style>
