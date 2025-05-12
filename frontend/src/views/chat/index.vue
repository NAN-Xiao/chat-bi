<template>
  <div class="chat-container">
    <!-- Sidebar for chat history -->
    <div class="chat-sidebar">
      <div class="sidebar-header">
        <el-button type="primary" class="new-chat" @click="createNewChat">
          <el-icon><Plus /></el-icon>
          New Conversation
        </el-button>
        <div class="search-box">
          <el-input
            v-model="searchKeyword"
            placeholder="Search conversation history"
            :prefix-icon="Search"
          />
        </div>
      </div>
      
      <div class="history-list">
        <div 
          v-for="chat in filteredHistory" 
          :key="chat.id"
          class="history-item"
          :class="{ active: currentChatId === chat.id }"
          @click="switchChat(chat.id)"
        >
          <span class="chat-title">{{ chat.title }}</span>
          <el-dropdown trigger="hover" @command="handleCommand($event, chat.id)">
            <span class="more-actions">
              <el-icon><More /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="rename">Rename</el-dropdown-item>
                <el-dropdown-item command="delete" divided>Delete</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </div>

    <!-- Main chat area -->
    <div class="chat-main">
      <div class="chat-messages" ref="messagesRef">
        <template v-if="currentChat?.messages?.length">
          <div 
            v-for="(msg, index) in currentChat.messages" 
            :key="index"
            class="message"
            :class="msg.role"
          >
            <!-- <div class="message-content">{{ msg.content }}</div> -->
            <div class="message-content" v-html="formatMessage(msg.content)"></div>
          </div>
        </template>
        <div v-else class="empty-state">
          <p>Welcome to SQLBot</p>
          <p class="sub-text">You can ask questions in natural language, for example:</p>
          <div class="examples">
            <div class="example-item">View this month's sales growth compared to last month</div>
            <div class="example-item">Analyze sales staff performance by region</div>
            <div class="example-item">Calculate the relationship between customer purchase frequency and average order value</div>
          </div>
        </div>
      </div>
      
      <div class="chat-input">
        <div class="input-wrapper">
          <el-input
            v-model="inputMessage"
            type="textarea"
            :rows="1"
            :autosize="{ minRows: 1, maxRows: 8 }"
            placeholder="Press Enter to send, Ctrl + Enter for new line"
            @keydown.enter.exact.prevent="sendMessage"
            @keydown.ctrl.enter.exact.prevent="handleCtrlEnter"
          />
          <div class="input-actions">  
            <el-button circle type="primary" class="send-btn" @click="sendMessage">
              <el-icon><Position /></el-icon>
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { Plus, Search, More, Position } from '@element-plus/icons-vue'
import { questionApi } from '@/api/chat'


interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface Chat {
  id: string
  title: string
  messages: ChatMessage[]
}

const chatHistory = ref<Chat[]>([])
const currentChatId = ref('')
const searchKeyword = ref('')
const inputMessage = ref('')
const messagesRef = ref<HTMLDivElement>()

const filteredHistory = computed(() => {
  return chatHistory.value.filter(chat => 
    chat.title.toLowerCase().includes(searchKeyword.value.toLowerCase())
  )
})

const currentChat = computed(() => {
  return chatHistory.value.find(chat => chat.id === currentChatId.value)
})

const createNewChat = () => {
  const newChat: Chat = {
    id: Date.now().toString(),
    title: `New Chat ${chatHistory.value.length + 1}`,
    messages: []
  }
  chatHistory.value.unshift(newChat)
  currentChatId.value = newChat.id
}

const switchChat = (chatId: string) => {
  currentChatId.value = chatId
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesRef.value) {
      const scrollHeight = messagesRef.value.scrollHeight
      const animateScroll = () => {
        const currentScroll = messagesRef.value!.scrollTop
        const distance = scrollHeight - currentScroll
        if (distance > 0) {
          window.requestAnimationFrame(animateScroll)
          messagesRef.value!.scrollTop = currentScroll + distance / 8
        }
      }
      animateScroll()
    }
  })
}

const sendMessage = () => {
  if (!inputMessage.value.trim()) return
  
  let chat = currentChat.value
  // if (!chat) return
  if (!chat) {
    chat = {
      id: null,
      title: 'test',
      messages: []
    } as unknown as Chat
  }

  chat.messages.push({
    role: 'user',
    content: inputMessage.value
  })
  
  const param = {
    question: inputMessage.value
  }
  inputMessage.value = ''
  chatHistory.value.unshift(chat)
  currentChatId.value = chat.id
  
  
  // const index = chat.messages.length - 1
  questionApi.add(param).then((result: string) => {
    // chat.messages[index]['content'] += result
    chat.messages.push({
      role: 'assistant',
      content: result
    })
    scrollToBottom()
  })
}

