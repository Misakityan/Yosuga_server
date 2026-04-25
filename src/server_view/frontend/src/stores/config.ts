import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export interface ASRConfig {
  enabled: boolean
  url: string
  model_name: string
}

export interface TTSConfig {
  enabled: boolean
  host: string
  port: number
  gpt_model_name: string
  sovits_model_name: string
  streaming: boolean
}

export interface AIConfig {
  api_key: string | null
  base_url: string
  model_name: string
  temperature: number
  max_tokens: number
}

export interface AppConfigState {
  version: string
  debug: boolean
  ai: AIConfig
  tts: TTSConfig
  asr: ASRConfig
  auto_agent: any
  llm_core: any
}

export const useConfigStore = defineStore('config', () => {
  const config = ref<AppConfigState | null>(null)
  const loading = ref(false)
  const saving = ref(false)

  const fetchConfig = async () => {
    loading.value = true
    try {
      const response = await axios.get('/api/config')
      if (response.data.success) {
        config.value = response.data.data
      }
    } catch (error) {
      console.error('获取配置失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const updateConfig = async (section: string, data: any) => {
    saving.value = true
    try {
      const response = await axios.post(`/api/config/${section}`, data)
      if (response.data.success) {
        if (config.value) {
          (config.value as any)[section] = data
        }
        return true
      }
      return false
    } catch (error) {
      console.error('更新配置失败:', error)
      throw error
    } finally {
      saving.value = false
    }
  }

  const reloadConfig = async () => {
    try {
      const response = await axios.post('/api/config/reload')
      return response.data.success
    } catch (error) {
      console.error('重载配置失败:', error)
      throw error
    }
  }

  return {
    config,
    loading,
    saving,
    fetchConfig,
    updateConfig,
    reloadConfig
  }
})