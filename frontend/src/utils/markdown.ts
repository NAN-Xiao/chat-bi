import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

const md = new MarkdownIt({
  html: false,
  linkify: false,
  breaks: true,
  typographer: true,
  quotes: '“”‘’',
  highlight: (str: any, lang: any): string => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs">
                  <code>${hljs.highlight(str, { language: lang, ignoreIllegals: true }).value}</code>
                </pre>`
      } catch (e) {
        console.error(e)
      }
    }

    return '<pre class="hljs"><code>' + md.utils.escapeHtml(str) + '</code></pre>'
  },
})

export default md
