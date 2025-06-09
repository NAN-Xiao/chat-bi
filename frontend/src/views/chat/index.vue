<template>
  <el-container class="chat-container">
    <el-aside class="chat-container-left">
      <el-container class="chat-container-right-container">
        <el-header class="chat-list-header">
          <el-button type="primary" @click="createNewChat">
            <el-icon>
              <Plus/>
            </el-icon>
            New Conversation
          </el-button>
        </el-header>
        <el-main class="chat-list">
          <ChatList
              :current-chat-id="currentChatId"
              v-model:loading="loading"
              :chat-list="chatList"
              @chat-selected="onClickHistory"
              @chat-deleted="onChatDeleted"
              @chat-renamed="onChatRenamed"
          />
        </el-main>
      </el-container>
    </el-aside>
    <el-container :loading="loading">
      <el-main class="chat-record-list">
        <el-scrollbar ref="chatListRef">
          <template v-for="(message, _index) in computedMessages" :key="_index">
            <ChatRow
                :current-chat="currentChat"
                v-model:datasource="currentChat.datasource"
                :msg="message"
            >
              <template v-if="message.role === 'assistant'">
                <ChatAnswer :message="message"/>
              </template>
              <template #footer v-if="message.role === 'assistant'">
                <!--<div>Suggestion</div>-->
              </template>
            </ChatRow>
          </template>
        </el-scrollbar>
      </el-main>
      <el-footer class="chat-footer">
        <div style="height: 24px">
          <template
              v-if="currentChat.datasource && currentChat.datasource_name"
          >
            Datasource：{{ currentChat.datasource_name }}
          </template>
        </div>
        <div class="input-wrapper">
          <el-input
              :disabled="isTyping"
              class="input-area"
              v-model="inputMessage"
              type="textarea"
              :rows="1"
              :autosize="{ minRows: 1, maxRows: 8 }"
              placeholder="Press Enter to send, Ctrl + Enter for new line"
              @keydown.enter.exact.prevent="sendMessage"
              @keydown.ctrl.enter.exact.prevent="handleCtrlEnter"
          />
          <el-button
              link
              type="primary"
              class="input-icon"
              @click="sendMessage"
              :disabled="isTyping"
          >
            <el-icon size="20">
              <Position/>
            </el-icon>
          </el-button>
        </div>
      </el-footer>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import {computed, nextTick, onMounted, ref} from "vue";
import {Plus, Position} from "@element-plus/icons-vue";
import {Chat, chatApi, ChatInfo, type ChatMessage, ChatRecord, questionApi,} from "@/api/chat";
import ChatList from "./ChatList.vue";
import ChatRow from "./ChatRow.vue";
import ChatAnswer from "./ChatAnswer.vue";

const inputMessage = ref("");

const chatListRef = ref()

function scrollToBottom() {
  nextTick(() => {
    chatListRef.value?.scrollTo({
      top: chatListRef.value.wrapRef.scrollHeight,
      behavior: 'smooth'
    })
  })
}

const loading = ref<boolean>(false);
const chatList = ref<Array<ChatInfo>>([]);

const currentChatId = ref<number | undefined>();
const currentChat = ref<ChatInfo>(new ChatInfo());
const isTyping = ref<boolean>(false);

const computedMessages = computed<Array<ChatMessage>>(() => {
  const welcome: ChatMessage = {
    role: "assistant",
    create_time: currentChat.value?.create_time,
    content: currentChat.value?.datasource,
    isTyping: false,
    isWelcome: true,
  };
  const messages: Array<ChatMessage> = [welcome];
  if (currentChatId.value === undefined) {
    return messages;
  }
  for (let i = 0; i < currentChat.value.records.length; i++) {
    const record = currentChat.value.records[i];
    if (record.question !== undefined) {
      messages.push({
        role: "user",
        create_time: record.create_time,
        content: record.question,
      });
    }
    messages.push({
      role: "assistant",
      create_time: record.create_time,
      record: record,
      isTyping: i === currentChat.value.records.length - 1 && isTyping.value,
    });
  }

  return messages;
});

const createNewChat = () => {
  currentChat.value = new ChatInfo();
  currentChatId.value = undefined;
  inputMessage.value = "";
};

function getChatList() {
  loading.value = true;
  chatApi
      .list()
      .then((res) => {
        chatList.value = chatApi.toChatInfoList(res);
      })
      .finally(() => {
        loading.value = false;
      });
}

function onClickHistory(chat: Chat) {
  currentChat.value = new ChatInfo(chat);
  if (chat !== undefined && chat.id !== undefined && !loading.value) {
    currentChatId.value = chat.id;
    loading.value = true;
    chatApi
        .get(chat.id)
        .then((res) => {
          const info = chatApi.toChatInfo(res);
          if (info) {
            currentChat.value = info;

            scrollToBottom()
          }
        })
        .finally(() => {
          loading.value = false;
        });
  }
}

function onChatDeleted(id: number) {
  for (let i = 0; i < chatList.value.length; i++) {
    if (chatList.value[i].id === id) {
      chatList.value.splice(i, 1);
      return;
    }
  }
}

