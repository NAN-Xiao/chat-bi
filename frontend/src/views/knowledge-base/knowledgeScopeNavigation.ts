import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { KnowledgeBaseScope } from '@/api/knowledgeBase'

const scopeRouteNames: Record<KnowledgeBaseScope, string> = {
  PLATFORM_PUBLIC: 'system-platform-knowledge-base',
  ADMIN_PUBLIC: 'system-workspace-knowledge-base',
}

export function useKnowledgeScopeNavigation() {
  const route = useRoute()
  const router = useRouter()

  return computed<KnowledgeBaseScope>({
    get: () => route.meta.knowledgeScope === 'ADMIN_PUBLIC' ? 'ADMIN_PUBLIC' : 'PLATFORM_PUBLIC',
    set: (scope) => {
      if (scope === route.meta.knowledgeScope) return
      router.push({ name: scopeRouteNames[scope] })
    },
  })
}
