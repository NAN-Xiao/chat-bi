<template>
  <div class="sqlbot-table-container professional-container">
    <div class="sqlbot-tool">
      <div class="tool-left">
        <el-input
          v-model="keyword"
          class="sqlbot-search"
          placeholder="Search"
          prefix-icon="el-icon-search"
          @keyup.enter.native="handleSearch"
        >
          <template #prefix>
            <el-icon class="el-input__icon"><search /></el-icon>
          </template>
        </el-input>
      </div>
      <div class="tool-right">
        <div class="tool-btn secondary-btn">
          <el-icon><IconOpeUpload /></el-icon>
          <span>Import Terminology</span>
        </div>
        <div class="tool-btn secondary-btn">
          <el-icon><IconOpeDownload /></el-icon>
          <span>Export Terminology</span>
        </div>
        <div class="tool-btn primary-btn">
          <el-icon><IconOpeAdd /></el-icon>
          <span>Add Terminology</span>
        </div>
      </div>
    </div>
    <div class="sqlbot-table">
      <el-table :data="state.tableData" style="width: 100%">
        <el-table-column prop="term" label="Term" width="280" />
        <el-table-column prop="definition" label="Definition"  />
        <el-table-column prop="domain" label="Domain" width="180" />
        <el-table-column prop="id" label="Actions" width="120" fixed="right">
          <template #default="scope">
            <div class="table-operate">
              <div class="opt-btn" @click="editHandler(scope.row.id)">
                <el-icon><IconOpeEdit /></el-icon>
              </div>
              <div class="opt-btn" @click="deleteHandler(scope.row.id)">
                <el-icon><IconOpeDelete /></el-icon>
              </div>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue';
import IconOpeUpload from '@/assets/svg/operate/ope-upload.svg';
import IconOpeDownload from '@/assets/svg/operate/ope-download.svg';
import IconOpeAdd from '@/assets/svg/operate/ope-add.svg';
import IconOpeEdit from '@/assets/svg/operate/ope-edit.svg';
import IconOpeDelete from '@/assets/svg/operate/ope-delete.svg';
import { Search } from '@element-plus/icons-vue'
const keyword = ref('')
const state = reactive({
  tableData: [
    {  
      term: 'Term 1',
      definition: 'Definition 1',
      domain: 'Domain 1',
      id: '1'
    },
    {
      term: 'Term 2',
      definition: 'Definition 2',
      domain: 'Domain 2',
      id: '2'
    },
    {
      term: 'Term 3',
      definition: 'Definition 3',
      domain: 'Domain 3',
      id: '3'
    }
  ]
})
const handleSearch = (e: any) => {
  console.log('search', e);
}
const editHandler = (id: any) => {
  console.log(id)
}
const deleteHandler = (id: any) => {
  console.log(id)
}
</script>

<style lang="less" scoped>
.sqlbot-table-container {
  width: 100%;
  height: 100%;
  .sqlbot-tool {
    height: 42px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    .tool-left {
      display: flex;
      align-items: center;
      .sqlbot-search {
        width: 300px;
        --el-input-inner-height: 40px !important;
        --el-input-border-radius: 24px;
        --el-input-bg-color: #f5f7fa;
        --el-input-border-color: #e5e8ed;        
      }
    }
    .tool-right {
      display: flex;
      align-items: center;
      column-gap: 12px;
      height: 35px;
      .secondary-btn {
        background: #f5f5f5;
        color: #333;
        border: 1px solid #ddd;
      }
      .primary-btn {
        background: #1890ff;
        color: white;
      }
      .tool-btn {
        display: flex;
        align-items: center;
        padding: 6px 16px;
        border-radius: 4px;
        cursor: pointer;
        outline: none;
        font-weight: 500;
        transition: all 0.3s;
        font-size: 14px;
        gap: 6px;
        &:hover {
          background-color: #f1f3f4;
        }
        &.default {
          color: #2d2e31;
          font-weight: 500;
          font-size: 14px;
          i {
            width: 20px;
            height: 20px;
          }
        }
      }
    }
  }
  .sqlbot-table {
    border-radius: 6px;
    :deep(.el-table) {
      --el-table-header-bg-color: #f5f7fa;
      --el-table-border-color: #ebeef5;
      --el-table-header-text-color: #606266;

      th {
        font-weight: 600;
        height: 48px;
      }

      td {
        height: 52px;
      }
    }
    .table-operate {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      .opt-btn {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #5f6368;
        cursor: pointer;
        transition: all 0.2s;
        background-color: #f1f3f4;
        border: none;
        font-size: 18px;
        &:hover {
          background-color: #e8f0fe;
          color: #4285f4;
        }
      }
    }
  }
}
</style>