function onChatRenamed(chat: Chat) {
  chatList.value.forEach((c: Chat) => {
    if (c.id === chat.id) {
      c.brief = chat.brief;
    }
  });
  if (currentChat.value.id === chat.id) {
    currentChat.value.brief = chat.brief;
  }
}

onMounted(() => {
  getChatList();
});


const sendMessage = async () => {
  if (!inputMessage.value.trim()) return;
  if (computedMessages.value[0].content === undefined) return;

  loading.value = true;
  isTyping.value = true;

  const currentRecord = new ChatRecord();
  currentRecord.create_time = new Date();
  currentRecord.chat_id = currentChatId.value;
  currentRecord.question = inputMessage.value;
  currentRecord.sql_answer = "";
  currentRecord.sql = "";
  currentRecord.chart_answer = "";
  currentRecord.chart = "";

  currentChat.value.records.push(currentRecord);
  inputMessage.value = "";

  let error = false;
  if (currentChatId.value === undefined) {
    await chatApi
        .startChat({
          question: currentRecord.question.trim(),
          datasource: currentChat.value.datasource,
        })
        .then((res) => {
          const chat = chatApi.toChatInfo(res);
          if (chat !== undefined) {
            chatList.value.unshift(chat);
            currentChatId.value = chat.id;
            chat.records.push(currentRecord);
            currentChat.value = chat;
          } else {
            error = true;
          }
        })
        .catch((e) => {
          isTyping.value = false;
          error = true;
          console.error(e);
        })
        .finally(() => {
          loading.value = false;
        });
  }
  if (error) return;

  try {
    const response = await questionApi.add({
      question: currentRecord.question,
      chat_id: currentChatId.value,
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let sql_answer = ''
    let chart_answer = ''

    while (true) {
      const {done, value} = await reader.read();
      console.log(done);
      if (done) {
        isTyping.value = false;
        break;
      }

      const chunk = decoder.decode(value);

      let _list = [chunk]

      const lines = chunk.trim().split('}\n\n{')
      if (lines.length > 1) {
        _list = []
        for (let line of lines) {
          if (!line.trim().startsWith('{')) {
            line = '{' + line.trim()
          }
          if (!line.trim().endsWith('}')) {
            line = line.trim() + '}'
          }
          _list.push(line)
        }
      }

      console.log(_list);

      for (const str of _list) {

        const data = JSON.parse(str);

        switch (data.type) {
          case "id":
            currentChat.value.records[currentChat.value.records.length - 1].id = data.id;
            break;
          case "info":
            console.log(data.msg);
            break;
          case "error":
            currentRecord.error = data.content;
            isTyping.value = false;
            break;
          case "sql-result":
            sql_answer += data.content;
            currentChat.value.records[currentChat.value.records.length - 1].sql_answer = sql_answer;
            break;
          case "sql":
            currentChat.value.records[currentChat.value.records.length - 1].sql = data.content;
            break;
          case "sql-data":
            currentChat.value.records[currentChat.value.records.length - 1].data = data.content;
            break;
          case "chart-result":
            chart_answer += data.content;
            currentChat.value.records[currentChat.value.records.length - 1].chart_answer = chart_answer;
            break;
          case "chart":
            currentChat.value.records[currentChat.value.records.length - 1].chart = data.content;
            break;
          case "finish":
            isTyping.value = false;
            break;
        }
        await nextTick()
      }

    }
  } catch (error) {
    if (!currentRecord.error) {
      currentRecord.error = "";
    }
    if (currentRecord.error.trim().length !== 0) {
      currentRecord.error = currentRecord.error + "\n";
    }
    currentRecord.error = currentRecord.error + "Error:" + error;
    console.error("Error:", error);
    isTyping.value = false;
  }
};

//@ts-ignore
const formatMessage = (content: string) => {
  if (!content) return "";
  return content
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\n/g, "<br>")
      .replace(/ {2}/g, "&nbsp;&nbsp;");
};

const handleCtrlEnter = (e: KeyboardEvent) => {
  const textarea = e.target as HTMLTextAreaElement;
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const value = textarea.value;

  inputMessage.value = value.substring(0, start) + "\n" + value.substring(end);

  nextTick(() => {
    textarea.selectionStart = textarea.selectionEnd = start + 1;
  });
};
</script>

<style lang="less" scoped>
.chat-container {
  height: 100%;

  .chat-container-left {
    --el-aside-width: 260px;

    border-right: solid 1px rgba(0, 0, 0, 0.3);

    background: var(--ed-fill-color-blank);

    .chat-container-right-container {
      height: 100%;

      .chat-list-header {
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .chat-list {
        padding: 0 0 20px 0;
      }
    }
  }

  .chat-record-list {
    padding: 0 0 20px 0;
  }

  .chat-footer {
    --ed-footer-height: 120px;

    display: flex;
    flex-direction: column;

    .input-wrapper {
      flex: 1;

      position: relative;

      .input-area {
        height: 100%;
        padding-bottom: 8px;

        :deep(.ed-textarea__inner) {
          height: 100% !important;
        }
      }

      .input-icon {
        min-width: unset;
        position: absolute;
        bottom: 14px;
        right: 8px;
      }
    }
  }

  .send-btn {
    min-width: 0;
  }
}
</style>
