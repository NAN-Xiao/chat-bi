import {request} from '@/utils/request'
import {getDate} from "@/utils/utils.ts";

export const questionApi = {

    pager: (pageNumber: number, pageSize: number) => request.get(`/chat/question/pager/${pageNumber}/${pageSize}`),
    /* add: (data: any) => new Promise((resolve, reject) => {
      request.post('/chat/question', data, { responseType: 'stream', timeout: 0, onDownloadProgress: p => {
        resolve(p)
      }}).catch(e => reject(e))
    }), */
    // add: (data: any) => request.post('/chat/question', data),
    add: (data: any) => request.fetchStream('/chat/question', data),
    edit: (data: any) => request.put('/chat/question', data),
    delete: (id: number) => request.delete(`/chat/question/${id}`),
    query: (id: number) => request.get(`/chat/question/${id}`)
}

export class ChatRecord {
    id?: number
    chat_id?: number
    create_time?: Date | string
    create_by?: number
    datasource?: number
    engine_type?: string
    question?: string
    answer?: string
    run_time: number = 0

    constructor()
    constructor(id: number, chat_id: number, create_time: Date | string, create_by: number, datasource: number, engine_type: string, question: string, answer: string, run_time: number)
    constructor(id?: number, chat_id?: number, create_time?: Date | string, create_by?: number, datasource?: number, engine_type?: string, question?: string, answer?: string, run_time?: number) {
        this.id = id
        this.chat_id = chat_id
        this.create_time = getDate(create_time)
        this.create_by = create_by
        this.datasource = datasource
        this.engine_type = engine_type
        this.question = question
        this.answer = answer
        this.run_time = run_time ?? 0
    }
}

export class Chat {
    id?: number
    create_time?: Date | string
    create_by?: number
    brief?: string
    chat_type?: string
    datasource?: number
    engine_type?: string

    constructor()
    constructor(id: number, create_time: Date | string, create_by: number, brief: string, chat_type: string, datasource: number, engine_type: string)
    constructor(id?: number, create_time?: Date | string, create_by?: number, brief?: string, chat_type?: string, datasource?: number, engine_type?: string) {
        this.id = id
        this.create_time = getDate(create_time)
        this.create_by = create_by
        this.brief = brief
        this.chat_type = chat_type
        this.datasource = datasource
        this.engine_type = engine_type
    }
}

export class ChatInfo extends Chat {
    datasource_name?: string
    datasource_exists: boolean = true
    records: Array<ChatRecord> = []

    constructor()
    constructor(chat: Chat)
    constructor(id: number, create_time: Date | string, create_by: number, brief: string, chat_type: string, datasource: number, engine_type: string, datasource_name: string, datasource_exists: boolean, records: Array<ChatRecord>)
    constructor(param1?: number | Chat, create_time?: Date | string, create_by?: number, brief?: string, chat_type?: string, datasource?: number, engine_type?: string, datasource_name?: string, datasource_exists: boolean = true, records: Array<ChatRecord> = []) {
        super()
        if (param1 !== undefined) {
            if (param1 instanceof Chat) {
                this.id = param1.id
                this.create_time = getDate(param1.create_time)
                this.create_by = param1.create_by
                this.brief = param1.brief
                this.chat_type = param1.chat_type
                this.datasource = param1.datasource
                this.engine_type = param1.engine_type
            } else {
                this.id = param1
                this.create_time = getDate(create_time)
                this.create_by = create_by
                this.brief = brief
                this.chat_type = chat_type
                this.datasource = datasource
                this.engine_type = engine_type
            }
        }
        this.datasource_name = datasource_name
        this.datasource_exists = datasource_exists
        this.records = records
    }
}

function toChatRecord(data?: any): ChatRecord | undefined {
    if (!data) {
        return undefined
    }
    return new ChatRecord(data.id, data.number, data.create_time, data.create_by, data.datasource, data.engine_type, data.question, data.answer, data.run_time)
}

function toChatRecordList(list: any = []): ChatRecord[] {
    const records: Array<ChatRecord> = []
    for (let i = 0; i < list.length; i++) {
        const record = toChatRecord(list[i])
        if (record) {
            records.push(record)
        }
    }
    return records
}

function toChatInfo(data?: any): ChatInfo | undefined {
    if (!data) {
        return undefined
    }
    return new ChatInfo(data.id, data.create_time, data.create_by, data.brief, data.chat_type, data.datasource, data.engine_type, data.datasource_name, data.datasource_exists, toChatRecordList(data.records))
}

function toChatInfoList(list: any[] = []): ChatInfo[] {
    const infos: Array<ChatInfo> = []
    for (let i = 0; i < list.length; i++) {
        const chatInfo = toChatInfo(list[i])
        if (chatInfo) {
            infos.push(chatInfo)
        }
    }
    return infos
}

function list(): Promise<Array<ChatInfo>> {
    return request.get('/chat/list')
}

function get(id: number): Promise<ChatInfo> {
    return request.get(`/chat/get/${id}`)
}

function startChat(data: any): Promise<ChatInfo> {
    return request.post('/chat/start', data)
}

function renameChat(chat_id: number, brief: string): Promise<string> {
    return request.post('/chat/rename', {id: chat_id, brief: brief})
}

function deleteChat(id: number): Promise<string> {
    return request.get(`/chat/delete/${id}`)
}

export const chatApi = {
    toChatRecord,
    toChatRecordList,
    toChatInfo,
    toChatInfoList,
    list,
    get,
    startChat,
    renameChat,
    deleteChat
}