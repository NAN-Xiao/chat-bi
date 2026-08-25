<script setup lang="ts">
defineProps<{
  title: string
  index?: number
}>()
</script>

<template>
  <section class="knowledge-content-frame">
    <header class="content-frame-header">
      <div class="content-frame-heading">
        <span v-if="index !== undefined" class="content-frame-index">{{ index }}</span>
        <slot name="title">
          <span class="content-frame-title">{{ title }}</span>
        </slot>
      </div>
      <div v-if="$slots.actions" class="content-frame-actions">
        <slot name="actions" />
      </div>
    </header>
    <div class="content-frame-body">
      <slot />
    </div>
  </section>
</template>

<style scoped lang="less">
.knowledge-content-frame {
  width: 100%;
  min-width: 0;
  overflow: hidden;
  border: 1px solid #dfe3e8;
  border-radius: 8px;
  background: #fff;
}
.content-frame-header,
.content-frame-heading,
.content-frame-actions {
  display: flex;
  align-items: center;
}
.content-frame-header {
  min-height: 48px;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 10px;
  background: #f8f9fb;
}
.content-frame-heading {
  min-width: 0;
  gap: 8px;
}
.content-frame-index {
  flex: 0 0 24px;
  color: #667085;
  font-size: 12px;
}
.content-frame-title {
  min-width: 0;
  overflow: hidden;
  color: #344054;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.content-frame-actions {
  flex: 0 0 auto;
  gap: 4px;
}
.content-frame-body {
  min-width: 0;
  padding: 14px 12px 4px;
  border-top: 1px solid #eaecf0;
}

@media (max-width: 680px) {
  .content-frame-header {
    gap: 8px;
  }

  .content-frame-body {
    padding-right: 10px;
    padding-left: 10px;
  }
}
</style>
