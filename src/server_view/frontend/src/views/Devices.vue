<template>
  <div class="devices-page">
    <n-space vertical :size="16">
      <n-h2>
        <n-text type="primary">嵌入式设备管理</n-text>
      </n-h2>

      <n-space justify="space-between" align="center">
        <n-button @click="refreshDevices" :loading="loading" type="primary">
          <template #icon>
            <n-icon><refresh-icon /></n-icon>
          </template>
          刷新设备列表
        </n-button>
        <n-tag v-if="devices.length > 0" type="success" round>
          在线设备: {{ devices.length }}
        </n-tag>
      </n-space>

      <n-empty v-if="!loading && devices.length === 0" description="暂无在线设备">
        <template #icon>
          <n-icon size="48"><device-icon /></n-icon>
        </template>
      </n-empty>

      <n-grid v-else :cols="1" :x-gap="12" :y-gap="12">
        <n-grid-item v-for="device in devices" :key="device.device_id">
          <n-card :title="device.name" hoverable>
            <template #header-extra>
              <n-space>
                <n-tag type="success" round size="small">在线</n-tag>
                <n-popconfirm @positive-click="handleRemoveDevice(device.device_id)">
                  <template #trigger>
                    <n-button circle size="small" type="error">
                      <template #icon><n-icon><close-icon /></n-icon></template>
                    </n-button>
                  </template>
                  确定移除设备 {{ device.name }}?
                </n-popconfirm>
              </n-space>
            </template>

            <n-descriptions label-placement="left" bordered :column="1" size="small">
              <n-descriptions-item label="设备ID">
                <n-text code>{{ device.device_id }}</n-text>
              </n-descriptions-item>
              <n-descriptions-item label="描述">
                {{ device.description || '无描述' }}
              </n-descriptions-item>
              <n-descriptions-item label="注册时间">
                {{ formatTime(device.register_time) }}
              </n-descriptions-item>
            </n-descriptions>

            <n-divider />

            <n-h5>可用功能</n-h5>
            <n-empty v-if="!device.functions || device.functions.length === 0" description="无可用功能" />
            <n-space v-else>
              <n-tag v-for="fn in device.functions" :key="fn.name" type="info" size="small">
                {{ fn.name }}
              </n-tag>
            </n-space>

            <template #action>
              <n-space justify="center">
                <n-button @click="showRpcModal(device)" type="primary" size="small">
                  <template #icon><n-icon><terminal-icon /></n-icon></template>
                  发送RPC命令
                </n-button>
              </n-space>
            </template>
          </n-card>
        </n-grid-item>
      </n-grid>
    </n-space>

    <!-- RPC 发送对话框 -->
    <n-modal v-model:show="rpcModalVisible" title="发送 RPC 命令" preset="card" style="width: 600px">
      <n-space vertical>
        <n-alert type="info" :title="'目标设备: ' + (rpcTarget?.name || '')" closable>
          输入 JSON-RPC 2.0 调用字符串
        </n-alert>
        <n-input
          v-model:value="rpcPayload"
          type="textarea"
          :rows="6"
          placeholder='{"method": "set_speed", "params": {"value": 100}, "id": 1}'
        />
        <n-space justify="end">
          <n-button @click="rpcModalVisible = false">取消</n-button>
          <n-button @click="handleSendRpc" type="primary" :loading="rpcSending">
            发送
          </n-button>
        </n-space>
      </n-space>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { useWebSocketStore } from '@/stores/websocket'
import {
  RefreshOutline as RefreshIcon,
  HardwareChipOutline as DeviceIcon,
  CloseOutline as CloseIcon,
  TerminalOutline as TerminalIcon
} from '@vicons/ionicons5'

const message = useMessage()
const wsStore = useWebSocketStore()

const loading = ref(false)
const devices = ref<any[]>([])
const rpcModalVisible = ref(false)
const rpcTarget = ref<any>(null)
const rpcPayload = ref('')
const rpcSending = ref(false)

function formatTime(t: number | string) {
  if (!t) return '未知'
  const d = typeof t === 'number' ? new Date(t * 1000) : new Date(t)
  return d.toLocaleString()
}

function refreshDevices() {
  loading.value = true
  const socket = wsStore.socket
  if (socket?.connected) {
    socket.emit('get_devices')
  } else {
    fetchDevicesHttp()
  }
}

async function fetchDevicesHttp() {
  try {
    const res = await fetch('/api/devices')
    const json = await res.json()
    if (json.success) {
      devices.value = json.data || []
    }
  } catch (e) {
    console.error('获取设备列表失败', e)
  } finally {
    loading.value = false
  }
}

function showRpcModal(device: any) {
  rpcTarget.value = device
  rpcPayload.value = ''
  rpcModalVisible.value = true
}

async function handleSendRpc() {
  if (!rpcTarget.value || !rpcPayload.value) return
  rpcSending.value = true
  const socket = wsStore.socket
  if (socket?.connected) {
    socket.emit('send_device_rpc', {
      device_id: rpcTarget.value.device_id,
      rpc_call: rpcPayload.value
    })
  }
  rpcSending.value = false
  rpcModalVisible.value = false
}

function handleRemoveDevice(deviceId: string) {
  devices.value = devices.value.filter(d => d.device_id !== deviceId)
}

function onDevicesList(data: any) {
  loading.value = false
  if (data.success) {
    devices.value = data.data || []
  }
}

function onDeviceRpcResult(data: any) {
  if (data.success) {
    message.success(data.message || 'RPC 命令已发送到设备')
  } else {
    message.error(data.error || 'RPC 发送失败')
  }
}

function onDeviceRpcResponse(data: any) {
  const payload = data.payload || {}
  const result = payload.result
  const error = payload.error
  const devId = data.device_id || ''

  if (error) {
    message.error(`设备 ${devId} RPC 返回错误: ${JSON.stringify(error)}`)
  } else {
    message.success(`设备 ${devId} RPC 返回: ${JSON.stringify(result)}`)
  }
}

onMounted(() => {
  const socket = wsStore.socket
  if (socket) {
    socket.on('devices_list', onDevicesList)
    socket.on('device_rpc_result', onDeviceRpcResult)
    socket.on('device_rpc_response', onDeviceRpcResponse)
  }
  refreshDevices()
})

onUnmounted(() => {
  const socket = wsStore.socket
  if (socket) {
    socket.off('devices_list', onDevicesList)
    socket.off('device_rpc_result', onDeviceRpcResult)
    socket.off('device_rpc_response', onDeviceRpcResponse)
  }
})
</script>

<style scoped>
.devices-page {
  max-width: 1200px;
  margin: 0 auto;
}
</style>
