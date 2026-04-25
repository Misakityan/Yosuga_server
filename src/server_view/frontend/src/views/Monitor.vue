<template>
  <div class="monitor-page">
    <n-grid :x-gap="16" :y-gap="16" cols="1 l:2">
      <n-gi>
        <n-card title="CPU 使用率历史" :bordered="false">
          <v-chart class="chart" :option="cpuChartOption" autoresize />
        </n-card>
      </n-gi>

      <n-gi>
        <n-card title="内存使用历史" :bordered="false">
          <v-chart class="chart" :option="memoryChartOption" autoresize />
        </n-card>
      </n-gi>
    </n-grid>

    <n-card title="实时指标" class="metrics-card" :bordered="false">
      <n-descriptions bordered :column="3">
        <n-descriptions-item label="CPU 核心数">
          {{ systemStats.cpu.count }}
        </n-descriptions-item>
        <n-descriptions-item label="内存总量">
          {{ formatBytes(systemStats.memory.total) }}
        </n-descriptions-item>
        <n-descriptions-item label="磁盘使用率">
          {{ systemStats.disk.percent?.toFixed(1) }}%
        </n-descriptions-item>
        <n-descriptions-item label="进程内存占用">
          {{ systemStats.process.memory_percent?.toFixed(2) }}%
        </n-descriptions-item>
        <n-descriptions-item label="进程 CPU 占用">
          {{ systemStats.process.cpu_percent?.toFixed(1) }}%
        </n-descriptions-item>
        <n-descriptions-item label="线程数">
          {{ systemStats.process.threads }}
        </n-descriptions-item>
      </n-descriptions>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent
} from 'echarts/components'
import VChart from 'vue-echarts'

use([
  CanvasRenderer,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent
])

const systemStats = ref({
  cpu: { percent: 0, count: 0 },
  memory: { total: 0, percent: 0 },
  disk: { percent: 0 },
  process: { memory_percent: 0, cpu_percent: 0, threads: 0 }
})

const cpuHistory = ref<number[]>([])
const memoryHistory = ref<number[]>([])
const timeLabels = ref<string[]>([])

const cpuChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: timeLabels.value
  },
  yAxis: {
    type: 'value',
    max: 100,
    axisLabel: { formatter: '{value}%' }
  },
  series: [{
    name: 'CPU',
    type: 'line',
    smooth: true,
    areaStyle: {
      color: {
        type: 'linear',
        x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(24, 160, 88, 0.3)' },
          { offset: 1, color: 'rgba(24, 160, 88, 0.05)' }
        ]
      }
    },
    lineStyle: { color: '#18a058' },
    itemStyle: { color: '#18a058' },
    data: cpuHistory.value
  }]
}))

const memoryChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: timeLabels.value
  },
  yAxis: {
    type: 'value',
    max: 100,
    axisLabel: { formatter: '{value}%' }
  },
  series: [{
    name: '内存',
    type: 'line',
    smooth: true,
    areaStyle: {
      color: {
        type: 'linear',
        x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(32, 128, 240, 0.3)' },
          { offset: 1, color: 'rgba(32, 128, 240, 0.05)' }
        ]
      }
    },
    lineStyle: { color: '#2080f0' },
    itemStyle: { color: '#2080f0' },
    data: memoryHistory.value
  }]
}))

const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

let intervalId: NodeJS.Timeout

const fetchStats = async () => {
  try {
    const res = await axios.get('/api/system/info')
    if (res.data.success) {
      systemStats.value = res.data.data

      cpuHistory.value.push(res.data.data.cpu.percent)
      memoryHistory.value.push(res.data.data.memory.percent)
      timeLabels.value.push(new Date().toLocaleTimeString())

      if (cpuHistory.value.length > 20) {
        cpuHistory.value.shift()
        memoryHistory.value.shift()
        timeLabels.value.shift()
      }
    }
  } catch (error) {
    console.error('获取监控数据失败:', error)
  }
}

onMounted(() => {
  fetchStats()
  intervalId = setInterval(fetchStats, 2000)
})

onUnmounted(() => {
  clearInterval(intervalId)
})
</script>

<style scoped>
.monitor-page {
  max-width: 1400px;
  margin: 0 auto;
}

.chart {
  height: 300px;
  width: 100%;
}

.metrics-card {
  margin-top: 24px;
}
</style>