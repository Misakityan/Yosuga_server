<template>
  <div class="dashboard">
    <CoreControl style="margin-bottom: 16px" />

    <!-- 系统体检报告卡片 -->
    <n-card
      v-if="lastReport"
      :title="`系统体检报告 (v${lastReport.version})`"
      class="diagnostics-card"
      :bordered="false"
      closable
      @close="lastReport = null"
    >
      <n-space align="center" justify="space-between">
        <n-space align="center">
          <n-icon size="32" :color="statusColor">
            <checkmark-circle-icon v-if="diagStore.overallStatus === 'success'" />
            <warning-icon v-else-if="diagStore.overallStatus === 'warning'" />
            <close-circle-icon v-else />
          </n-icon>
          <div>
            <div :style="{ color: statusColor, fontWeight: 600 }">
              {{ statusText }}
            </div>
            <div class="text-secondary">
              {{ lastReport.summary.healthy }}/{{ lastReport.summary.total }} 项检查通过
            </div>
          </div>
        </n-space>

        <n-button text type="primary" @click="showDetails = true">
          查看详情
        </n-button>
      </n-space>
    </n-card>

    <n-grid :x-gap="16" :y-gap="16" cols="1 s:2 l:4">
      <n-gi>
        <n-card class="stat-card" :bordered="false">
          <n-statistic label="CPU 使用率" :value="systemStats?.cpu?.percent ?? 0">
            <template #suffix>%</template>
          </n-statistic>
          <n-progress
            type="line"
            :percentage="systemStats?.cpu?.percent ?? 0"
            :indicator-placement="'inside'"
            :color="getProgressColor(systemStats?.cpu?.percent ?? 0)"
          />
        </n-card>
      </n-gi>

      <n-gi>
        <n-card class="stat-card" :bordered="false">
          <n-statistic label="内存使用" :value="memoryPercent">
            <template #suffix>%</template>
          </n-statistic>
          <n-progress
            type="line"
            :percentage="memoryPercent"
            :indicator-placement="'inside'"
            :color="getProgressColor(memoryPercent)"
          />
        </n-card>
      </n-gi>

      <n-gi>
        <n-card class="stat-card" :bordered="false">
          <n-statistic label="运行时间" :value="uptimeFormatted" />
          <div class="stat-detail">进程启动至今</div>
        </n-card>
      </n-gi>

      <n-gi>
        <n-card class="stat-card" :bordered="false">
          <n-statistic label="服务健康" :value="`${diagStore.healthyCount}/5`" />
          <div class="stat-detail">
            <span :style="{ color: diagStore.hasUnhealthy ? '#d03050' : '#18a058' }">
              {{ diagStore.hasUnhealthy ? '存在异常服务' : '所有服务正常' }}
            </span>
          </div>
        </n-card>
      </n-gi>
    </n-grid>

    <!-- 模块状态 - TCP端口检测 -->
    <n-card title="模块状态" class="module-card" :bordered="false">
      <template #header-extra>
        <n-space>
          <n-tag :type="checkingAll ? 'warning' : 'success'" size="small">
            <n-spin v-if="checkingAll" :size="12" style="margin-right: 4px" />
            {{ checkingAll ? '检测中...' : 'TCP端口检测' }}
          </n-tag>
          <n-button text type="primary" size="small" @click="refreshAllModules">
            <template #icon><n-icon><refresh-icon /></n-icon></template>
            刷新
          </n-button>
        </n-space>
      </template>

      <n-grid :x-gap="16" :y-gap="16" cols="2 s:3 l:5">
        <n-gi v-for="(health, name) in moduleHealthDisplay" :key="name">
          <div
            class="module-item"
            :class="{
              active: health.status === 'healthy',
              error: health.status === 'unhealthy',
              checking: health.status === 'checking'
            }"
            @click="checkSingleModule(name)"
          >
            <n-icon size="24">
              <checkmark-circle-icon v-if="health.status === 'healthy'" color="#18a058" />
              <close-circle-icon v-else-if="health.status === 'unhealthy'" color="#d03050" />
              <time-icon v-else-if="health.status === 'checking'" color="#f0a020" />
              <help-circle-icon v-else color="#808080" />
            </n-icon>

            <div class="module-info">
              <div class="module-name">{{ getModuleName(name) }}</div>

              <n-tooltip>
                <template #trigger>
                  <div class="module-status" :class="health.status">
                    <span v-if="health.status === 'healthy'">端口可连通</span>
                    <span v-else-if="health.status === 'unhealthy'">端口不可达</span>
                    <span v-else-if="health.status === 'checking'">检测中...</span>
                    <span v-else>未检测</span>

                    <span v-if="health.latency_ms && health.status === 'healthy'" class="latency">
                      ({{ health.latency_ms < 1 ? '<1' : health.latency_ms.toFixed(0) }}ms)
                    </span>
                  </div>
                </template>
                <div style="font-size: 12px;">
                  <div>主机: {{ health.details?.host || 'localhost' }}</div>
                  <div>端口: {{ health.details?.port || getDefaultPort(name) }}</div>
                  <div>上次检查: {{ formatTime(health.lastCheck) }}</div>
                  <div v-if="health.details?.error" style="color: #ff4d4f;">
                    错误: {{ health.details.error }}
                  </div>
                </div>
              </n-tooltip>
            </div>

            <n-button
              v-if="health.status === 'unhealthy'"
              text
              type="error"
              size="tiny"
              @click.stop="showModuleDetails(name)"
            >
              详情
            </n-button>
          </div>
        </n-gi>
      </n-grid>
    </n-card>

    <!-- 快速操作 -->
    <n-card title="快速操作" class="action-card" :bordered="false">
      <n-space>
        <n-button
          type="primary"
          :loading="diagStore.isRunningFullCheck"
          @click="runSystemDiagnostics"
        >
          <template #icon><n-icon><medical-icon /></n-icon></template>
          {{ diagStore.isRunningFullCheck ? '体检中...' : '系统体检' }}
        </n-button>

        <n-button @click="handleReloadConfig">
          <template #icon><n-icon><refresh-icon /></n-icon></template>
          重载配置
        </n-button>

        <n-button @click="exportConfig">
          <template #icon><n-icon><download-icon /></n-icon></template>
          导出配置
        </n-button>

        <n-upload
          action="/api/config/import"
          accept=".json"
          :show-file-list="false"
          @finish="handleImportFinish"
          @error="handleImportError"
        >
          <n-button>
            <template #icon><n-icon><upload-icon /></n-icon></template>
            导入配置
          </n-button>
        </n-upload>

        <n-button @click="router.push('/logs')">
          <template #icon><n-icon><terminal-icon /></n-icon></template>
          查看日志
        </n-button>
      </n-space>
    </n-card>

    <!-- 体检详情抽屉 -->
    <n-drawer v-model:show="showDetails" :width="600" placement="right">
      <n-drawer-content title="详细体检报告">
        <n-timeline v-if="lastReport">
          <n-timeline-item
            v-for="check in lastReport.checks"
            :key="check.name"
            :type="check.status === 'healthy' ? 'success' : check.status === 'unhealthy' ? 'error' : 'default'"
            :title="check.name"
            :content="check.message"
            :time="`${check.latency_ms.toFixed(1)}ms`"
          />
        </n-timeline>
      </n-drawer-content>
    </n-drawer>

    <!-- 模块详情Modal -->
    <n-modal v-model:show="showModuleModal" :title="`${selectedModule} 连接详情`">
      <n-card style="width: 450px" v-if="selectedModule">
        <n-descriptions bordered :column="1" size="small">
          <n-descriptions-item label="检测方式">
            <n-tag size="small">TCP端口连通性</n-tag>
          </n-descriptions-item>

          <n-descriptions-item label="目标地址">
            {{ currentModuleHealth?.details?.host || 'localhost' }}
            :{{ currentModuleHealth?.details?.port || getDefaultPort(selectedModule) }}
          </n-descriptions-item>

          <n-descriptions-item label="连接状态">
            <n-tag :type="currentModuleHealth?.status === 'healthy' ? 'success' : 'error'">
              {{ currentModuleHealth?.status === 'healthy' ? '端口开放' : '端口关闭' }}
            </n-tag>
          </n-descriptions-item>

          <n-descriptions-item label="响应延迟" v-if="currentModuleHealth?.latency_ms">
            {{ currentModuleHealth.latency_ms.toFixed(2) }} ms
          </n-descriptions-item>

          <n-descriptions-item label="最后检测">
            {{ formatTime(currentModuleHealth?.lastCheck || 0) }}
          </n-descriptions-item>

          <n-descriptions-item label="错误信息" v-if="currentModuleHealth?.details?.error">
            <span style="color: #d03050;">
              {{ currentModuleHealth.details.error }}
            </span>
          </n-descriptions-item>
        </n-descriptions>

        <n-alert
          v-if="currentModuleHealth?.status === 'unhealthy'"
          type="error"
          style="margin-top: 16px"
          :show-icon="true"
        >
          <template #header>排查建议</template>

          <div v-if="currentModuleHealth?.details?.error === '连接被拒绝'" style="font-size: 13px;">
            1. 服务可能已崩溃或未启动<br>
            2. 检查防火墙是否放行端口<br>
            3. 查看端口是否被其他进程占用
          </div>
          <div v-else-if="currentModuleHealth?.details?.error === '连接超时'" style="font-size: 13px;">
            1. 服务未启动或网络不可达<br>
            2. 检查IP地址和端口配置<br>
            3. 确认服务监听的是0.0.0.0而非127.0.0.1
          </div>
          <div v-else style="font-size: 13px;">
            1. 确认服务已启动<br>
            2. 检查配置文件中的host/port<br>
            3. 查看系统日志获取详细信息
          </div>

          <n-divider style="margin: 8px 0;" />
          <n-space vertical size="small" style="font-size: 12px;">
            <div>配置文件: <code>settings.json</code></div>
            <div v-if="selectedModule === 'asr'">默认端口: 20260</div>
            <div v-else-if="selectedModule === 'tts'">默认端口: 20261</div>
            <div v-else-if="selectedModule === 'ai' || selectedModule === 'auto_agent'">默认端口: 1234 (LM Studio)</div>
          </n-space>
        </n-alert>

        <n-space v-else justify="end" style="margin-top: 16px;">
          <n-button size="small" @click="checkSingleModule(selectedModule)">
            重新检测
          </n-button>
        </n-space>
      </n-card>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import {
  CheckmarkCircleOutline as CheckmarkCircleIcon,
  CloseCircleOutline as CloseCircleIcon,
  RefreshOutline as RefreshIcon,
  TerminalOutline as TerminalIcon,
  DownloadOutline as DownloadIcon,
  CloudUploadOutline as UploadIcon,
  MedicalOutline as MedicalIcon,
  WarningOutline as WarningIcon,
  TimeOutline as TimeIcon,
  HelpCircleOutline as HelpCircleIcon
} from '@vicons/ionicons5'
import { useMessage } from 'naive-ui'
import CoreControl from '@/components/CoreControl.vue'
import { useWebSocketStore } from '@/stores/websocket'
import { useDiagnosticsStore } from '@/stores/diagnostics'

