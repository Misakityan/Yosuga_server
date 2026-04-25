// core.ts - 现在仅作为HTTP备用，主要逻辑迁移到websocket.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useCoreStore = defineStore('core', () => {
  // 保留HTTP方法作为备用
  const fetchStatus = async () => {
    try {
      const response = await axios.get('/api/core/status')
      return response.data.data
    } catch (error) {
      console.error('获取核心状态失败:', error)
      return null
    }
  }

  const startCore = async (): Promise<boolean> => {
    try {
      const response = await axios.post('/api/core/start')
      return response.data.success
    } catch (error) {
      return false
    }
  }

  const stopCore = async (): Promise<boolean> => {
    try {
      const response = await axios.post('/api/core/stop')
      return response.data.success
    } catch (error) {
      return false
    }
  }

  return {
    fetchStatus,
    startCore,
    stopCore
  }
})