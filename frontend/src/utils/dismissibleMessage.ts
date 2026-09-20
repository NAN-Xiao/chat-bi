import { ElMessage } from 'element-plus-secondary'

let messageSequence = 0

/** Keep the normal timeout, while allowing a click elsewhere to dismiss this message. */
export function showDismissibleSuccess(message: string) {
  const customClass = `dismissible-success-${++messageSequence}`
  const handleOutsideClick = (event: MouseEvent) => {
    const clickedMessage = event.composedPath().some(
      (target) => target instanceof Element && target.classList.contains(customClass)
    )
    if (!clickedMessage) instance.close()
  }
  const instance = ElMessage.success({
    message,
    customClass,
    grouping: false,
    onClose: () => document.removeEventListener('click', handleOutsideClick, true),
  })
  // Capture runs before button handlers, so the click that opens the message
  // cannot dismiss it, and controls that stop propagation still dismiss it.
  document.addEventListener('click', handleOutsideClick, true)
  return instance
}
