import type MarkdownIt from 'markdown-it'
import type Token from 'markdown-it/lib/token.mjs'

export interface KnowledgeDocumentSection {
  id: string
  title: string
  html: string
}

function createSection(index: number, title: string, html: string): KnowledgeDocumentSection {
  return {
    id: `document-section-${index + 1}`,
    title: title.trim().replace(/^\d{1,3}[.、．]\s*/, ''),
    html,
  }
}

function parseMarkdownHeadings(
  content: string,
  fallbackTitle: string,
  markdown: MarkdownIt
): KnowledgeDocumentSection[] {
  const environment = {}
  const tokens = markdown.parse(content, environment)
  const headingLevels = tokens
    .filter((token) => token.type === 'heading_open')
    .map((token) => Number(token.tag.slice(1)))
    .filter(Number.isFinite)

  if (!headingLevels.length) return []

  const headingCounts = headingLevels.reduce<Record<number, number>>((counts, level) => {
    counts[level] = (counts[level] || 0) + 1
    return counts
  }, {})
  const shallowestLevel = Math.min(...headingLevels)
  const nestedSectionLevel = [...new Set(headingLevels)]
    .sort((left, right) => left - right)
    .find((level) => level > shallowestLevel && headingCounts[level] >= 2)
  const sectionLevel =
    headingCounts[shallowestLevel] === 1 && nestedSectionLevel
      ? nestedSectionLevel
      : shallowestLevel
  const sections: KnowledgeDocumentSection[] = []
  let sectionTitle = ''
  let sectionTokens: Token[] = []

  const flushSection = () => {
    const html = markdown.renderer.render(sectionTokens, markdown.options, environment).trim()
    if (!sectionTitle && !html) return
    sections.push(createSection(sections.length, sectionTitle || fallbackTitle, html))
  }

  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index]
    const level = token.type === 'heading_open' ? Number(token.tag.slice(1)) : 0
    if (token.type === 'heading_open' && level === sectionLevel) {
      if (sectionTitle) {
        flushSection()
        sectionTokens = []
      }
      sectionTitle = tokens[index + 1]?.content?.trim() || fallbackTitle
      index += 2
      continue
    }
    if (!sectionTitle && token.type === 'heading_open' && level < sectionLevel) {
      index += 2
      continue
    }
    sectionTokens.push(token)
  }
  flushSection()

  return sections
}

function parseNumberedHeadings(
  content: string,
  fallbackTitle: string,
  markdown: MarkdownIt
): KnowledgeDocumentSection[] {
  const lines = content.split(/\r?\n/)
  const candidates = lines.flatMap((line, index) => {
    const match = line.match(/^\s*(\d{1,3})[.、．]\s+(.{1,80}?)\s*$/)
    return match ? [{ lineIndex: index, number: Number(match[1]), title: match[2] }] : []
  })

  const isConsecutive = candidates.every(
    (candidate, index) => candidate.number === candidates[0].number + index
  )
  if (candidates.length < 2 || candidates[0].number !== 1 || !isConsecutive) return []

  const bodies = candidates.map((candidate, index) => {
    const nextLineIndex = candidates[index + 1]?.lineIndex ?? lines.length
    return lines
      .slice(candidate.lineIndex + 1, nextLineIndex)
      .join('\n')
      .trim()
  })

  // Consecutive list items without their own bodies are an ordered list, not document headings.
  if (bodies.some((body) => !body)) return []

  const sections: KnowledgeDocumentSection[] = []
  const preface = lines.slice(0, candidates[0].lineIndex).join('\n').trim()
  if (preface)
    sections.push(createSection(sections.length, fallbackTitle, markdown.render(preface)))
  candidates.forEach((candidate, index) => {
    sections.push(
      createSection(sections.length, candidate.title, markdown.render(bodies[index]).trim())
    )
  })
  return sections
}

export function buildKnowledgeDocumentSections(
  content: string | null | undefined,
  fallbackTitle: string,
  emptyText: string,
  markdown: MarkdownIt
): KnowledgeDocumentSection[] {
  const source = content?.trim() || ''
  if (!source) return [createSection(0, fallbackTitle, markdown.render(emptyText))]

  const markdownSections = parseMarkdownHeadings(source, fallbackTitle, markdown)
  if (markdownSections.length) return markdownSections

  const numberedSections = parseNumberedHeadings(source, fallbackTitle, markdown)
  if (numberedSections.length) return numberedSections

  return [createSection(0, fallbackTitle, markdown.render(source))]
}
