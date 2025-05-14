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
            :class="[msg.role, { 'is-typing': msg.isTyping }]"
          >
            <div
              v-if="msg.role === 'assistant'"
              class="message-content"
              :class="{ 'typing': msg.isTyping }"
              v-html="formatMessage(msg.content)"
            ></div>
            <div v-else class="message-content">
              {{ msg.content }}
            </div>
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
  isTyping?: boolean 
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
  /* nextTick(() => {
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
  }) */
}

const updateMessageContent = (index: number, content: string) => {
  if (currentChat.value) {
    currentChat.value.messages[index] = {
      ...currentChat.value.messages[index],
      content
    }
  }
}

const sendMessage = async () => {
  if (!inputMessage.value.trim()) return
  
  let chat = currentChat.value
  if (!chat) {
    chat = {
      id: Date.now().toString(),
      title: 'New Chat',
      messages: []
    }
    chatHistory.value.unshift(chat)
    currentChatId.value = chat.id
  }

  chat.messages.push({
    role: 'user',
    content: inputMessage.value
  })
  
  const defaultMsg = 'Thinking...'
  chat.messages.push({
    role: 'assistant',
    content: defaultMsg,
    isTyping: true
  })
  
  const userInput = inputMessage.value
  inputMessage.value = ''
  
  const index = chat.messages.length - 1
  
  try {
    const response = await questionApi.add({ question: userInput })
    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        chat.messages[index].isTyping = false
        break
      }

      const chunk = decoder.decode(value)
      const lines = chunk.split('\n\n')
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.replace('data:', '').trim())
          let realContent = data.content
          
          switch (data.type) {
            case 'html':
              realContent = '\n' + data.content
              break
            
            case 'error':
              realContent = '\nError: ' + data.content
              break
            
            default:
              if (data.content) {
                const currentContent = chat.messages[index].content
                const newContent = currentContent.startsWith(defaultMsg) 
                  ? realContent 
                  : currentContent + realContent
                
                updateMessageContent(index, newContent)
                await nextTick()
                scrollToBottom()
              }
          }
        }
      }
    }
  } catch (error) {
    console.error('Error:', error)
    updateMessageContent(index, chat.messages[index].content + '\nError: Failed to get response')
    chat.messages[index].isTyping = false
  }
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
  height: calc(100vh - 61px); 
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
    height: 100%;
    position: relative;
    overflow: hidden;
    
    .chat-messages {
      // flex: 1;
      height: calc(100% - 188px);
      overflow-y: auto;
      padding: 24px;
      scroll-behavior: smooth;
      
      &::-webkit-scrollbar {
        width: 6px;
        height: 6px;
      }
      
      &::-webkit-scrollbar-thumb {
        background: rgba(0, 0, 0, 0.2);
        border-radius: 3px;
        
        &:hover {
          background: rgba(0, 0, 0, 0.3);
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
        transition: all 0.3s ease;

        &.user {
          text-align: right;
          .message-content {
            background-color: #e6f4ff;
          }
        }

        &.assistant {
          .message-content {
            background-color: #f5f5f5;
            text-align: left;
          }
        }

        .message-content {
          display: inline-block;
          padding: 12px 16px;
          border-radius: 8px;
          max-width: 80%;
          transition: all 0.3s ease;
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
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      background: #fff;
      border-top: 1px solid var(--el-border-color-lighter);
      padding: 16px 24px;
      z-index: 10;

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