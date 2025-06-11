<script setup lang="ts">
import dashboardInfoSvg from '@/assets/svg/dashboard-info.svg'
import icon_pc_outlined from '@/assets/svg/icon_pc_outlined.svg'
import icon_edit_outlined from '@/assets/svg/icon_edit_outlined.svg'
import DashboardDetailInfo from "@/views/dashboard/common/DashboardDetailInfo.vue";

const emit = defineEmits(['reload', 'download', 'downloadAsAppTemplate'])
const preview = () => {
  window.open(`#/dashboard-preview?resourceId=${props.dashboardInfo.id}`, '_blank')
}
const edit = () => {
  window.open(`#/canvas?resourceId=${props.dashboardInfo.id}`, '_blank')
}
const props = defineProps({
  dashboardInfo: {
    type: Object,
    required: true
  }
})

</script>

<template>
  <div class="preview-head flex-align-center">
    <div class="canvas-name ellipsis">{{ dashboardInfo.name }}</div>
    <el-divider style="margin: 5px 10px 0 17px" direction="vertical"/>
    <span class="create-area" style="line-height: 22px">Creator:{{ dashboardInfo.createName }}</span>
    <div style="padding-top: 4px" class="create-area flex-align-center">
      <el-popover show-arrow :offset="8" placement="bottom" width="400" trigger="hover">
        <template #reference>
          <el-icon class="info-tips">
            <dashboardInfoSvg class="svg-icon"/>
          </el-icon>
        </template>
        <DashboardDetailInfo :dashboard-info="dashboardInfo"></DashboardDetailInfo>
      </el-popover>
    </div>
    <div class="canvas-opt-button">
      <el-button secondary @click="preview">
        <template #icon>
          <icon name="icon_pc_outlined">
            <icon_pc_outlined class="svg-icon"/>
          </icon>
        </template>
        Preview
      </el-button>
      <el-button class="custom-button" type="primary" @click="edit">
        <template #icon>
          <Icon name="icon_edit_outlined">
            <icon_edit_outlined class="svg-icon"/>
          </Icon>
        </template>
        Edit
      </el-button
      >
    </div>
  </div>
</template>

<style lang="less">
.pad12 {
  .ed-dropdown-menu__item {
    padding: 5px 36px 5px 12px !important;

    .ed-icon {
      margin-right: 8px;
    }

    .arrow-right_icon {
      position: absolute;
      right: 12px;
      margin-right: 0;
    }

    &:has(.arrow-right_icon) {
      width: 100%;
    }
  }
}

.preview-head {
  display: flex;
  width: 100%;
  min-width: 300px;
  height: 56px;
  padding: 16px 24px;
  border-bottom: 1px solid rgba(31, 35, 41, 0.15);

  .canvas-name {
    max-width: 200px;
    font-size: 16px;
    font-weight: 500;
  }

  .canvas-have-update {
    background-color: rgba(52, 199, 36, 0.2);
    color: rgba(44, 169, 31, 1);
    font-weight: 400;
    font-size: 12px;
    line-height: 20px;
    vertical-align: middle;
    padding: 0 4px;
    margin-left: 8px;
  }

  .custom-icon {
    cursor: pointer;
    margin-left: 8px;
  }

  .create-area {
    color: #646a73;
    font-weight: 400;
    font-size: 14px;
  }

  .canvas-opt-button {
    display: flex;
    justify-content: right;
    align-items: center;
    flex: 1;

    .head-more-icon {
      color: #1f2329;
      margin-left: 12px;
      cursor: pointer;
      font-size: 20px;
      border-radius: 4px;
      position: relative;

      &:hover {
        &::after {
          content: '';
          position: absolute;
          top: -4px;
          left: -4px;
          border-radius: 4px;
          height: 28px;
          width: 28px;
          background: #1f23291a;
        }
      }
    }
  }
}

.info-tips {
  margin-left: 4px;
  font-size: 16px;
  color: #646a73;
}

.custom-button {
  margin-left: 12px;
}

.flex-align-center {
  & + & {
    margin-left: 4px;
  }
}
</style>
