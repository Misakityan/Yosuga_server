<template>
  <n-card class="core-control" :bordered="false">
    <n-space align="center" justify="space-between">
      <n-space align="center">
        <n-badge
          dot
          :type="isRunning ? 'success' : 'error'"
          :processing="isLoading"
        >
          <n-icon size="28" :color="getStatusColor">
            <pulse-icon />
          </n-icon>
        </n-badge>
        <div>
          <div class="core-title">
            Yosuga 核心
            <n-tag v-if="isRunning" type="success" size="small" style="margin-left: 8px">
              运行中
            </n-tag>
            <n-tag v-else-if="hasError" type="error" size="small" style="margin-left: 8px">
              启动失败
            </n-tag>
            <n-tag v-else type="default" size="small" style="margin-left: 8px">
              已停止
            </n-tag>
          </div>
          <div class="core-status">
            <span v-if="isRunning">
              PID: {{ coreStatus?.pid || 0 }} |
              运行时间: {{ formatUptime(coreStatus?.uptime || 0) }} |
              线程{{ coreStatus?.thread_alive ? '存活' : '异常' }}
            </span>
            <span v-else-if="hasError" class="error-text">
              错误: {{ coreStatus?.error }}
            </span>
            <span v-else>点击启动按钮开始运行</span>
          </div>
        </div>
      </n-space>

      <n-space>
        <!-- 启动按钮 -->
        <n-button
          v-if="!isRunning && !isLoading"
          type="primary"
          size="large"
          @click="handleStart"
        >
          <template #icon>
            <n-icon><play-icon /></n-icon>
          </template>
          启动核心
        </n-button>

        <!-- 停止按钮 -->
        <n-button
          v-if="isRunning"
          type="error"
          size="large"
          :loading="isLoading"
          @click="handleStop"
        >
          <template #icon>
            <n-icon><stop-icon /></n-icon>
          </template>
          停止核心
        </n-button>

        <!-- 刷新按钮（现在主要用于强制刷新HTTP备用） -->
        <n-button circle size="large" :loading="isLoading" @click="refreshStatus">
          <template #icon>
            <n-icon><refresh-icon /></n-icon>
          </template>
        </n-button>
      </n-space>
    </n-space>

    <!-- WebSocket连接状态指示器 -->
    <n-divider />
    <n-space align="center" justify="space-between" size="small">
      <n-space align="center" size="small">
        <n-badge :type="wsStore.status === 'connected' ? 'success' : 'error'" dot />
        <span style="font-size: 12px; color: var(--n-text-color-3)">
          {{ wsStore.status === 'connected' ? '实时连接正常' : '实时连接断开' }}
          <span v-if="wsStore.latency > 0">({{ wsStore.latency }}ms)</span>
        </span>
      </n-space>

      <n-button v-if="wsStore.status !== 'connected'" text type="primary" size="small" @click="reconnect">
        重新连接
      </n-button>
    </n-space>

    <!-- 错误提示 -->
    <n-alert v-if="errorMsg" type="error" closable style="margin-top: 12px" @close="errorMsg = ''">
      {{ errorMsg }}
    </n-alert>
  </n-card>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  PulseOutline as PulseIcon,
  PlayOutline as PlayIcon,
  StopOutline as StopIcon,
  RefreshOutline as RefreshIcon
} from '@vicons/ionicons5'
import { useWebSocketStore } from '@/stores/websocket'
import axios from 'axios'

const message = useMessage()
const router = useRouter()
const wsStore = useWebSocketStore()

// 本地状态
const isLoading = ref(false)
const errorMsg = ref('')

// 从WebSocket获取核心状态（实时）
const coreStatus = computed(() => wsStore.coreStatus)
const isRunning = computed(() => coreStatus.value?.is_running ?? false)
const hasError = computed(() => !!coreStatus.value?.error)

// 状态颜色
const getStatusColor = computed(() => {
  if (isLoading.value) return '#f0a020'
  if (isRunning.value) return '#18a058'
  if (hasError.value) return '#d03050'
  return '#808080'
})

