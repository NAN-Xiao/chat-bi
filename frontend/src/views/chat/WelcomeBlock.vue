<script setup lang="ts">
import ChatBlock from './ChatBlock.vue'
import { ChatInfo } from '@/api/chat.ts'
import { computed, onMounted, ref } from 'vue'
import { datasourceApi } from '@/api/datasource.ts'
import DatasourceItemCard from '../ds/DatasourceItemCard.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const props = withDefaults(
  defineProps<{
    modelValue?: number
    currentChat: ChatInfo
  }>(),
  {}
)

const dsList = ref<Array<any>>([])

const editable = computed(() => {
  return props.currentChat?.id === undefined
})

const ds = computed(() => {
  for (let i = 0; i < dsList.value.length; i++) {
    const item = dsList.value[i]
    if (props.modelValue === item.id) {
      return item
    }
  }
  if (props.currentChat && props.currentChat.datasource !== undefined) {
    return {
      id: props.currentChat.datasource,
      name: props.currentChat.datasource_name ?? 'Datasource does not exist',
      type: props.currentChat.engine_type,
    }
  }
  return undefined
})

const emits = defineEmits(['update:modelValue'])

function selectDs(ds: any) {
  if (editable.value) {
    emits('update:modelValue', ds.id)
  }
}

function listDs() {
  datasourceApi.list().then((res) => {
    dsList.value = res
  })
}

const dialogVisible = ref(false)

const DatasourceListRef = ref()

const innerDs = ref()

function showDs() {
  innerDs.value = props.modelValue
  listDs()
  dialogVisible.value = true
}

function selectDsInDialog(ds: any) {
  innerDs.value = ds.id
}

function confirmSelectDs() {
  if (innerDs.value) {
    emits('update:modelValue', innerDs.value)
    dialogVisible.value = false
  }
}

onMounted(() => {
  listDs()
})
</script>

<template>
  <ChatBlock>
    <div class="welcome-content">
      <div>{{ t('qa.greeting') }}</div>
      <div class="sub">{{ t('qa.description') }}</div>
      <template v-if="editable">
        <template v-if="dsList.length > 0">
          <div class="ds-select-row">
            <div>{{ t('qa.select_datasource') }}</div>
            <el-button link type="primary" @click="showDs">{{ t('qa.view_more') }}</el-button>
          </div>
          <div class="ds-row-container">
            <template v-for="(item, _index) in dsList" :key="_index">
              <DatasourceItemCard
                v-if="_index < 3 || item?.id === modelValue"
                :ds="item"
                class="ds-card"
                :class="[item?.id === modelValue ? 'ds-card-selected' : '']"
                @click="selectDs(item)"
              />
            </template>
          </div>
        </template>
        <div v-else>
          {{ t('qa.empty_datasource') }}
        </div>
      </template>
      <template v-else>
        <div class="ds-select-row">
          <div>{{ t('qa.selected_datasource') }}</div>
        </div>
        <div class="ds-row-container">
          <DatasourceItemCard :ds="ds" />
        </div>
      </template>
    </div>

    <el-drawer
      ref="DatasourceListRef"
      v-model="dialogVisible"
      title="Choose Datasource"
      direction="btt"
      size="100%"
    >
      <el-scrollbar>
        <div class="ds-row-container">
          <template v-for="(item, _index) in dsList" :key="_index">
            <DatasourceItemCard
              :ds="item"
              class="ds-card"
              :class="[item?.id === innerDs ? 'ds-card-selected' : '']"
              @click="selectDsInDialog(item)"
            />
          </template>
        </div>
      </el-scrollbar>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible = false">Cancel</el-button>
          <el-button type="primary" @click="confirmSelectDs"> Confirm </el-button>
        </div>
      </template>
    </el-drawer>
  </ChatBlock>
</template>

<style scoped lang="less">
.welcome-content {
  padding: 12px;
}

.sub {
  color: grey;
  font-size: 0.8em;
}

.ds-select-row {
  display: flex;
  align-items: center;
  flex-direction: row;
  justify-content: space-between;
}

.ds-row-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 24px;
}

.ds-card {
  cursor: pointer;
}

.ds-card-selected {
  box-shadow: 0 1px 3px var(--ed-color-primary-light-5);
  border: 1px solid var(--ed-color-primary-light-5);
}
</style>
