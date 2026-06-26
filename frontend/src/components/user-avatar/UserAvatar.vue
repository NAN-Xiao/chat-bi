<script setup lang="ts">
import { computed, type CSSProperties } from 'vue'

const props = withDefaults(
  defineProps<{
    name?: string | number | null
    account?: string | number | null
    uid?: string | number | null
    size?: number | string
    ariaLabel?: string
  }>(),
  {
    size: 32,
    ariaLabel: '',
  }
)

const avatarPalettes = [
  { background: '#e8efff', color: '#2f6bff', border: '#cddcff' },
  { background: '#e7f8f0', color: '#0f9f6e', border: '#bfead8' },
  { background: '#fff3d6', color: '#c46a00', border: '#ffe0a3' },
  { background: '#f3e8ff', color: '#7c3aed', border: '#ddc2ff' },
  { background: '#ffe8ef', color: '#d92d5b', border: '#ffc5d6' },
  { background: '#e6f7ff', color: '#0284c7', border: '#b9e9ff' },
  { background: '#eef7e6', color: '#4b8f1f', border: '#d0eabf' },
  { background: '#fff0e6', color: '#ea580c', border: '#ffd5ba' },
  { background: '#fde8ff', color: '#b423d4', border: '#f5c6ff' },
  { background: '#e6fbf7', color: '#0d9488', border: '#b8eee5' },
  { background: '#fff1f2', color: '#e11d48', border: '#ffcdd5' },
  { background: '#edf7ff', color: '#0b73d9', border: '#c7e6ff' },
]

const normalizeValue = (value?: string | number | null) => String(value ?? '').trim()

const displayText = computed(() => {
  return [props.name, props.account, props.uid].map(normalizeValue).find(Boolean) || '-'
})

const hashKey = computed(() => {
  return [props.uid, props.account, props.name].map(normalizeValue).find(Boolean) || displayText.value
})

const hashString = (value: string) => {
  let hash = 0
  Array.from(value).forEach((char) => {
    hash = (hash * 31 + (char.codePointAt(0) || 0)) >>> 0
  })
  return hash
}

const selectedPalette = computed(() => {
  return avatarPalettes[hashString(hashKey.value) % avatarPalettes.length]
})

const initial = computed(() => {
  const firstChar = Array.from(displayText.value)[0]
  return firstChar ? firstChar.toLocaleUpperCase() : '-'
})

const avatarSize = computed(() => {
  return typeof props.size === 'number' ? `${props.size}px` : props.size || '32px'
})

const avatarFontSize = computed(() => {
  const numericSize = Number.parseFloat(String(props.size))
  return Number.isFinite(numericSize) ? `${Math.max(12, Math.round(numericSize * 0.38))}px` : '14px'
})

const avatarStyle = computed<CSSProperties>(
  () =>
    ({
      '--user-avatar-size': avatarSize.value,
      '--user-avatar-font-size': avatarFontSize.value,
      '--user-avatar-bg': selectedPalette.value.background,
      '--user-avatar-color': selectedPalette.value.color,
      '--user-avatar-border': selectedPalette.value.border,
    }) as CSSProperties
)
</script>

<template>
  <span
    class="user-avatar"
    :style="avatarStyle"
    role="img"
    :aria-label="ariaLabel || displayText"
  >
    {{ initial }}
  </span>
</template>

<style lang="less" scoped>
.user-avatar {
  flex: 0 0 var(--user-avatar-size);
  width: var(--user-avatar-size);
  height: var(--user-avatar-size);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid var(--user-avatar-border);
  border-radius: 50%;
  background: var(--user-avatar-bg);
  color: var(--user-avatar-color);
  font-size: var(--user-avatar-font-size);
  font-weight: 700;
  line-height: 1;
  text-align: center;
  user-select: none;
}
</style>