// 格式化运行时间
const formatUptime = (seconds: number) => {
  if (!seconds) return '0s'
  const hrs = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  if (hrs > 0) return `${hrs}h ${mins}m`
  if (mins > 0) return `${mins}m ${secs}s`
  return `${secs}s`
}

// 使用WebSocket启动核心（更快速，无HTTP开销）
const handleStart = async () => {
  errorMsg.value = ''
  isLoading.value = true

  try {
    // 优先使用WebSocket，如果不连接则回退到HTTP
    if (wsStore.status === 'connected') {
      wsStore.controlCore('start')
      // 等待WebSocket推送状态更新（最多5秒）
      await waitForStatusChange(true, 5000)
    } else {
      // HTTP备用方案
      const res = await axios.post('/api/core/start')
      if (!res.data.success) {
        throw new Error(res.data.error || '启动失败')
      }
    }
  } catch (error: any) {
    errorMsg.value = error.response?.data?.error || error.message || '启动失败'
    message.error(errorMsg.value)
  } finally {
    isLoading.value = false
  }
}

// 使用WebSocket停止核心
const handleStop = async () => {
  const confirmed = confirm('确定要停止 Yosuga 核心吗？这将中断所有正在进行的对话和任务。')
  if (!confirmed) return

  isLoading.value = true
  try {
    if (wsStore.status === 'connected') {
      wsStore.controlCore('stop')
      await waitForStatusChange(false, 5000)
    } else {
      const res = await axios.post('/api/core/stop')
      if (!res.data.success) {
        throw new Error(res.data.error || '停止失败')
      }
    }
    message.success('Yosuga 核心已停止')
  } catch (error: any) {
    errorMsg.value = error.response?.data?.error || error.message || '停止失败'
    message.error(errorMsg.value)
  } finally {
    isLoading.value = false
  }
}

// 等待状态变化辅助函数
const waitForStatusChange = (targetRunning: boolean, timeout: number): Promise<void> => {
  return new Promise((resolve, reject) => {
    const checkInterval = setInterval(() => {
      if (coreStatus.value?.is_running === targetRunning) {
        clearInterval(checkInterval)
        clearTimeout(timeoutId)
        resolve()
      }
    }, 100)

    const timeoutId = setTimeout(() => {
      clearInterval(checkInterval)
      resolve() // 超时也不报错，依赖后续状态更新
    }, timeout)
  })
}

// 刷新状态（HTTP备用）
const refreshStatus = async () => {
  try {
    const res = await axios.get('/api/core/status')
    if (res.data.success) {
      // 手动更新store（如果需要）
      message.success('状态已刷新')
    }
  } catch (error) {
    message.error('刷新状态失败')
  }
}

// 重新连接WebSocket
const reconnect = () => {
  wsStore.disconnect()
  setTimeout(() => wsStore.connect(), 500)
}

// 监听WebSocket连接状态
watch(() => wsStore.status, (newStatus) => {
  if (newStatus === 'disconnected' && isRunning.value) {
    // 如果断开但核心在运行，尝试重新连接
    setTimeout(() => wsStore.connect(), 1000)
  }
})

onMounted(() => {
  // 确保WebSocket连接
  if (wsStore.status !== 'connected') {
    wsStore.connect()
  }
})
</script>

<style scoped>
.core-control {
  background: linear-gradient(135deg, var(--n-card-color) 0%, var(--n-action-color) 100%);
  border: 1px solid var(--n-border-color);
}

.core-title {
  font-weight: 600;
  font-size: 16px;
  display: flex;
  align-items: center;
}

.core-status {
  font-size: 13px;
  color: var(--n-text-color-3);
  margin-top: 4px;
}

.error-text {
  color: #d03050;
  font-weight: 500;
}

:deep(.n-badge .n-badge-dot) {
  width: 10px;
  height: 10px;
}
</style>