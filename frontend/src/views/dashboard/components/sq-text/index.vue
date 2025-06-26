<template>
  <div
    class="rich-main-class"
    :class="{ 'edit-model': configItem.editing }"
    @keydown.stop
    @keyup.stop
    @dblclick="setEdit"
  >
    <editor
      :id="tinymceId"
      v-model="configItem.propValue"
      :class="{ 'custom-text-content': true, dragHandle: isDisabled }"
      :init="init"
    ></editor>
  </div>
</template>

<script setup lang="ts">
import tinymce from 'tinymce/tinymce'
import Editor from '@tinymce/tinymce-vue'
import 'tinymce/themes/silver'
import 'tinymce/themes/silver/theme'
import 'tinymce/icons/default'

import 'tinymce/plugins/advlist'
import 'tinymce/plugins/autolink'
import 'tinymce/plugins/link'
import 'tinymce/plugins/image'
import 'tinymce/plugins/lists'
import 'tinymce/plugins/charmap'
import 'tinymce/plugins/media'
import 'tinymce/plugins/wordcount'
import 'tinymce/plugins/directionality'
import 'tinymce/plugins/nonbreaking'
import 'tinymce/plugins/pagebreak'
import '@npkg/tinymce-plugins/letterspacing'

import { computed, nextTick, type PropType, reactive, toRefs } from 'vue'
import { onMounted } from 'vue'
import type { CanvasItem } from '@/utils/canvas.ts'

const props = defineProps({
  configItem: {
    type: Object as PropType<CanvasItem>,
    required: true,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const { configItem } = toRefs(props)
const tinymceId = 'vue-tinymce-' + +new Date() + ((Math.random() * 1000).toFixed(0) + '')
const init = reactive({
  base_url: '/tinymce', // 指向 public/tinymce 目录
  suffix: '.min',
  selector: tinymceId,
  language: 'zh_CN',
  skin: 'oxide',
  plugins:
    'advlist autolink link image lists charmap  media wordcount contextmenu directionality pagebreak letterspacing', // 插件
  // 工具栏
  toolbar:
    'undo redo | fontfamily fontsize | |forecolor backcolor bold italic letterspacing |underline strikethrough link lineheight| formatselect | alignleft aligncenter alignright |',
  toolbar_location: '/',
  font_family_formats:
    '微软雅黑=Microsoft YaHei;宋体=SimSun;黑体=SimHei;仿宋=FangSong;华文黑体=STHeiti;华文楷体=STKaiti;华文宋体=STSong;华文仿宋=STFangsong;Andale Mono=andale mono,times;Arial=arial,helvetica,sans-serif;Arial Black=arial black,avant garde;Book Antiqua=book antiqua,palatino;Comic Sans MS=comic sans ms,sans-serif;Courier New=courier new,courier;Georgia=georgia,palatino;Helvetica=helvetica;Impact=impact,chicago;Symbol=symbol;Tahoma=tahoma,arial,helvetica,sans-serif;Terminal=terminal,monaco;Times New Roman=times new roman,times;Trebuchet MS=trebuchet ms,geneva;Verdana=verdana,geneva;Webdings=webdings;Wingdings=wingdings',
  font_size_formats:
    '12px 14px 16px 18px 20px 22px 24px 28px 32px 36px 42px 48px 56px 72px 80px 90px 100px 110px 120px 140px 150px 170px 190px 210px', // 字体大小
  menubar: false,
  placeholder: '',
  inline: true,
  setup: function (editor: any) {
    editor.on('blur', function () {
      configItem.value.editing = false
    })
  },
})

const isDisabled = computed(() => props.disabled || !configItem.value.editing)

const setEdit = () => {
  configItem.value.editing = true
  nextTick(() => {
    editCursor()
  })
}

const editCursor = () => {
  setTimeout(() => {
    const myDiv = document.getElementById(tinymceId)
    // Focus the cursor on the end of the text
    const range = document.createRange()
    const sel = window.getSelection()
    if (myDiv && myDiv.childNodes) {
      range.setStart(myDiv.childNodes[myDiv.childNodes.length - 1], 1)
      range.collapse(false)
      if (sel) {
        sel.removeAllRanges()
        sel.addRange(range)
      }
    }
    // For some browsers, it may be necessary to set the cursor to the end in another way
    if (myDiv && myDiv.focus) {
      myDiv.focus()
    }
  }, 100)
}

onMounted(() => {
  tinymce.init({})
})
</script>
<style scoped lang="less">
.edit-model {
  cursor: text;
}

.rich-main-class {
  display: flex;
  font-size: initial;
  width: 100%;
  height: 100%;
  overflow-y: auto !important;
  position: relative;

  div::-webkit-scrollbar {
    width: 0px !important;
    height: 0px !important;
  }

  :deep(.ol) {
    display: block !important;
    list-style-type: decimal;
    margin-block-start: 1em !important;
    margin-block-end: 1em !important;
    margin-inline-start: 0px !important;
    margin-inline-end: 0px !important;
    padding-inline-start: 40px !important;
  }

  :deep(ul) {
    display: block !important;
    list-style-type: disc;
    margin-block-start: 1em !important;
    margin-block-end: 1em !important;
    margin-inline-start: 0px !important;
    margin-inline-end: 0px !important;
    padding-inline-start: 40px !important;
  }

  :deep(li) {
    margin-left: 20px;
    display: list-item !important;
    text-align: -webkit-match-parent !important;
  }
}

.custom-text-content {
  width: 100%;
  overflow-y: auto;
  outline: none !important;
  border: none !important;
  margin: 2px;

  ol {
    list-style-type: decimal;
  }
}
</style>