const router = useRouter()
const message = useMessage()
const wsStore = useWebSocketStore()
const diagStore = useDiagnosticsStore()

const checkingAll = ref(false)
const showDetails = ref(false)
const showModuleModal = ref(false)
const selectedModule = ref<string>('')

const systemStats = computed(() => wsStore.systemStats)
const lastReport = computed(() => diagStore.lastReport)
const moduleHealthDisplay = computed(() => diagStore.moduleHealth)

const memoryPercent = computed(() => Math.round(systemStats.value?.memory?.percent ?? 0))
const uptimeFormatted = computed(() => {
  const seconds = systemStats.value?.process?.uptime ?? 0
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  return hours > 0 ? `${hours}h ${mins}m` : `${mins}m`
})

const statusColor = computed(() => {
  if (diagStore.overallStatus === 'success') return '#18a058'
  if (diagStore.overallStatus === 'warning') return '#f0a020'
  return '#d03050'
})

const statusText = computed(() => {
  if (diagStore.overallStatus === 'success') return '系统健康'
  if (diagStore.overallStatus === 'warning') return '部分异常'
  return '需要关注'
})

const currentModuleHealth = computed(() => {
  if (!selectedModule.value) return null
  return diagStore.moduleHealth[selectedModule.value]
})

const getProgressColor = (value: number) => {
  if (value < 60) return '#18a058'
  if (value < 80) return '#f0a020'
  return '#d03050'
}

