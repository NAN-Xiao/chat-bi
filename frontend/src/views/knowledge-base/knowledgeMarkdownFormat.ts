export const KNOWLEDGE_MARKDOWN_FORMAT_ERROR = '格式错误：请上传符合要求的 Markdown 文档。'

export interface ParsedKnowledgeMarkdown {
  markdown: string
}

export class KnowledgeMarkdownFormatError extends Error {
  constructor(reason?: string) {
    super(reason ? `${KNOWLEDGE_MARKDOWN_FORMAT_ERROR}${reason}` : KNOWLEDGE_MARKDOWN_FORMAT_ERROR)
    this.name = 'KnowledgeMarkdownFormatError'
  }
}

export function knowledgeMarkdownTemplateContent(markdown: string): string {
  return `${markdown.trim()}\n`
}

export function isKnowledgeMarkdownFileName(fileName: string): boolean {
  const normalized = fileName.trim().toLowerCase()
  return normalized.endsWith('.md') || normalized.endsWith('.markdown')
}

export function parseKnowledgeMarkdown(source: string): ParsedKnowledgeMarkdown {
  const normalized = source.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n')
  const markdown = normalized.trim()
  validateMarkdownStructure(markdown)
  return { markdown: `${markdown}\n` }
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
  return parseKnowledgeMarkdown(source)
}

function validateMarkdownStructure(markdown: string): void {
  const lines = markdown.split('\n')
  const firstContent = lines.find((line) => line.trim())?.trim() || ''
  if (!/^#\s+\S/.test(firstContent)) {
    throw new KnowledgeMarkdownFormatError('正文必须以一级标题开始。')
  }

  let activeFence: string | null = null
  let hasSecondLevelHeading = false
  let hasMeaningfulBody = false
  for (const line of lines) {
    const value = line.trim()
    const previousFence: string | null = activeFence
    activeFence = advanceMarkdownFence(line, activeFence)
    if (previousFence !== null) {
      if (activeFence === previousFence && value) hasMeaningfulBody = true
      continue
    }
    if (activeFence !== null) continue
    if (/^##\s+\S/.test(value)) hasSecondLevelHeading = true
    else if (value && !/^#{1,6}\s+/.test(value)) hasMeaningfulBody = true
  }

  if (!hasSecondLevelHeading) {
    throw new KnowledgeMarkdownFormatError('正文至少需要一个二级章节。')
  }
  if (!hasMeaningfulBody) {
    throw new KnowledgeMarkdownFormatError('正文内容不能为空。')
  }
  if (activeFence !== null) {
    throw new KnowledgeMarkdownFormatError('代码块未闭合。')
  }
}

function advanceMarkdownFence(line: string, activeFence: string | null): string | null {
  if (activeFence === null) {
    return line.match(/^[ \t]{0,3}(`{3,}|~{3,})/)?.[1] || null
  }
  const closing = line.match(/^[ \t]{0,3}(`+|~+)[ \t]*$/)?.[1]
  if (closing?.[0] === activeFence[0] && closing.length >= activeFence.length) return null
  return activeFence
}
