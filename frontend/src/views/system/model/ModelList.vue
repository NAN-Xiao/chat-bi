<script lang="ts" setup>
import { ref, shallowRef, computed } from 'vue'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import icon_Azure_OpenAI_colorful from '@/assets/model/icon_Azure_OpenAI_colorful.png'
interface Model {
  name: string
  modleType: string
  baseModle: string
  img?: string
}
const keywords = ref('')
const modelList = shallowRef([
  {
    img: icon_Azure_OpenAI_colorful,
    name: '千帆大模型-chinese',
  },
  {
    img: icon_Azure_OpenAI_colorful,
    name: '千帆大模-chinese',
  },
] as Model[])
const modelListWithSearch = computed(() => {
  if (!keywords.value) return modelList.value
  return modelList.value.filter((ele) =>
    ele.name.toLowerCase().includes(keywords.value.toLowerCase())
  )
})
const emits = defineEmits(['clickModel'])
const handleModelClick = (item: any) => {
  emits('clickModel', item)
}
</script>

<template>
  <div class="model-list">
    <div class="title">选择供应商</div>
    <el-input
      clearable
      v-model="keywords"
      style="width: 100%; margin-right: 12px"
      placeholder="搜索"
    >
      <template #prefix>
        <el-icon>
          <icon_searchOutline_outlined class="svg-icon" />
        </el-icon>
      </template>
    </el-input>
    <div class="list-content">
      <div
        @click="handleModelClick(ele)"
        class="model"
        v-for="ele in modelListWithSearch"
        :key="ele.name"
      >
        <img width="32px" height="32px" :src="ele.img" />
        <span class="name">{{ ele.name }}</span>
      </div>
      <EmptyBackground
        v-if="!!keywords && !modelListWithSearch.length"
        :description="'没有找到相关内容'"
        img-type="tree"
        style="width: 100%;margin-top: 100px;"
      />
    </div>
  </div>
</template>

<style lang="less" scoped>
.model-list {
  width: 800px;
  margin: 0 auto;
  height: 100%;
  padding-top: 24px;
  .title {
    font-weight: 500;
    font-size: 16px;
    line-height: 24px;
    margin-bottom: 16px;
  }

  .list-content {
    margin-top: 16px;
    display: flex;
    justify-content: space-between;
    height: calc(100% - 40px);

    .model {
      width: 392px;
      height: 64px;
      display: flex;
      align-items: center;
      padding-left: 16px;
      margin-bottom: 16px;
      flex-wrap: wrap;
      border: 1px solid #dee0e3;
      border-radius: 4px;
      cursor: pointer;
      &:hover {
        box-shadow: 0px 6px 24px 0px #1f232914;
      }
      .name {
        margin-left: 12px;
        font-weight: 500;
        font-size: 14px;
        line-height: 22px;
      }
    }
  }
}
</style>
