<script lang="ts" setup>
import { onMounted, ref, computed, shallowRef } from 'vue'
import icon_close_outlined from '@/assets/svg/operate/ope-close.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import { chatApi, ChatInfo } from '@/api/chat.ts'
import { datasourceApi } from '@/api/datasource.ts'
import Card from '@/views/ds/ChatCard.vue'

const props = withDefaults(
  defineProps<{
    hidden?: boolean
  }>(),
  {
    hidden: false,
  }
)

const datasourceConfigvVisible = ref(false)
const keywords = ref('')
const datasourceList = shallowRef([] as any[])
const datasourceListWithSearch = computed(() => {
  if (!keywords.value) return datasourceList.value
  return datasourceList.value.filter((ele) =>
    ele.name.toLowerCase().includes(keywords.value.toLowerCase())
  )
})
const beforeClose = () => {
  datasourceConfigvVisible.value = false
  keywords.value = ''
}

const emits = defineEmits(['onChatCreated'])

function listDs() {
  datasourceApi.list().then((res) => {
    datasourceList.value = res
  })
}

const dialogVisible = ref(false)

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
})

defineExpose({
  showDs,
  hideDs,
  createChat,
})
</script>

<template>
  <el-drawer
    v-model="datasourceConfigvVisible"
    :close-on-click-modal="false"
    size="calc(100% - 100px)"
    modal-class="datasource-drawer-chat"
    direction="btt"
    :before-close="beforeClose"
    :show-close="false"
  >
    <template #header="{ close }">
      <span style="white-space: nowrap">{{ $t('qa.select_datasource') }}</span>
      <div class="flex-center" style="width: 100%">
        <el-input
          v-model="keywords"
          clearable
          style="width: 320px"
          :placeholder="$t('datasource.search')"
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined />
            </el-icon>
          </template>
        </el-input>
      </div>
      <el-icon style="cursor: pointer" @click="close">
        <icon_close_outlined></icon_close_outlined>
      </el-icon>
    </template>
    <div class="card-content">
      <Card
        v-for="ele in datasourceListWithSearch"
        :id="ele.id"
        :key="ele.id"
        :name="ele.name"
        :type="ele.type"
        :type-name="ele.type_name"
        :num="ele.num"
        :description="ele.description"
        @select-ds="selectDsInDialog(ele)"
      ></Card>
    </div>
    <template #footer>
      <div class="dialog-footer">
        <el-button secondary :disabled="loading" @click="hideDs">{{
          $t('common.cancel')
        }}</el-button>
        <el-button
          type="primary"
          :disabled="loading || innerDs === undefined"
          @click="confirmSelectDs"
        >
          {{ $t('datasource.confirm') }}
        </el-button>
      </div>
    </template>
  </el-drawer>
</template>

<style lang="less">
.datasource-drawer-chat {
  .card-content {
    display: flex;
    flex-wrap: wrap;
    max-height: calc(100% - 40px);
    overflow-y: auto;
  }
}
</style>
