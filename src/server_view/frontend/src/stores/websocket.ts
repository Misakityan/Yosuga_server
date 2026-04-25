import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { io, Socket } from 'socket.io-client'

// 系统状态类型定义
export interface SystemStats {
  cpu: { percent: number; count: number }
  memory: {
    total: number; available: number;
    percent: number; used: number; free: number
  }
  disk: { total: number; used: number; free: number; percent: number }
  process: {
    memory_percent: number; cpu_percent: number;
    threads: number; uptime: number
  }
  timestamp: number
}

export interface CoreStatus {
  is_running: boolean
  pid: number
  uptime: number
  error: string | null
  thread_alive: boolean
  start_time: string | null
}

export const useWebSocketStore = defineStore('websocket', () => {
  const socket = ref<Socket | null>(null)
  const status = ref<'disconnected' | 'connecting' | 'connected'>('disconnected')
  const logs = ref<string[]>([])
  const currentFilter = ref('ALL')

  // 新增：系统状态（来自WebSocket实时推送）
  const systemStats = ref<SystemStats | null>(null)
  const coreStatus = ref<CoreStatus | null>(null)

  // 连接状态时间戳
  const lastPing = ref<number>(0)
  const latency = computed(() => {
    if (!lastPing.value) return 0
    return Date.now() - lastPing.value
  })

  const connect = () => {
    if (socket.value?.connected) return

    status.value = 'connecting'
    socket.value = io('http://localhost:8089', {
      transports: ['websocket'],
      autoConnect: true,
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5,
    })

    socket.value.on('connect', () => {
      status.value = 'connected'
      lastPing.value = Date.now()
      // 连接时自动订阅日志
      subscribeWithLevel(currentFilter.value)
    })

    socket.value.on('disconnect', (reason) => {
      status.value = 'disconnected'
      console.log(`WebSocket断开: ${reason}`)
    })

    socket.value.on('connect_error', (err) => {
      console.error('WebSocket连接错误:', err)
      status.value = 'disconnected'
    })

    // 日志接收
    socket.value.on('log_line', (data: { line: string; timestamp?: string; level?: string }) => {
      logs.value.push(data.line)
      if (logs.value.length > 1000) {
        logs.value.shift()
      }
    })

    // 新增：系统状态实时推送
    socket.value.on('system_stats', (response: { success: boolean; data: SystemStats }) => {
      if (response.success && response.data) {
        systemStats.value = response.data
        lastPing.value = Date.now()
      }
    })

    // 新增：核心状态实时推送（替代HTTP轮询）
    socket.value.on('core_status', (response: { success: boolean; data: CoreStatus; message?: string }) => {
      if (response.success && response.data) {
        coreStatus.value = response.data
        console.log('核心状态更新:', response.data.is_running ? '运行中' : '已停止', response.message || '')
      }
    })

    // 控制操作结果回调
    socket.value.on('core_control_result', (result: { success: boolean; error?: string; message?: string; data?: any }) => {
      if (!result.success) {
        console.error('核心控制失败:', result.error)
      } else {
        console.log('核心控制成功:', result.message)
      }
    })
  }

  // 新增：通过WebSocket控制核心（替代HTTP请求）
  const controlCore = (action: 'start' | 'stop') => {
    socket.value?.emit('control_core', { action })
  }

  const subscribeWithLevel = (level: string) => {
    currentFilter.value = level
    socket.value?.emit('subscribe_logs', { level })
  }

  const disconnect = () => {
    socket.value?.disconnect()
  }

  const clearLogs = () => {
    logs.value = []
  }

  // 心跳检测
  const startHeartbeat = () => {
    const interval = setInterval(() => {
      if (status.value === 'connected' && socket.value) {
        // 如果超过10秒没有收到system_stats，认为连接可能有问题
        if (lastPing.value && (Date.now() - lastPing.value > 10000)) {
          console.warn('WebSocket可能卡顿，尝试重新连接...')
          socket.value.connect()
        }
      }
    }, 5000)
    return () => clearInterval(interval)
  }

  return {
    socket,
    status,
    logs,
    currentFilter,
    systemStats,      // 导出系统状态
    coreStatus,       // 导出核心状态
    latency,
    connect,
    disconnect,
    clearLogs,
    subscribeWithLevel,
    controlCore,      // 导出控制函数
    startHeartbeat
  }
})