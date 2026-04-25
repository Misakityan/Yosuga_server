<template>
  <div class="logs-terminal-page">
    <!-- 终端工具栏 -->
    <div class="terminal-toolbar">
      <n-space align="center" justify="space-between" style="width: 100%">
        <n-space align="center">
          <n-icon size="20" color="#18a058"><terminal-icon /></n-icon>
          <span class="toolbar-title">系统日志终端</span>
          <n-divider vertical />

          <!-- 日志统计 -->
          <n-tag size="small" :type="logStats.error > 0 ? 'error' : 'default'">
            ERROR: {{ logStats.error }}
          </n-tag>
          <n-tag size="small" type="warning">
            WARN: {{ logStats.warn }}
          </n-tag>
          <n-tag size="small" type="info">
            INFO: {{ logStats.info }}
          </n-tag>
          <span class="total-logs">总计: {{ wsStore.logs.length }} 行</span>
        </n-space>

        <n-space align="center">
          <!-- 自动跟随开关（终端核心功能） -->
          <n-tooltip>
            <template #trigger>
              <n-button
                :type="isFollowing ? 'primary' : 'default'"
                size="small"
                @click="toggleFollow"
                :class="{ 'following': isFollowing }"
              >
                <template #icon>
                  <n-icon>
                    <caret-down-icon v-if="isFollowing" />
                    <pause-icon v-else />
                  </n-icon>
                </template>
                {{ isFollowing ? '跟随' : '暂停' }}
              </n-button>
            </template>
            <span>{{ isFollowing ? '自动滚动到底部' : '已暂停自动滚动' }}</span>
          </n-tooltip>

          <!-- 等级筛选 -->
          <n-select
            v-model:value="selectedLevel"
            :options="levelOptions"
            style="width: 100px"
            size="small"
            @update:value="handleLevelChange"
          />

          <!-- 搜索 -->
          <n-input
            v-model:value="searchText"
            placeholder="搜索日志..."
            size="small"
            clearable
            style="width: 150px"
          >
            <template #prefix>
              <n-icon><search-icon /></n-icon>
            </template>
          </n-input>

          <n-divider vertical />

          <n-button size="small" @click="clearLogs" type="error" quaternary>
            <template #icon><n-icon><trash-icon /></n-icon></template>
            清空
          </n-button>

          <n-button size="small" @click="downloadLogs">
            <template #icon><n-icon><download-icon /></n-icon></template>
            导出
          </n-button>

          <n-tag :type="wsStore.status === 'connected' ? 'success' : 'error'" size="small">
            {{ wsStore.status === 'connected' ? '● 实时' : '● 离线' }}
          </n-tag>
        </n-space>
      </n-space>
    </div>

    <!-- 终端主体区域 -->
    <div class="terminal-container" ref="terminalContainer">
      <!-- 新日志提示条（当不在底部且有新日志时显示） -->
      <div
        v-show="hasNewLogs && !isFollowing"
        class="new-logs-indicator"
        @click="scrollToBottom"
      >
        <n-icon><arrow-down-icon /></n-icon>
        <span>{{ newLogsCount }} 条新日志 - 点击滚动到底部</span>
      </div>

      <!-- 日志内容区域（终端风格） -->
      <div
        class="terminal-content"
        ref="logContent"
        @scroll="handleScroll"
      >
        <div
          v-for="(log, index) in filteredLogs"
          :key="index"
          class="terminal-line"
          :class="getLogLevelClass(log)"
        >
          <!-- 时间戳 -->
          <span class="timestamp" v-if="showTimestamp">
            {{ extractTimestamp(log) }}
          </span>

          <!-- 日志等级标签 -->
          <span class="level-badge" :class="getLogLevelClass(log)">
            {{ getLogLevelLabel(log) }}
          </span>

          <!-- 日志内容（可点击选择复制） -->
          <span
            class="log-message"
            v-html="highlightSearch(log)"
            @dblclick="selectLine(log)"
          ></span>
        </div>

        <!-- 空状态 -->
        <div v-if="filteredLogs.length === 0" class="empty-terminal">
          <n-empty description="暂无日志输出" size="small">
            <template #icon>
              <n-icon :size="40" color="#333"><terminal-outline-icon /></n-icon>
            </template>
          </n-empty>
        </div>

        <!-- 底部锚点（用于自动滚动定位） -->
        <div ref="bottomAnchor" class="bottom-anchor"></div>
      </div>
    </div>

    <!-- 终端状态栏 -->
    <div class="terminal-statusbar">
      <n-space align="center" justify="space-between" style="width: 100%">
        <n-space align="center" size="small">
          <span v-if="selectedLine" class="selected-info">
            已选择: {{ selectedLine.substring(0, 50) }}{{ selectedLine.length > 50 ? '...' : '' }}
          </span>
          <span v-else class="hint-text">
            提示: 双击行选择文本 | Ctrl+F 搜索 | 滚轮查看历史
          </span>
        </n-space>

        <n-space align="center" size="small">
          <span class="status-item">滚动位置: {{ scrollPercent }}%</span>
          <span class="status-item">显示: {{ filteredLogs.length }}/{{ wsStore.logs.length }}</span>
          <span class="status-item" :class="{ 'following-active': isFollowing }">
            {{ isFollowing ? '● 跟随模式' : '○ 手动浏览' }}
          </span>
        </n-space>
      </n-space>
    </div>

    <!-- 行详情弹窗（双击行时显示完整内容） -->
    <n-modal v-model:show="showLineDetail" title="日志详情" style="width: 800px">
      <n-card>
        <div class="line-detail-content">{{ selectedLine }}</div>
        <n-space justify="end" style="margin-top: 16px;">
          <n-button @click="copySelectedLine">复制</n-button>
          <n-button @click="showLineDetail = false">关闭</n-button>
        </n-space>
      </n-card>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import {
  TrashOutline as TrashIcon,
  DownloadOutline as DownloadIcon,
  SearchOutline as SearchIcon,
  TerminalOutline as TerminalIcon,
  CaretDownOutline as CaretDownIcon,
  PauseOutline as PauseIcon,
  ArrowDownOutline as ArrowDownIcon
} from '@vicons/ionicons5'
import { useWebSocketStore } from '@/stores/websocket'
import { useMessage, useDialog } from 'naive-ui'

