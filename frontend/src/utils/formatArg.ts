export const formatArg = (text: string) => {
  if (!text) {
    return false
  }

  const normalized = text.trim().toLowerCase()
  const mappingArray = ['true', 'false', '1', '0']
  if (!mappingArray.includes(normalized)) {
    return text
  }

  return JSON.parse(normalized)
}
