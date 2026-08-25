<script setup lang="ts">
import { nextTick, onBeforeUnmount, watch } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { Markdown } from '@tiptap/markdown'
import { TableKit } from '@tiptap/extension-table'

export type KnowledgeBlockFormat = 'paragraph' | 'heading-2' | 'heading-3'

const props = withDefaults(
  defineProps<{
    modelValue: string
    readonly?: boolean
  }>(),
  {
    readonly: false,
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

let applyingExternalContent = false

function blocksRemovedFormatShortcut(event: KeyboardEvent) {
  if (!(event.ctrlKey || event.metaKey)) return false
  return ['b', 'i', 'u', 'k'].includes(event.key.toLowerCase())
}

const editor = useEditor({
  content: props.modelValue,
  contentType: 'markdown',
  editable: !props.readonly,
  extensions: [
    StarterKit.configure({
      heading: { levels: [2, 3] },
      link: { openOnClick: false },
      underline: false,
    }),
    TableKit.configure({
      table: { resizable: false },
    }),
    Markdown.configure({
      indentation: { style: 'space', size: 2 },
      markedOptions: { gfm: true, breaks: true },
    }),
  ],
  editorProps: {
    attributes: {
      class: 'knowledge-markdown-surface',
      'aria-label': '知识块正文',
    },
    handleKeyDown: (_view, event) => blocksRemovedFormatShortcut(event),
  },
  onUpdate: ({ editor: instance }) => {
    if (applyingExternalContent || props.readonly) return
    const markdown = instance.getMarkdown()
    if (markdown !== props.modelValue) emit('update:modelValue', markdown)
  },
})

watch(
  () => props.modelValue,
  async (value) => {
    if (!editor.value || value === editor.value.getMarkdown()) return
    applyingExternalContent = true
    editor.value.commands.setContent(value, {
      contentType: 'markdown',
      emitUpdate: false,
    })
    await nextTick()
    applyingExternalContent = false
  }
)

watch(
  () => props.readonly,
  (value) => editor.value?.setEditable(!value)
)

function undo() {
  return editor.value?.chain().focus().undo().run() ?? false
}

function redo() {
  return editor.value?.chain().focus().redo().run() ?? false
}

function setBlockFormat(format: KnowledgeBlockFormat) {
  if (!editor.value) return false
  if (format === 'heading-2') return editor.value.chain().focus().setHeading({ level: 2 }).run()
  if (format === 'heading-3') return editor.value.chain().focus().setHeading({ level: 3 }).run()
  return editor.value.chain().focus().setParagraph().run()
}

function toggleBulletList() {
  return editor.value?.chain().focus().toggleBulletList().run() ?? false
}

function toggleOrderedList() {
  return editor.value?.chain().focus().toggleOrderedList().run() ?? false
}

function toggleBlockquote() {
  return editor.value?.chain().focus().toggleBlockquote().run() ?? false
}

defineExpose({
  undo,
  redo,
  setBlockFormat,
  toggleBulletList,
  toggleOrderedList,
  toggleBlockquote,
})

onBeforeUnmount(() => editor.value?.destroy())
</script>

<template>
  <EditorContent v-if="editor" :editor="editor" class="knowledge-markdown-editor" />
</template>

<style scoped lang="less">
.knowledge-markdown-editor {
  width: 100%;
  min-width: 0;
}

.knowledge-markdown-editor :deep(.knowledge-markdown-surface) {
  min-height: 160px;
  padding: 0;
  outline: 0;
  color: #1d2939;
  font-size: 12px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}

.knowledge-markdown-editor :deep(.knowledge-markdown-surface > :first-child) {
  margin-top: 0;
}

.knowledge-markdown-editor :deep(.knowledge-markdown-surface > :last-child) {
  margin-bottom: 0;
}

.knowledge-markdown-editor :deep(p),
.knowledge-markdown-editor :deep(ul),
.knowledge-markdown-editor :deep(ol),
.knowledge-markdown-editor :deep(blockquote),
.knowledge-markdown-editor :deep(pre),
.knowledge-markdown-editor :deep(table) {
  margin: 10px 0;
}

.knowledge-markdown-editor :deep(h2),
.knowledge-markdown-editor :deep(h3) {
  margin: 24px 0 10px;
  color: #1d2939;
  font-weight: 600;
  letter-spacing: 0;
}

.knowledge-markdown-editor :deep(h2) {
  font-size: 20px;
}

.knowledge-markdown-editor :deep(h3) {
  font-size: 17px;
}

.knowledge-markdown-editor :deep(ul),
.knowledge-markdown-editor :deep(ol) {
  padding-left: 24px;
}

.knowledge-markdown-editor :deep(blockquote) {
  padding: 10px 14px;
  border-left: 3px solid #2f6bff;
  color: #667085;
  background: #eff8ff;
}

.knowledge-markdown-editor :deep(pre) {
  overflow-x: auto;
  padding: 12px 14px;
  border-radius: 6px;
  color: #344054;
  background: #f2f4f7;
}

.knowledge-markdown-editor :deep(code) {
  font-family: Consolas, 'Cascadia Code', monospace;
  font-size: 13px;
}

.knowledge-markdown-editor :deep(table) {
  width: 100%;
  border-collapse: collapse;
}

.knowledge-markdown-editor :deep(th),
.knowledge-markdown-editor :deep(td) {
  padding: 7px 9px;
  border: 1px solid #d0d5dd;
  text-align: left;
}

.knowledge-markdown-editor :deep(.ProseMirror-focused) {
  outline: 0;
}

.knowledge-markdown-editor :deep(.is-empty:first-child::before) {
  float: left;
  height: 0;
  color: #98a2b3;
  content: '输入当前知识块的可检索内容';
  pointer-events: none;
}
</style>