const wsStore = useWebSocketStore()
const message = useMessage()
const dialog = useDialog()

// DOM引用
const terminalContainer = ref<HTMLElement>()
const logContent = ref<HTMLElement>()
const bottomAnchor = ref<HTMLElement>()

// 状态
const selectedLevel = ref('ALL')
const searchText = ref('')
const isFollowing = ref(true)  // 终端核心：是否自动跟随底部
const hasNewLogs = ref(false)  // 有新日志但未跟随
const newLogsCount = ref(0)
const showTimestamp = ref(true)
const selectedLine = ref('')
const showLineDetail = ref(false)
const scrollPercent = ref(100)

// 用于判断是否在底部的阈值（像素）
const BOTTOM_THRESHOLD = 50

// 日志等级定义
const LOG_LEVELS = [
  { key: 'DEBUG', label: 'DEBUG', color: '#569cd6', weight: 1 },
  { key: 'INFO', label: 'INFO', color: '#4ec9b0', weight: 2 },
  { key: 'SUCCESS', label: 'OK', color: '#4ec9b0', weight: 2 },
  { key: 'WARNING', label: 'WARN', color: '#dcdcaa', weight: 3 },
  { key: 'ERROR', label: 'ERR', color: '#f44747', weight: 4 },
  { key: 'CRITICAL', label: 'CRIT', color: '#f44747', weight: 5 }
]

const levelOptions = [
  { label: '全部', value: 'ALL' },
  { label: '调试', value: 'DEBUG' },
  { label: '信息', value: 'INFO' },
  { label: '警告', value: 'WARNING' },
  { label: '错误', value: 'ERROR' },
  { label: '严重', value: 'CRITICAL' }
]

// 统计各等级日志数量
const logStats = computed(() => {
  const stats = { error: 0, warn: 0, info: 0, debug: 0 }
  wsStore.logs.forEach(log => {
    const level = getLogLevel(log)
    if (level === 'error' || level === 'critical') stats.error++
    else if (level === 'warning') stats.warn++
    else if (level === 'info' || level === 'success') stats.info++
    else stats.debug++
  })
  return stats
})

// 过滤后的日志
const filteredLogs = computed(() => {
  let logs = [...wsStore.logs]

  // 等级过滤
  if (selectedLevel.value !== 'ALL') {
    const targetLevel = selectedLevel.value.toLowerCase()
    logs = logs.filter(log => {
      const level = getLogLevel(log)
      if (selectedLevel.value === 'ERROR') {
        return level === 'error' || level === 'critical'
      }
      return level === targetLevel
    })
  }

  // 搜索过滤
  if (searchText.value) {
    const keyword = searchText.value.toLowerCase()
    logs = logs.filter(log => log.toLowerCase().includes(keyword))
  }

  return logs
})

// 获取日志等级
const getLogLevel = (log: string): string => {
  for (const level of LOG_LEVELS) {
    if (log.includes(`| ${level.key} |`) ||
        log.includes(`[${level.key}]`) ||
        log.includes(` ${level.key} `)) {
      return level.key.toLowerCase()
    }
  }
  return 'other'
}

const getLogLevelClass = (log: string): string => {
  return getLogLevel(log)
}

