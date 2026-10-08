<script setup lang="ts"></script>

<template>
  <div class="base-container"><slot></slot></div>
</template>

<style scoped lang="less">
.base-container {
  background: var(--workspace-control-bg);
  border-radius: 12px;
  padding: 12px;
  margin-top: 16px;
}
</style>
