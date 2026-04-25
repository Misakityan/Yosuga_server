import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import axios from 'axios'

export const usePreferencesStore = defineStore('preferences', () => {
  // 用户偏好状态
  const preferences = ref({
    theme: 'light',           // 'light' | 'dark' | 'auto'
    sidebarCollapsed: false,
    logLevel: 'ALL',          // 默认日志等级筛选
    logAutoScroll: true,      // 日志自动滚动
    refreshInterval: 2000,    // 数据刷新间隔(ms)
    lastVisitedPage: 'dashboard',
    favoriteConfigs: [] as string[], // 收藏的配置项
    notifications: {
      coreStatus: true,       // 核心状态变化通知
      errors: true            // 错误通知
    }
  })

  const isLoaded = ref(false)

  // 从服务器加载偏好
  const loadPreferences = async () => {
    try {
      const response = await axios.get('/api/preferences')
      if (response.data.success) {
        preferences.value = { ...preferences.value, ...response.data.data }
        applyTheme(preferences.value.theme)
      }
    } catch (error) {
      console.error('加载偏好失败:', error)
      // 从 localStorage 回退
      const local = localStorage.getItem('yosuga_preferences')
      if (local) {
        preferences.value = { ...preferences.value, ...JSON.parse(local) }
      }
    } finally {
      isLoaded.value = true
    }
  }

  // 保存偏好到服务器和本地
  const savePreferences = async () => {
    try {
      await axios.post('/api/preferences', preferences.value)
      localStorage.setItem('yosuga_preferences', JSON.stringify(preferences.value))
    } catch (error) {
      console.error('保存偏好失败:', error)
      // 至少保存到本地
      localStorage.setItem('yosuga_preferences', JSON.stringify(preferences.value))
    }
  }

  // 应用主题
  const applyTheme = (theme: string) => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark')
    } else if (theme === 'light') {
      document.documentElement.classList.remove('dark')
    } else {
      // auto: 跟随系统
      if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.classList.add('dark')
      } else {
        document.documentElement.classList.remove('dark')
      }
    }
  }

  // 设置主题
  const setTheme = (theme: string) => {
    preferences.value.theme = theme
    applyTheme(theme)
    savePreferences()
  }

  // 切换侧边栏
  const toggleSidebar = () => {
    preferences.value.sidebarCollapsed = !preferences.value.sidebarCollapsed
    savePreferences()
  }

  // 设置日志等级
  const setLogLevel = (level: string) => {
    preferences.value.logLevel = level
    savePreferences()
  }

  // 监听系统主题变化
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      if (preferences.value.theme === 'auto') {
        applyTheme('auto')
      }
    })
  }

  // 自动保存（防抖）
  let saveTimer: NodeJS.Timeout
  watch(preferences, () => {
    clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      savePreferences()
    }, 500)
  }, { deep: true })

  return {
    preferences,
    isLoaded,
    loadPreferences,
    savePreferences,
    setTheme,
    toggleSidebar,
    setLogLevel
  }
})