watch(() => currentChat.value?.messages, () => {
  scrollToBottom()
}, { deep: true })

const formatMessage = (content: string) => {
  if (!content) return ''
  return content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
    .replace(/ {2}/g, '&nbsp;&nbsp;')
}

const handleCommand = (command: string, chatId: string) => {
  switch (command) {
    case 'rename':
      break
    case 'delete':
      chatHistory.value = chatHistory.value.filter(chat => chat.id !== chatId)
      if (currentChatId.value === chatId) {
        currentChatId.value = chatHistory.value[0]?.id || ''
      }
      break
  }
}

const handleCtrlEnter = (e: KeyboardEvent) => {
  const textarea = e.target as HTMLTextAreaElement
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const value = textarea.value
  
  inputMessage.value = value.substring(0, start) + '\n' + value.substring(end)
  
  nextTick(() => {
    textarea.selectionStart = textarea.selectionEnd = start + 1
  })
}
</script>

<style lang="less" scoped>
.chat-container {
  height: 100%;
  display: flex;
  background-color: var(--white);
  border-radius: var(--border-radius);
  box-shadow: var(--shadow);
  overflow: hidden;

  .chat-sidebar {
    width: 260px;
    border-right: 1px solid #e6e6e6;
    display: flex;
    flex-direction: column;
    
    .sidebar-header {
      padding: 16px;
      border-bottom: 1px solid #e6e6e6;

      .new-chat {
        width: 100%;
        margin-bottom: 12px;
      }

      .search-box {
        :deep(.el-input__wrapper) {
          background-color: #f5f5f5;
        }
      }
    }

    .history-list {
      flex: 1;
      overflow-y: auto;
      padding: 8px;

      .history-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 12px;
        margin-bottom: 4px;
        border-radius: 6px;
        cursor: pointer;

        &:hover {
          background-color: #f5f5f5;
        }

        &.active {
          background-color: #e6f4ff;
        }

        .chat-title {
          flex: 1;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .more-actions {
          opacity: 0;
          padding: 4px;
        }

        &:hover .more-actions {
          opacity: 1;
        }
      }
    }
  }

  .chat-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    
    .chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      
      &::-webkit-scrollbar {
        width: 6px;
        height: 6px;
      }
      
      &::-webkit-scrollbar-thumb {
        background: #ccc;
        border-radius: 3px;
        
        &:hover {
          background: #999;
        }
      }
      
      &::-webkit-scrollbar-track {
        background: transparent;
      }
      
      &:not(:hover)::-webkit-scrollbar-thumb {
        background: transparent;
      }

      .message {
        margin-bottom: 24px;

        &.user {
          text-align: right;
          .message-content {
            background-color: #e6f4ff;
          }
        }

        &.assistant .message-content {
          background-color: #f5f5f5;
          text-align: left;
        }

        .message-content {
          display: inline-block;
          padding: 12px 16px;
          border-radius: 8px;
          max-width: 80%;
        }
      }

      .empty-state {
        text-align: center;
        color: #666;
        padding: 40px 0;

        .sub-text {
          margin: 16px 0;
        }

        .examples {
          .example-item {
            background-color: #f5f5f5;
            padding: 12px;
            margin: 8px auto;
            max-width: 400px;
            border-radius: 8px;
            cursor: pointer;

            &:hover {
              background-color: #e6f4ff;
            }
          }
        }
      }
    }

    .chat-input {
      padding: 16px 24px;
      border-top: 1px solid var(--el-border-color-lighter);
      background: #fff;

      .input-wrapper {
        position: relative;
        border-radius: 12px;
        border: 1px solid var(--el-border-color);
        background: #f5f5f5;
        transition: all 0.3s;
        
        &:hover, &:focus-within {
          border-color: var(--el-border-color-darker);
          box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }

        :deep(.el-textarea__inner) {
          padding: 16px;
          font-size: 14px;
          // line-height: 1.6;
          // min-height: 80px;
          resize: none;
          border: none;
          background: transparent;
          box-shadow: none !important;
          
          &:focus {
            box-shadow: none !important;
          }
        }

        :deep(.el-textarea__wrapper) {
          box-shadow: none !important; 
          padding: 0;
          background: transparent;
        }
        .input-actions {
          display: flex;
          align-items: center;
          justify-content: end;
          height: 36px;
          padding: 8px;
        }
      }

    
    }
  }
}
</style>