const getModuleName = (key: string) => {
  const names: Record<string, string> = {
    asr: '语音识别 (ASR)',
    tts: '语音合成 (TTS)',
    ai: 'AI 对话',
    auto_agent: '自动代理',
    llm_core: 'LLM 核心'
  }
  return names[key] || key
}

const getDefaultPort = (module: string) => {
  const ports: Record<string, string> = {
    asr: '20260',
    tts: '20261',
    ai: '1234',
    auto_agent: '1234',
    llm_core: '本地'
  }
  return ports[module] || '-'
}

const formatTime = (timestamp: number) => {
  if (!timestamp) return '从未'
  const diff = Date.now() - timestamp
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff/60000)}分钟前`
  return new Date(timestamp).toLocaleTimeString()
}

const runSystemDiagnostics = async () => {
  try {
    await diagStore.runFullDiagnostics()
    message.success('系统体检完成')
  } catch (error) {
    message.error('体检失败: ' + (error as Error).message)
  }
}

const checkSingleModule = async (name: string) => {
  await diagStore.checkModule(name)
}

const refreshAllModules = async () => {
  checkingAll.value = true
  await diagStore.checkAllModules()
  checkingAll.value = false
  message.success('模块状态已刷新')
}

const showModuleDetails = (name: string) => {
  selectedModule.value = name
  showModuleModal.value = true
}

const handleReloadConfig = async () => {
  try {
    const res = await axios.post('/api/config/reload')
    if (res.data.success) message.success('配置已重载')
  } catch {
    message.error('重载配置失败')
  }
}

const exportConfig = () => {
  window.open('/api/config/export', '_blank')
}

const handleImportFinish = () => {
  message.success('配置导入成功，正在重载...')
  setTimeout(() => window.location.reload(), 1000)
}

const handleImportError = () => {
  message.error('配置导入失败')
}

let heartbeatCleanup: (() => void) | null = null

onMounted(() => {
  wsStore.connect()
  diagStore.initWebSocketListeners()
  heartbeatCleanup = wsStore.startHeartbeat()

  setTimeout(() => {
    diagStore.checkAllModules()
    diagStore.startAutoCheck(30000)
  }, 1000)
})

onUnmounted(() => {
  if (heartbeatCleanup) heartbeatCleanup()
  diagStore.stopAutoCheck()
})
</script>

<style scoped>
.dashboard {
  max-width: 1400px;
  margin: 0 auto;
}

.diagnostics-card {
  margin-bottom: 16px;
  background: linear-gradient(135deg, var(--n-card-color) 0%, var(--n-action-color) 100%);
  border-left: 4px solid v-bind(statusColor);
}

.stat-card {
  background: linear-gradient(135deg, var(--n-card-color) 0%, var(--n-card-color) 100%);
  transition: transform 0.3s;
}

.stat-card:hover {
  transform: translateY(-2px);
}

.stat-detail {
  margin-top: 8px;
  font-size: 12px;
  color: var(--n-text-color-3);
}

.module-card,
.action-card {
  margin-top: 24px;
}

.module-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-radius: 8px;
  background-color: var(--n-action-color);
  transition: all 0.3s;
  cursor: pointer;
}

.module-item:hover {
  background-color: var(--n-hover-color);
}

.module-item.active {
  background-color: rgba(24, 160, 88, 0.1);
  border: 1px solid rgba(24, 160, 88, 0.3);
}

.module-item.error {
  background-color: rgba(208, 48, 80, 0.1);
  border: 1px solid rgba(208, 48, 80, 0.3);
}

.module-item.checking {
  background-color: rgba(240, 160, 32, 0.1);
  border: 1px solid rgba(240, 160, 32, 0.3);
}

.module-info {
  flex: 1;
  min-width: 0;
}

.module-name {
  font-weight: 500;
  font-size: 14px;
}

.module-status {
  font-size: 12px;
  color: var(--n-text-color-3);
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.module-status.healthy {
  color: #18a058;
}

.module-status.unhealthy {
  color: #d03050;
}

.module-status.checking {
  color: #f0a020;
}

.latency {
  font-size: 11px;
  opacity: 0.8;
  margin-left: 4px;
  font-family: monospace;
}

.text-secondary {
  font-size: 12px;
  color: var(--n-text-color-3);
}
</style>