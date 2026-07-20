interface ChatWithBrief {
  id?: number
  brief?: string
}

interface RecordIdentity {
  id?: number
  create_time?: Date | string
}

interface ApplyBriefInput<T extends ChatWithBrief> {
  chatList: T[]
  currentChat: T
  currentChatId?: number
  ownerChatId?: number
  brief: string
}

function normalizeChatId(value?: number) {
  const chatId = Number(value)
  return Number.isFinite(chatId) && chatId > 0 ? chatId : undefined
}

export function resolveTaskOwnerChatId(recordChatId?: number, currentChatId?: number) {
  return normalizeChatId(recordChatId) || normalizeChatId(currentChatId)
}

export function isTaskOwnerChatVisible(
  ownerChatId?: number,
  currentChatId?: number,
  currentChatObjectId?: number
) {
  const ownerId = normalizeChatId(ownerChatId)
  return (
    ownerId !== undefined &&
    ownerId === normalizeChatId(currentChatId) &&
    ownerId === normalizeChatId(currentChatObjectId)
  )
}

export function applyBriefToTaskOwner<T extends ChatWithBrief>({
  chatList,
  currentChat,
  currentChatId,
  ownerChatId,
  brief,
}: ApplyBriefInput<T>) {
  const ownerId = normalizeChatId(ownerChatId)
  if (!ownerId) {
    return false
  }

  const ownerChat = chatList.find((chat) => normalizeChatId(chat.id) === ownerId)
  if (ownerChat) {
    ownerChat.brief = brief
  }

  if (!isTaskOwnerChatVisible(ownerId, currentChatId, currentChat.id)) {
    return false
  }
  currentChat.brief = brief
  return true
}

export function buildChatMessageRenderKey(
  chatId: number | undefined,
  role: string,
  record: RecordIdentity | undefined,
  index: number
) {
  const ownerId = normalizeChatId(chatId) || 'new'
  let recordKey: string | number = record?.id || index
  if (record?.create_time) {
    const createTime = new Date(record.create_time)
    recordKey = Number.isNaN(createTime.getTime())
      ? String(record.create_time)
      : createTime.toISOString()
  }
  return `${ownerId}:${role}:${recordKey}`
}
