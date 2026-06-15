export interface ParsedSseChunk {
  buffer: string
  payloads: string[]
}

export function parseSseChunk(buffer: string, text: string): ParsedSseChunk {
  const nextBuffer = (buffer + text).replace(/\r\n/g, '\n')
  const payloads: string[] = []

  let remaining = nextBuffer
  let boundary = remaining.indexOf('\n\n')

  while (boundary >= 0) {
    const chunk = remaining.slice(0, boundary)
    remaining = remaining.slice(boundary + 2)

    const payload = chunk
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.replace(/^data:\s?/, ''))
      .join('')

    if (payload) {
      payloads.push(payload)
    }

    boundary = remaining.indexOf('\n\n')
  }

  return {
    buffer: remaining,
    payloads,
  }
}
