import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

const md = new MarkdownIt({
  html: true,
  linkify: true,
  highlight: (str, lang): string => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `
          <pre>
          <code class="hljs">
          ${hljs.highlight(str, { language: lang, ignoreIllegals: true }).value}
          </code>
          </pre>
            `
      } catch (e) {
        console.error(e)
        return str
      }
    }

    return '<pre><code class="hljs">' + md.utils.escapeHtml(str) + '</code></pre>'
  },
})

export default md
