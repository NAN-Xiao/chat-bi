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
const themeText = computed(() => (theme.value === 'dark' ? '浅色' : '深色'))

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
    <span v-if="!collapse" class="theme-toggle-track">
      <span class="theme-toggle-thumb">
        <svg
          class="theme-toggle-icon"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            v-if="showMoonIcon"
            d="M21 13.2A8.6 8.6 0 0 1 10.8 3a7.7 7.7 0 1 0 10.2 10.2Z"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <template v-else>
            <circle cx="12" cy="12" r="4.2" stroke="currentColor" stroke-width="1.8" />
            <path
              d="M12 2.8v2.1M12 19.1v2.1M4.9 4.9l1.5 1.5M17.6 17.6l1.5 1.5M2.8 12h2.1M19.1 12h2.1M4.9 19.1l1.5-1.5M17.6 6.4l1.5-1.5"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
            />
          </template>
        </svg>
      </span>
      <span class="theme-toggle-label">{{ themeText }}</span>
    </span>
    <template v-else>
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
    </template>
  </button>
</template>

<style lang="less" scoped>
.theme-toggle {
  width: min(120px, calc(100% - 8px));
  height: 34px;
  border: 0;
  border-radius: 999px;
  display: block;
  margin-left: 8px;
  padding: 0;
  outline: none;
  color: var(--theme-text-secondary, #53617a);
  background: transparent;
  cursor: pointer;
  transition:
    color 160ms ease,
    opacity 160ms ease;

  &:hover,
  &:focus,
  &:focus-visible {
    outline: none;
    background: transparent;
    color: var(--theme-sidebar-emphasis-text, var(--theme-text-primary, #172033));
    opacity: 1;
  }

  &.collapse {
    width: 40px;
    height: 40px;
    margin: 0;
    display: inline-grid;
    place-items: center;
    background: transparent;
  }

  &.theme-toggle--dark {
    .theme-toggle-thumb {
      left: auto;
      right: 3px;
    }

    .theme-toggle-label {
      text-align: left;
      padding-left: 12px;
      padding-right: 52px;
    }
  }
}

.theme-toggle-icon {
  width: 16px;
  height: 16px;
  display: block;
}

.theme-toggle-track {
  position: relative;
  width: 100%;
  height: 34px;
  border-radius: 999px;
  display: flex;
  align-items: center;
  overflow: hidden;
  color: var(--theme-sidebar-text-secondary, #9fb0cc);
  background: var(--theme-sidebar-control-bg, rgba(255, 255, 255, 0.08));
  box-shadow: inset 0 0 0 1px var(--theme-sidebar-border, rgba(255, 255, 255, 0.08));
}

.theme-toggle-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  right: auto;
  width: calc(50% - 3px);
  height: 28px;
  border-radius: 999px;
  display: inline-grid;
  place-items: center;
  color: #ffffff;
  background: linear-gradient(135deg, #58739f 0%, #405a84 100%);
  box-shadow: 0 5px 12px rgba(0, 0, 0, 0.16);
  transition:
    left 180ms ease,
    right 180ms ease;
}

.theme-toggle-label {
  position: relative;
  z-index: 1;
  width: 100%;
  padding-left: 52px;
  padding-right: 12px;
  color: var(--theme-sidebar-text-secondary, #9fb0cc);
  font-size: 13px;
  line-height: 34px;
  text-align: right;
  transition:
    padding 180ms ease,
    text-align 180ms ease;
}
</style>
