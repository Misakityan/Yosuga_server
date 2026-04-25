import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'
import { useWebSocketStore } from './websocket'

export interface CheckResult {
  name: string
  status: 'healthy' | 'unhealthy' | 'unknown' | 'checking'
  message: string
  details: {
    host?: string
    port?: number
    error?: string
    tcp_ok?: boolean
  }
  latency_ms: number
  timestamp: number
}

export interface DiagnosticsReport {
  overall_status: 'healthy' | 'unhealthy' | 'unknown'
  checks: CheckResult[]
  summary: {
    healthy: number
    unhealthy: number
    unknown: number
    total: number
  }
  generated_at: number
  version: string
}

export interface ModuleHealth {
  module: string
  status: 'healthy' | 'unhealthy' | 'unknown' | 'checking'
  message: string
  details: {
    host?: string
    port?: number
    error?: string
  }
  latency_ms?: number
  lastCheck: number
}

export const useDiagnosticsStore = defineStore('diagnostics', () => {
  const wsStore = useWebSocketStore()

  const isRunningFullCheck = ref(false)
  const lastReport = ref<DiagnosticsReport | null>(null)
  const moduleHealth = ref<Record<string, ModuleHealth>>({
    asr: { module: 'asr', status: 'unknown', message: '未检查', details: {}, lastCheck: 0 },
    tts: { module: 'tts', status: 'unknown', message: '未检查', details: {}, lastCheck: 0 },
    ai: { module: 'ai', status: 'unknown', message: '未检查', details: {}, lastCheck: 0 },
    auto_agent: { module: 'auto_agent', status: 'unknown', message: '未检查', details: {}, lastCheck: 0 },
    llm_core: { module: 'llm_core', status: 'unknown', message: '未检查', details: {}, lastCheck: 0 }
  })

  const healthyCount = computed(() =>
    Object.values(moduleHealth.value).filter(m => m.status === 'healthy').length
  )

  const hasUnhealthy = computed(() =>
    Object.values(moduleHealth.value).some(m => m.status === 'unhealthy')
  )

  const overallStatus = computed(() => {
    if (hasUnhealthy.value) return 'error'
    if (healthyCount.value === 5) return 'success'
    return 'warning'
  })

  const runFullDiagnostics = async (): Promise<DiagnosticsReport> => {
    isRunningFullCheck.value = true
    try {
      const response = await axios.post<DiagnosticsReport>('/api/diagnostics/run')
      lastReport.value = response.data

      response.data.checks.forEach(check => {
        const moduleMap: Record<string, string> = {
          'ASR服务': 'asr',
          'TTS服务': 'tts',
          'AI服务': 'ai',
          '自动代理服务': 'auto_agent',
          'LLM核心': 'llm_core'
        }

        const moduleKey = moduleMap[check.name]
        if (moduleKey && moduleHealth.value[moduleKey]) {
          moduleHealth.value[moduleKey] = {
            module: moduleKey,
            status: check.status,
            message: check.message,
            details: check.details,
            latency_ms: check.latency_ms,
            lastCheck: Date.now()
          }
        }
      })

      return response.data
    } finally {
      isRunningFullCheck.value = false
    }
  }

  const checkModule = async (module: string) => {
    if (moduleHealth.value[module]) {
      moduleHealth.value[module].status = 'checking'
    }

    try {
      if (wsStore.status === 'connected') {
        wsStore.socket?.emit('check_module_health', { module })
        return
      }

      const response = await axios.get(`/api/diagnostics/check/${module}`)
      if (response.data.success) {
        updateModuleHealth(module, response.data.data)
      }
    } catch (error) {
      moduleHealth.value[module] = {
        module,
        status: 'unhealthy',
        message: '检查失败',
        details: { error: '网络请求失败' },
        lastCheck: Date.now()
      }
    }
  }

  const updateModuleHealth = (module: string, data: CheckResult) => {
    moduleHealth.value[module] = {
      module,
      status: data.status,
      message: data.message,
      details: data.details,
      latency_ms: data.latency_ms,
      lastCheck: Date.now()
    }
  }

  const checkAllModules = async () => {
    const modules = ['asr', 'tts', 'ai', 'auto_agent', 'llm_core']
    await Promise.all(modules.map(m => checkModule(m)))
  }

  const initWebSocketListeners = () => {
    wsStore.socket?.on('module_health_result', (result: {
      success: boolean
      module?: string
      data?: CheckResult
      error?: string
    }) => {
      if (result.success && result.module && result.data) {
        updateModuleHealth(result.module, result.data)
      }
    })

    wsStore.socket?.on('module_status_update', (update: {
      module: string
      status: CheckResult
    }) => {
      updateModuleHealth(update.module, update.status)
    })
  }

  let autoCheckInterval: NodeJS.Timeout | null = null

  const startAutoCheck = (intervalMs = 30000) => {
    stopAutoCheck()
    autoCheckInterval = setInterval(() => {
      checkAllModules()
    }, intervalMs)
  }

  const stopAutoCheck = () => {
    if (autoCheckInterval) {
      clearInterval(autoCheckInterval)
      autoCheckInterval = null
    }
  }

  return {
    isRunningFullCheck,
    lastReport,
    moduleHealth,
    healthyCount,
    hasUnhealthy,
    overallStatus,
    runFullDiagnostics,
    checkModule,
    checkAllModules,
    initWebSocketListeners,
    startAutoCheck,
    stopAutoCheck
  }
})