const getLogLevelLabel = (log: string): string => {
  const level = getLogLevel(log)
  if (level === 'other') return 'LOG'
  const found = LOG_LEVELS.find(l => l.key.toLowerCase() === level)
  return found ? found.label : 'LOG'
}

// 提取时间戳
const extractTimestamp = (log: string): string => {
  const match = log.match(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)/)
  return match ? match[1].split(' ')[1] : '' // 只返回时间部分
}

// 高亮搜索词
const highlightSearch = (log: string) => {
  if (!searchText.value) return escapeHtml(log)
  const regex = new RegExp(`(${escapeRegex(searchText.value)})`, 'gi')
  return escapeHtml(log).replace(regex, '<mark>$1</mark>')
}

const escapeHtml = (text: string): string => {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

const escapeRegex = (string: string): string => {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// 核心：滚动到底部（终端行为）
const scrollToBottom = async (smooth = false) => {
  await nextTick()
  if (bottomAnchor.value) {
    bottomAnchor.value.scrollIntoView({
      behavior: smooth ? 'smooth' : 'auto',
      block: 'end'
    })
  }
  hasNewLogs.value = false
  newLogsCount.value = 0
  scrollPercent.value = 100
}

// 检查是否在底部
const checkIfNearBottom = (): boolean => {
  if (!logContent.value) return true
  const { scrollTop, scrollHeight, clientHeight } = logContent.value
  const distanceToBottom = scrollHeight - scrollTop - clientHeight
  return distanceToBottom < BOTTOM_THRESHOLD
}

// 处理滚动事件
const handleScroll = () => {
  if (!logContent.value) return

  const { scrollTop, scrollHeight, clientHeight } = logContent.value
  const distanceToBottom = scrollHeight - scrollTop - clientHeight

  // 计算滚动百分比
  scrollPercent.value = Math.round(((scrollTop + clientHeight) / scrollHeight) * 100)

  // 如果用户手动滚动离开底部，暂停自动跟随
  if (distanceToBottom > BOTTOM_THRESHOLD && isFollowing.value) {
    isFollowing.value = false
    console.log('用户手动滚动，暂停跟随')
  }

  // 如果用户滚动到底部附近，恢复跟随
  if (distanceToBottom < BOTTOM_THRESHOLD && !isFollowing.value) {
    isFollowing.value = true
    hasNewLogs.value = false
    newLogsCount.value = 0
  }
}

// 切换跟随模式
const toggleFollow = () => {
  isFollowing.value = !isFollowing.value
  if (isFollowing.value) {
    scrollToBottom(true)
    message.success('已恢复自动跟随')
  } else {
    message.info('已暂停自动跟随，可自由查看历史日志')
  }
}

// 监听日志变化（核心：自动滚动逻辑）
watch(() => wsStore.logs.length, (newLength, oldLength) => {
  if (newLength > oldLength) {
    const added = newLength - oldLength
    if (!isFollowing.value) {
      // 不跟随状态下累积新日志计数
      hasNewLogs.value = true
      newLogsCount.value += added
    } else {
      // 跟随状态下自动滚到底部
      scrollToBottom(false)
    }
  }
})

// 监听过滤条件变化（重新计算后保持在当前位置或底部）
watch([selectedLevel, searchText], () => {
  if (isFollowing.value) {
    nextTick(() => scrollToBottom(false))
  }
})

// 处理等级变更
const handleLevelChange = (level: string) => {
  wsStore.subscribeWithLevel(level)
}

// 清空日志
const clearLogs = () => {
  dialog.warning({
    title: '清空日志',
    content: '确定要清空所有日志吗？此操作不可恢复。',
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: () => {
      wsStore.clearLogs()
      hasNewLogs.value = false
      newLogsCount.value = 0
      message.success('日志已清空')
    }
  })
}

// 下载日志
const downloadLogs = () => {
  const blob = new Blob([wsStore.logs.join('\n')], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `yosuga-logs-${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.log`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// 双击选择行
const selectLine = (log: string) => {
  selectedLine.value = log
  showLineDetail.value = true
}

const copySelectedLine = () => {
  navigator.clipboard.writeText(selectedLine.value)
  message.success('已复制到剪贴板')
}

// 键盘快捷键
const handleKeydown = (e: KeyboardEvent) => {
  if (e.ctrlKey && e.key === 'f') {
    e.preventDefault()
    // 聚焦搜索框
    const searchInput = document.querySelector('.logs-terminal-page input') as HTMLInputElement
    searchInput?.focus()
  }
  if (e.key === 'Escape') {
    isFollowing.value = true
    scrollToBottom()
  }
}

onMounted(() => {
  // 初始滚动到底部
  setTimeout(() => scrollToBottom(false), 100)

  // 监听键盘
  window.addEventListener('keydown', handleKeydown)

  // 定期更新滚动位置显示（用于状态栏）
  const updateInterval = setInterval(() => {
    if (logContent.value && isFollowing.value) {
      scrollPercent.value = 100
    }
  }, 1000)

  return () => clearInterval(updateInterval)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
/* 终端页面布局 */
.logs-terminal-page {
  height: calc(100vh - 140px);
  display: flex;
  flex-direction: column;
  background: #1e1e1e; /* VS Code终端深色背景 */
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #333;
}

/* 工具栏 */
.terminal-toolbar {
  padding: 12px 16px;
  background: #252526;
  border-bottom: 1px solid #333;
  display: flex;
  align-items: center;
}

.toolbar-title {
  font-weight: 600;
  color: #cccccc;
  font-size: 14px;
}

.total-logs {
  font-size: 12px;
  color: #858585;
  margin-left: 8px;
}

/* 终端主体 */
.terminal-container {
  flex: 1;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 新日志提示条 */
.new-logs-indicator {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  background: rgba(24, 160, 88, 0.9);
  color: white;
  text-align: center;
  padding: 8px;
  cursor: pointer;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  transition: opacity 0.3s;
  backdrop-filter: blur(4px);
}

.new-logs-indicator:hover {
  background: rgba(24, 160, 88, 1);
}

/* 日志内容区域 - 终端风格 */
.terminal-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 16px;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  background: #1e1e1e;
  color: #d4d4d4;

  /* 终端滚动条样式 */
  scrollbar-width: thin;
  scrollbar-color: #424242 #1e1e1e;
}

.terminal-content::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.terminal-content::-webkit-scrollbar-track {
  background: #1e1e1e;
}

.terminal-content::-webkit-scrollbar-thumb {
  background: #424242;
  border-radius: 5px;
}

.terminal-content::-webkit-scrollbar-thumb:hover {
  background: #4f4f4f;
}

/* 终端行样式 */
.terminal-line {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 2px 0;
  white-space: pre-wrap;
  word-break: break-all;
  border-radius: 2px;
  transition: background-color 0.1s;
}

.terminal-line:hover {
  background-color: rgba(255, 255, 255, 0.03);
}

/* 时间戳 */
.timestamp {
  color: #858585;
  font-size: 12px;
  min-width: 80px;
  flex-shrink: 0;
  user-select: none;
}

/* 等级标签 */
.level-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 45px;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
  font-family: monospace;
  text-transform: uppercase;
}

.level-badge.debug {
  background-color: rgba(86, 156, 214, 0.15);
  color: #569cd6;
}

.level-badge.info,
.level-badge.success {
  background-color: rgba(78, 201, 176, 0.15);
  color: #4ec9b0;
}

.level-badge.warning {
  background-color: rgba(220, 220, 170, 0.15);
  color: #dcdcaa;
}

.level-badge.error,
.level-badge.critical {
  background-color: rgba(244, 71, 71, 0.15);
  color: #f44747;
}

.level-badge.other {
  background-color: rgba(133, 133, 133, 0.15);
  color: #858585;
}

/* 日志消息 */
.log-message {
  flex: 1;
  color: #d4d4d4;
}

/* 错误行高亮 */
.terminal-line.error .log-message,
.terminal-line.critical .log-message {
  color: #f44747;
}

.terminal-line.warning .log-message {
  color: #dcdcaa;
}

.terminal-line.debug .log-message {
  color: #858585;
}

/* 搜索高亮 */
:deep(mark) {
  background-color: rgba(220, 220, 170, 0.4);
  color: #dcdcaa;
  padding: 0 2px;
  border-radius: 2px;
  font-weight: bold;
}

/* 空状态 */
.empty-terminal {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #858585;
}

/* 底部锚点 */
.bottom-anchor {
  height: 1px;
  flex-shrink: 0;
}

/* 状态栏 */
.terminal-statusbar {
  padding: 8px 16px;
  background: #252526;
  border-top: 1px solid #333;
  font-size: 12px;
  color: #858585;
  display: flex;
  align-items: center;
}

.status-item {
  padding: 0 8px;
  border-right: 1px solid #333;
}

.status-item:last-child {
  border-right: none;
}

.following-active {
  color: #4ec9b0;
}

.hint-text {
  color: #6e6e6e;
  font-style: italic;
}

.selected-info {
  color: #4ec9b0;
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 跟随按钮高亮 */
.following {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* 行详情弹窗 */
.line-detail-content {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 400px;
  overflow: auto;
  border: 1px solid #333;
}

/* 响应式 */
@media (max-width: 768px) {
  .timestamp {
    display: none;
  }

  .terminal-toolbar .n-space:first-child {
    display: none;
  }
}
</style>