<script setup lang="ts">
import ChatBlock from './ChatBlock.vue'
import {ChatInfo} from "@/api/chat.ts";
import {computed, onMounted, ref} from "vue";
import {datasourceApi} from "@/api/datasource.ts";
import DatasourceItemCard from '../ds/DatasourceItemCard.vue'

const props = withDefaults(defineProps<{
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
      type: props.currentChat.engine_type
    }
  }
  return undefined
})

const emits = defineEmits(["update:modelValue"])

function selectDs(ds: any) {
  if (editable.value) {
    emits("update:modelValue", ds.id)
  }
}

function listDs() {
  datasourceApi.list().then((res) => {
    dsList.value = res
  })
}

function showDs() {
  listDs()

}


onMounted(() => {
  listDs()
})

</script>

<template>
  <ChatBlock>
    <div>你好，我是SQLBot，很高兴为你服务</div>
    <div class="sub">我可以帮忙查询数据、生成图表、检测数据异常、预测数据等，请选择一个数据源，开启智能问数吧～</div>
    <template v-if="editable">
      <template v-if="dsList.length>0">
        <div class="ds-select-row">
          <div>选择数据源</div>
          <el-button @click="showDs" link type="primary">查看更多</el-button>
        </div>
        <div class="ds-row-container">
          <template v-for="(item, _index) in dsList" :key="_index">
            <DatasourceItemCard :ds="item" @click="selectDs(item)" v-if="_index<3 || item?.id===modelValue"
                                class="ds-card" :class="[item?.id===modelValue? 'ds-card-selected': '']"/>
          </template>
        </div>
      </template>
      <div v-else>
        数据源为空，请新建后再开启智能问数！
      </div>
    </template>
    <template v-else>
      <div class="ds-select-row">
        <div>已选择数据源</div>
      </div>
      <div class="ds-row-container">
        <DatasourceItemCard :ds="ds"/>
      </div>
    </template>
  </ChatBlock>
</template>

<style scoped lang="less">
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
  border-color: var(--ed-color-primary-light-5);
}


</style>