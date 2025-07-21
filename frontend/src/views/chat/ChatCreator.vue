<script setup lang="ts">
import { chatApi, ChatInfo } from '@/api/chat.ts'
import { onMounted, ref } from 'vue'
import { datasourceApi } from '@/api/datasource.ts'
import DatasourceItemCard from '../ds/DatasourceItemCard.vue'

const props = withDefaults(
  defineProps<{
    hidden?: boolean
  }>(),
  {
    hidden: false,
  }
)

const dsList = ref<Array<any>>([])

const emits = defineEmits(['onChatCreated'])

function listDs() {
  datasourceApi.list().then((res) => {
    dsList.value = res
  })
}

const dialogVisible = ref(false)

const DatasourceListRef = ref()

const innerDs = ref()

const loading = ref(false)

function showDs() {
  listDs()
  dialogVisible.value = true
}

function hideDs() {
  innerDs.value = undefined
  dialogVisible.value = false
}

function selectDsInDialog(ds: any) {
  innerDs.value = ds.id
}

function confirmSelectDs() {
  if (innerDs.value) {
    createChat(innerDs.value)
  }
}

function createChat(datasource: number) {
  loading.value = true
  chatApi
    .startChat({
      datasource: datasource,
    })
    .then((res) => {
      const chat: ChatInfo | undefined = chatApi.toChatInfo(res)
      if (chat == undefined) {
        throw Error('chat is undefined')
      }
      emits('onChatCreated', chat)
      hideDs()
    })
    .catch((e) => {
      console.error(e)
    })
    .finally(() => {
      loading.value = false
    })
}

onMounted(() => {
  if (props.hidden) {
    return
  }
  listDs()
})

defineExpose({
  showDs,
  hideDs,
  createChat,
})
</script>

<template>
  <div v-if="!hidden">
    <el-drawer
      ref="DatasourceListRef"
      v-model="dialogVisible"
      direction="btt"
      :close-on-press-escape="false"
      :close-on-click-modal="false"
      destroy-on-close
      :show-close="false"
      size="100%"
    >
      <template #header>
        <div>
          <div>Choose Datasource</div>
        </div>
      </template>
      <el-scrollbar v-loading="loading">
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
          <el-button :disabled="loading" @click="hideDs">Cancel</el-button>
          <el-button
            type="primary"
            :disabled="loading || innerDs === undefined"
            @click="confirmSelectDs"
          >
            Confirm
          </el-button>
        </div>
      </template>
    </el-drawer>
  </div>
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
