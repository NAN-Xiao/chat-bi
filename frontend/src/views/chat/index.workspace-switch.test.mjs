import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('./index.vue', import.meta.url), 'utf8')

test('工作空间切换期间禁用聊天交互控件', () => {
  assert.match(
    source,
    /const chatInteractionDisabled = computed\(\(\) => isTyping\.value \|\| workspaceContextSwitching\.value\)/
  )
  assert.match(source, /<el-button[^>]*:disabled="workspaceContextSwitching"[^>]*@click="createNewChatSimple"/s)
  assert.match(source, /<el-input[\s\S]*?:disabled="chatInteractionDisabled"/)
  assert.match(source, /<AgentSelector[\s\S]*?:disabled="chatInteractionDisabled"/)
  assert.match(source, /<DataSkillSelector[\s\S]*?:disabled="chatInteractionDisabled"/)
  assert.match(source, /:disabled="workspaceContextSwitching \|\| !inputMessage\.trim\(\)"/)
  assert.match(
    source,
    /datasourceContext\.loadDatasources\(\)\.finally\(\(\) => \{\s*workspaceContextSwitching\.value = false/
  )
})

test('工作空间切换期间函数入口拒绝新建会话和发送消息', () => {
  assert.match(
    source,
    /const createNewChatSimple = async \(\) => \{\s*if \(workspaceContextSwitching\.value\) return/
  )
  assert.match(
    source,
    /const ensureChatReadyForSend = async \(\) => \{\s*if \(workspaceContextSwitching\.value\) return false/
  )
})
