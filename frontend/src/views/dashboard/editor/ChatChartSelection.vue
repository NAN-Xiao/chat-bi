<template>
  <el-drawer
    v-model="dialogShow"
    direction="btt"
    size="90%"
    trigger="click"
    :title="t('dashboard.add_chart')"
    modal-class="custom-drawer"
    @closed="handleClose()"
  >
    <div>Preview</div>

    <template #footer>
      <el-row class="multiplexing-footer">
        <el-col class="adapt-count">
          <span>{{ t('dashboard.chart_selected', [selectComponentCount]) }} </span>
        </el-col>
        <el-button class="close-button" @click="dialogShow = false">{{
          t('common.cancel')
        }}</el-button>
        <el-button
          type="primary"
          :disabled="!selectComponentCount"
          class="confirm-button"
          @click="saveMultiplexing"
          >{{ t('common.save') }}</el-button
        >
      </el-row>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
const dialogShow = ref(false)
const curDvType = ref('dashboard')
const { t } = useI18n()
const selectComponentCount = computed(() => Object.keys(state.curMultiplexingComponents).length)
const state = reactive({
  curMultiplexingComponents: {},
})
const dialogInit = (dvType = 'dashboard') => {
  curDvType.value = dvType
  dialogShow.value = true
  state.curMultiplexingComponents = {}
}

const saveMultiplexing = () => {
  dialogShow.value = false
}
const handleClose = () => {}
defineExpose({
  dialogInit,
})
</script>

<style lang="less" scoped>
.close-button {
  position: absolute;
  top: 18px;
  right: 120px;
}
.confirm-button {
  position: absolute;
  top: 18px;
  right: 20px;
}
.multiplexing-area {
  width: 100%;
  height: 100%;
}
.multiplexing-footer {
  position: relative;
}

.adapt-count {
  position: absolute;
  top: 18px;
  left: 20px;
  color: #646a73;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
}

.adapt-select {
  position: absolute;
  top: 18px;
  right: 220px;
}
.adapt-text {
  font-size: 14px;
  font-weight: 400;
  color: #1f2329;
  line-height: 22px;
}
</style>

<style lang="less">
.custom-drawer {
  .ed-drawer__footer {
    height: 64px !important;
    padding: 0 !important;
    box-shadow: 0 -1px 0px #d7d7d7 !important;
  }

  .ed-drawer__body {
    padding: 0 0 64px 0 !important;
  }
}
</style>
