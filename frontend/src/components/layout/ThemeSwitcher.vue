<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { applyTheme, getInitialTheme, getNextTheme, type ThemeMode } from '@/utils/theme'

defineProps({
  collapse: { type: Boolean, required: true },
})

const theme = ref<ThemeMode>(getInitialTheme())

const setTheme = (value: ThemeMode) => {
  theme.value = value
  applyTheme(value)
}

const toggleTheme = () => {
  setTheme(getNextTheme(theme.value))
}

const nextThemeLabel = computed(() => {
  return theme.value === 'dark' ? '切换浅色主题' : '切换深色主题'
})

const showMoonIcon = computed(() => theme.value === 'light')

onMounted(() => {
  setTheme(getInitialTheme())
})
</script>

<template>
  <button
    type="button"
    class="theme-toggle"
    :class="[`theme-toggle--${theme}`, { collapse }]"
    :aria-label="nextThemeLabel"
    :title="nextThemeLabel"
    @click="toggleTheme"
  >
    <svg
      v-if="showMoonIcon"
      class="theme-toggle-icon"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M21 13.2A8.6 8.6 0 0 1 10.8 3a7.7 7.7 0 1 0 10.2 10.2Z"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
    <svg
      v-else
      class="theme-toggle-icon"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4.2" stroke="currentColor" stroke-width="1.8" />
      <path
        d="M12 2.8v2.1M12 19.1v2.1M4.9 4.9l1.5 1.5M17.6 17.6l1.5 1.5M2.8 12h2.1M19.1 12h2.1M4.9 19.1l1.5-1.5M17.6 6.4l1.5-1.5"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linecap="round"
      />
    </svg>
  </button>
</template>

<style lang="less" scoped>
.theme-toggle {
  width: 40px;
  height: 40px;
  border: 1px solid var(--theme-shell-border, #d7deea);
  border-radius: 8px;
  display: inline-grid;
  place-items: center;
  color: var(--theme-text-secondary, #53617a);
  background: var(--theme-control-bg, rgba(255, 255, 255, 0.72));
  cursor: pointer;
  transition:
    border-color 160ms ease,
    background 160ms ease,
    color 160ms ease,
    box-shadow 160ms ease;

  &:hover,
  &:focus {
    border-color: rgba(255, 255, 255, 0.22);
    background: var(--theme-control-hover-bg, #ffffff);
    color: var(--theme-sidebar-active-text, var(--theme-text-primary, #172033));
    box-shadow: var(--theme-control-shadow, 0 8px 18px rgba(16, 24, 40, 0.08));
  }

  &.collapse {
    width: 40px;
    background: transparent;
  }
}

.theme-toggle-icon {
  width: 16px;
  height: 16px;
}
</style>
