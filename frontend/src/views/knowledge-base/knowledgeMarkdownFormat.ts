import { parse } from 'yaml'

export const KNOWLEDGE_MARKDOWN_TEMPLATE_TYPE = 'knowledge_document'
export const KNOWLEDGE_MARKDOWN_TEMPLATE_VERSION = 1
export const KNOWLEDGE_MARKDOWN_FORMAT_ERROR = '格式错误：请使用下载的 Markdown 模板上传。'

export interface ParsedKnowledgeMarkdown {
  markdown: string
  templateType: typeof KNOWLEDGE_MARKDOWN_TEMPLATE_TYPE
  templateVersion: typeof KNOWLEDGE_MARKDOWN_TEMPLATE_VERSION
}

export class KnowledgeMarkdownFormatError extends Error {
  constructor(reason?: string) {
    super(reason ? `${KNOWLEDGE_MARKDOWN_FORMAT_ERROR}${reason}` : KNOWLEDGE_MARKDOWN_FORMAT_ERROR)
    this.name = 'KnowledgeMarkdownFormatError'
  }
}

export function knowledgeMarkdownFrontMatter(): string {
  return [
    '---',
    `template_type: ${KNOWLEDGE_MARKDOWN_TEMPLATE_TYPE}`,
    `template_version: ${KNOWLEDGE_MARKDOWN_TEMPLATE_VERSION}`,
    '---',
    '',
  ].join('\n')
}

export function knowledgeMarkdownTemplateContent(markdown: string): string {
  return `${knowledgeMarkdownFrontMatter()}${markdown.trim()}\n`
}

export function isKnowledgeMarkdownFileName(fileName: string): boolean {
  const normalized = fileName.trim().toLowerCase()
  return normalized.endsWith('.md') || normalized.endsWith('.markdown')
}

export function parseKnowledgeMarkdownTemplate(source: string): ParsedKnowledgeMarkdown {
  const normalized = source.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n')
  if (!normalized.startsWith('---\n')) throw new KnowledgeMarkdownFormatError('缺少模板标记。')

  const frontMatterEnd = normalized.indexOf('\n---\n', 4)
  if (frontMatterEnd < 0) throw new KnowledgeMarkdownFormatError('模板标记未闭合。')

  let metadata: unknown
  try {
    metadata = parse(normalized.slice(4, frontMatterEnd))
  } catch {
    throw new KnowledgeMarkdownFormatError('模板标记无效。')
  }
  if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) {
    throw new KnowledgeMarkdownFormatError('模板标记无效。')
  }

  const values = metadata as Record<string, unknown>
  if (values.template_type !== KNOWLEDGE_MARKDOWN_TEMPLATE_TYPE) {
    throw new KnowledgeMarkdownFormatError('模板类型不正确。')
  }
  if (values.template_version !== KNOWLEDGE_MARKDOWN_TEMPLATE_VERSION) {
    throw new KnowledgeMarkdownFormatError('模板版本不支持。')
  }

  const markdown = normalized.slice(frontMatterEnd + 5).trim()
  validateMarkdownStructure(markdown)
  return {
    markdown: `${markdown}\n`,
    templateType: KNOWLEDGE_MARKDOWN_TEMPLATE_TYPE,
    templateVersion: KNOWLEDGE_MARKDOWN_TEMPLATE_VERSION,
  }
}

export async function parseKnowledgeMarkdownFile(file: File): Promise<ParsedKnowledgeMarkdown> {
  if (!isKnowledgeMarkdownFileName(file.name)) {
    throw new KnowledgeMarkdownFormatError('仅支持 .md 或 .markdown 文件。')
  }
  let source: string
  try {
    source = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer())
  } catch {
    throw new KnowledgeMarkdownFormatError('文件必须使用 UTF-8 编码。')
  }
  return parseKnowledgeMarkdownTemplate(source)
}

function validateMarkdownStructure(markdown: string): void {
  const lines = markdown.split('\n')
  const firstContent = lines.find((line) => line.trim())?.trim() || ''
  if (!/^#\s+\S/.test(firstContent)) {
    throw new KnowledgeMarkdownFormatError('正文必须以一级标题开始。')
  }
  if (!lines.some((line) => /^##\s+\S/.test(line.trim()))) {
    throw new KnowledgeMarkdownFormatError('正文至少需要一个二级章节。')
  }
  if (!hasMeaningfulBody(lines)) {
    throw new KnowledgeMarkdownFormatError('正文内容不能为空。')
  }
  if (!hasClosedFences(lines)) {
    throw new KnowledgeMarkdownFormatError('代码块未闭合。')
  }
}

function hasMeaningfulBody(lines: string[]): boolean {
  return lines.some((line) => {
    const value = line.trim()
    return Boolean(value)
      && !/^#{1,6}\s+/.test(value)
      && !/^(?:```|~~~)/.test(value)
  })
}

function hasClosedFences(lines: string[]): boolean {
  let activeFence: '```' | '~~~' | null = null
  for (const line of lines) {
    const marker = line.trimStart().match(/^(```|~~~)/)?.[1] as '```' | '~~~' | undefined
    if (!marker) continue
    if (activeFence === null) activeFence = marker
    else if (activeFence === marker) activeFence = null
  }
  return activeFence === null
}
