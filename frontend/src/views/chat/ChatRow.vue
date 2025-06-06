<script setup lang="ts">
import ChatBlock from './ChatBlock.vue'
import WelcomeBlock from './WelcomeBlock.vue'
import {ChatInfo, type ChatMessage} from "@/api/chat.ts";
import {computed} from "vue";
import {UserFilled} from "@element-plus/icons-vue"

const props = withDefaults(defineProps<{
      msg: ChatMessage
      currentChat: ChatInfo
      datasource?: number
    }>(),
    {}
)

const emits = defineEmits(["update:datasource"])

const _datasource = computed({
  get() {
    return props.datasource
  },
  set(v) {
    emits("update:datasource", v)
  }
})

</script>

<template>
  <div class="chat-row" :class="{'right-to-left': msg.role === 'user'}">
    <el-avatar class="ai-avatar" shape="square" v-if="msg.role === 'assistant'">SQLBot</el-avatar>
    <el-avatar class="user-avatar" shape="square" v-if="msg.role === 'user'">
      <el-icon>
        <UserFilled/>
      </el-icon>
    </el-avatar>
    <ChatBlock v-if="!msg.isWelcome" :msg="msg" :class="{'row-full': msg.role === 'assistant'}">
      <slot></slot>
      <template #footer>
        <slot name="footer"></slot>
      </template>
    </ChatBlock>
    <WelcomeBlock v-else v-model="_datasource" :current-chat="currentChat" class="row-full"/>
  </div>
</template>

<style scoped lang="less">
.chat-row {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  gap: 8px;

  padding: 20px 20px 0;

  &.right-to-left {
    flex-direction: row-reverse;
  }

  .row-full {
    flex: 1;
    width: 0;
  }
}

.ai-avatar {
  background: var(--el-color-primary);
}

.user-avatar {
  background: var(--ed-color-primary)
}


</style>