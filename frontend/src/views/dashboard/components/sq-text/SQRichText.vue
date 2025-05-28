<template>
  <editor v-model="myValue" :init="init" :id="tinymceId"></editor>
</template>

<script setup lang="ts">
import tinymce from 'tinymce/tinymce'
import Editor from '@tinymce/tinymce-vue'
import 'tinymce/themes/silver'
import 'tinymce/themes/silver/theme'
import 'tinymce/icons/default'

import 'tinymce/icons/default/icons'
import 'tinymce/plugins/table'
import 'tinymce/plugins/lists'
import 'tinymce/plugins/wordcount'
import 'tinymce/plugins/code'
import '@npkg/tinymce-plugins/letterspacing'

import {reactive, ref} from 'vue'
import {onMounted} from 'vue'
defineProps({
  value: {
    type: String,
    default: () => {
      return ''
    }
  },
  baseUrl: {
    type: String,
    default: ''
  },
  disabled: {
    type: Boolean,
    default: false
  },
  plugins: {
    type: [String, Array],
    default: 'lists  table'
  }
})
const myValue = ref('this is a rich text')
const tinymceId = ref('vue-tinymce-1')
const init = reactive({
  selector: '#vue-tinymce-1',
  language_url: '/tinymce-sqlbot-private/langs/zh_CN.js',
  language: 'zh_CN',
  skin_url: '/tinymce-sqlbot-private/skins/ui/oxide',
  content_css: '/tinymce-sqlbot-private/skins/content/default/content.css',
  toolbar: false,
  menubar: false,
  inline: true,
  base_url: '/node_modules/tinymce',
  plugins: ['link', 'table'],
  quickbars_selection_toolbar: 'bold italic forecolor | link blockquote quickimage',
})
onMounted(() => {
  tinymce.init({})
})
</script>
<style scoped lang="less"></style>
