<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import markdown from '@/utils/markdown'
import { buildKnowledgeDocumentSections } from './knowledgeDocumentSections'

const props = defineProps<{
  content?: string | null
  title: string
  directoryLabel: string
  emptyText: string
  readyLabel: string
}>()

const workspaceRef = ref<HTMLElement | null>(null)
const activeSectionId = ref('')
const sectionElements = new Map<string, HTMLElement>()

const sections = computed(() =>
  buildKnowledgeDocumentSections(props.content, props.title, props.emptyText, markdown)
)

watch(
  sections,
  (value) => {
    activeSectionId.value = value[0]?.id || ''
    nextTick(() => workspaceRef.value?.scrollTo({ top: 0 }))
  },
  { immediate: true }
)

function setSectionElement(sectionId: string, element: Element | null) {
  if (element instanceof HTMLElement) sectionElements.set(sectionId, element)
  else sectionElements.delete(sectionId)
}

async function activateSection(sectionId: string, scroll = false) {
  activeSectionId.value = sectionId
  if (!scroll) return
  await nextTick()
  const workspace = workspaceRef.value
  const section = sectionElements.get(sectionId)
  if (!workspace || !section) return
  const workspaceTop = workspace.getBoundingClientRect().top
  const sectionTop = section.getBoundingClientRect().top
  workspace.scrollTo({
    top: workspace.scrollTop + sectionTop - workspaceTop - 20,
    behavior: 'smooth',
  })
}

function updateActiveSection() {
  const workspace = workspaceRef.value
  if (!workspace) return
  if (workspace.scrollTop + workspace.clientHeight >= workspace.scrollHeight - 8) {
    activeSectionId.value = sections.value[sections.value.length - 1]?.id || ''
    return
  }
  const workspaceTop = workspace.getBoundingClientRect().top
  let nearestId = sections.value[0]?.id || ''
  let nearestDistance = Number.POSITIVE_INFINITY

  sections.value.forEach((section) => {
    const element = sectionElements.get(section.id)
    if (!element) return
    const distance = Math.abs(element.getBoundingClientRect().top - workspaceTop - 20)
    if (distance < nearestDistance) {
      nearestDistance = distance
      nearestId = section.id
    }
  })
  activeSectionId.value = nearestId
}
</script>

<template>
  <div class="knowledge-document-viewer">
    <aside class="document-directory" :aria-label="directoryLabel">
      <div class="directory-heading">
        <span class="directory-label">{{ directoryLabel }}</span>
        <span class="directory-count">{{ sections.length }}</span>
      </div>
      <nav class="directory-list">
        <button
          v-for="(section, index) in sections"
          :key="section.id"
          type="button"
          class="directory-item"
          :class="{ 'is-active': activeSectionId === section.id }"
          :aria-current="activeSectionId === section.id ? 'location' : undefined"
          @click="activateSection(section.id, true)"
        >
          <span class="directory-index">{{ index + 1 }}</span>
          <span class="directory-item-title" :title="section.title">{{ section.title }}</span>
          <span class="directory-status" :title="readyLabel" />
        </button>
      </nav>
    </aside>

    <main ref="workspaceRef" class="document-workspace" @scroll.passive="updateActiveSection">
      <div class="document-canvas">
        <section
          v-for="(section, index) in sections"
          :key="section.id"
          :ref="(element) => setSectionElement(section.id, element as Element | null)"
          class="document-section"
          :class="{ 'is-active': activeSectionId === section.id }"
          @click="activateSection(section.id)"
        >
          <header class="section-header">
            <h2>{{ index + 1 }}. {{ section.title }}</h2>
          </header>
          <div v-dompurify-html="section.html" class="section-content markdown-body" />
        </section>
      </div>
    </main>
  </div>
</template>

<style scoped lang="less">
.knowledge-document-viewer {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
  flex: 1;
  overflow: hidden;
  border: 1px solid #e4e7ec;
  border-radius: 6px;
  background: #f5f7fa;
}
.document-directory {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border-right: 1px solid #e4e7ec;
  background: #fff;
}
.directory-heading {
  display: flex;
  min-height: 52px;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid #eaecf0;
}
.directory-label {
  color: #344054;
  font-size: 13px;
  font-weight: 600;
}
.directory-count {
  margin-left: 7px;
  color: #98a2b3;
  font-size: 12px;
}
.directory-list {
  height: calc(100% - 52px);
  overflow-y: auto;
  padding: 8px;
}
.directory-item {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) 8px;
  width: 100%;
  min-width: 0;
  align-items: center;
  gap: 6px;
  padding: 9px 8px;
  border: 0;
  border-radius: 4px;
  color: #475467;
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.directory-item:hover,
.directory-item:focus-visible,
.directory-item.is-active {
  color: #175cd3;
  background: #eff8ff;
  outline: 0;
}
.directory-index {
  color: #98a2b3;
  font-size: 12px;
  text-align: center;
}
.directory-item-title {
  min-width: 0;
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.directory-status {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #12b76a;
}
.document-workspace {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  background: #fff;
}
.document-canvas {
  width: min(100%, 960px);
  min-width: 0;
  margin: 0 auto;
  padding: 36px 48px 80px;
}
.document-section {
  min-width: 0;
  scroll-margin-top: 20px;
}
.document-section + .document-section {
  margin-top: 40px;
}
.section-header {
  padding-bottom: 8px;
  border-bottom: 1px solid #d8dee4;
}
.section-header h2 {
  margin: 0;
  color: #1f2328;
  font-size: 20px;
  font-weight: 600;
  line-height: 30px;
  letter-spacing: 0;
}
.section-content {
  min-height: 72px;
  padding-top: 16px;
  background-color: transparent;
  color: #1f2328;
  font-family:
    -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
  font-size: 14px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.section-content :deep(> :first-child) {
  margin-top: 0;
}
.section-content :deep(> :last-child) {
  margin-bottom: 0;
}
.section-content :deep(h1),
.section-content :deep(h2),
.section-content :deep(h3),
.section-content :deep(h4) {
  margin: 18px 0 8px;
  color: #1d2939;
  letter-spacing: 0;
}
.section-content :deep(ul),
.section-content :deep(ol) {
  padding-left: 24px;
}
.section-content :deep(pre) {
  max-width: 100%;
  overflow-x: auto;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}
.section-content :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
}
.section-content :deep(th),
.section-content :deep(td) {
  padding: 7px 9px;
  border: 1px solid #d0d5dd;
}

@media (max-width: 680px) {
  .knowledge-document-viewer {
    display: flex;
    flex-direction: column;
  }
  .document-directory {
    flex: 0 0 auto;
    border-right: 0;
    border-bottom: 1px solid #e4e7ec;
  }
  .directory-heading {
    min-height: 44px;
  }
  .directory-list {
    display: flex;
    height: auto;
    overflow-x: auto;
    overflow-y: hidden;
    padding: 6px 8px;
  }
  .directory-item {
    flex: 0 0 154px;
  }
  .document-workspace {
    flex: 1;
  }
  .document-canvas {
    width: 100%;
    padding: 20px 16px 64px;
  }
  .section-content {
    padding-top: 14px;
  }
  .section-header h2 {
    font-size: 18px;
    line-height: 28px;
  }
}
</style>
