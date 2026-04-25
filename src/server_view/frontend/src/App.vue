<template>
  <n-config-provider :theme="currentTheme" :theme-overrides="themeOverrides">
    <n-loading-bar-provider>
      <n-dialog-provider>
        <n-notification-provider>
          <n-message-provider>
            <n-layout class="layout" position="absolute" has-sider>
              <!-- 侧边栏 -->
              <n-layout-sider
                bordered
                collapse-mode="width"
                :collapsed-width="64"
                :width="240"
                :collapsed="prefs.preferences.sidebarCollapsed"
                show-trigger
                @collapse="prefs.toggleSidebar()"
                @expand="prefs.toggleSidebar()"
              >
                <div class="logo">
                  <n-icon size="32" color="#18a058">
                    <logo-icon />
                  </n-icon>
                  <span v-if="!prefs.preferences.sidebarCollapsed" class="logo-text">Yosuga Server</span>
                </div>

                <n-menu
                  :collapsed="prefs.preferences.sidebarCollapsed"
                  :collapsed-width="64"
                  :collapsed-icon-size="22"
                  :options="menuOptions"
                  :value="activeKey"
                  @update:value="handleMenuUpdate"
                />
              </n-layout-sider>

              <!-- 主内容区 -->
              <n-layout>
                <n-layout-header bordered class="header">
                  <div class="header-left">
                    <n-breadcrumb>
                      <n-breadcrumb-item>Yosuga</n-breadcrumb-item>
                      <n-breadcrumb-item>{{ pageTitle }}</n-breadcrumb-item>
                    </n-breadcrumb>
                  </div>
                  <div class="header-right">
                    <!-- 主题切换 -->
                    <n-dropdown :options="themeOptions" @select="handleThemeSelect">
                      <n-button circle>
                        <template #icon>
                          <n-icon>
                            <sunny-icon v-if="prefs.preferences.theme === 'light'" />
                            <moon-icon v-else-if="prefs.preferences.theme === 'dark'" />
                            <contrast-icon v-else />
                          </n-icon>
                        </template>
                      </n-button>
                    </n-dropdown>

                    <n-badge :value="wsStatus === 'connected' ? 'Live' : 'Offline'"
                             :type="wsStatus === 'connected' ? 'success' : 'error'">
                      <n-button circle>
                        <template #icon>
                          <n-icon><wifi-icon /></n-icon>
                        </template>
                      </n-button>
                    </n-badge>
                  </div>
                </n-layout-header>

                <n-layout-content class="content">
                  <router-view v-slot="{ Component }">
                    <transition name="fade" mode="out-in">
                      <component :is="Component" />
                    </transition>
                  </router-view>
                </n-layout-content>
              </n-layout>
            </n-layout>
          </n-message-provider>
        </n-notification-provider>
      </n-dialog-provider>
    </n-loading-bar-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { darkTheme, lightTheme, type GlobalTheme, type DropdownOption } from 'naive-ui'
import {
  HomeOutline as HomeIcon,
  SettingsOutline as SettingsIcon,
  TerminalOutline as TerminalIcon,
  StatsChartOutline as StatsIcon,
  HardwareChipOutline as DeviceIcon,
  SunnyOutline as SunnyIcon,
  MoonOutline as MoonIcon,
  WifiOutline as WifiIcon,
  PulseOutline as LogoIcon,
  ContrastOutline as ContrastIcon
} from '@vicons/ionicons5'
import { useWebSocketStore } from '@/stores/websocket'
import { usePreferencesStore } from '@/stores/preferences'
import { storeToRefs } from 'pinia'
import { NIcon } from 'naive-ui'

const route = useRoute()
const router = useRouter()
const wsStore = useWebSocketStore()
const { status: wsStatus } = storeToRefs(wsStore)
const prefs = usePreferencesStore()

const activeKey = computed(() => route.name as string)
const pageTitle = computed(() => route.meta?.title as string || 'Dashboard')

// 主题计算
const currentTheme = computed<GlobalTheme | null>(() => {
  if (prefs.preferences.theme === 'dark') return darkTheme
  if (prefs.preferences.theme === 'light') return lightTheme
  return null // auto 时由 CSS 处理
})

const themeOverrides = {
  common: {
    primaryColor: '#18a058',
    primaryColorHover: '#36ad6a',
    primaryColorPressed: '#0c7a43',
  }
}

// 主题选项
const themeOptions: DropdownOption[] = [
  { label: '浅色模式', key: 'light', icon: () => h(NIcon, null, { default: () => h(SunnyIcon) }) },
  { label: '深色模式', key: 'dark', icon: () => h(NIcon, null, { default: () => h(MoonIcon) }) },
  { label: '跟随系统', key: 'auto', icon: () => h(NIcon, null, { default: () => h(ContrastIcon) }) }
]

const renderIcon = (icon: any) => {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const menuOptions = [
  { label: '仪表板', key: 'dashboard', icon: renderIcon(HomeIcon) },
  { label: '系统监控', key: 'monitor', icon: renderIcon(StatsIcon) },
  { label: '设备管理', key: 'devices', icon: renderIcon(DeviceIcon) },
  { label: '配置管理', key: 'config', icon: renderIcon(SettingsIcon) },
  { label: '日志查看', key: 'logs', icon: renderIcon(TerminalIcon) }
]

const handleMenuUpdate = (key: string) => {
  prefs.preferences.lastVisitedPage = key
  router.push({ name: key })
}

const handleThemeSelect = (key: string) => {
  prefs.setTheme(key)
}

onMounted(() => {
  prefs.loadPreferences()
  wsStore.connect()

  // 恢复上次访问的页面
  if (prefs.preferences.lastVisitedPage && prefs.preferences.lastVisitedPage !== 'dashboard') {
    router.push({ name: prefs.preferences.lastVisitedPage })
  }
})
</script>

<style>
/* 全局主题 CSS 变量 */
:root {
  color-scheme: light dark;
}

/* 深色模式自动适配 */
@media (prefers-color-scheme: dark) {
  :root:not(.light) {
    color-scheme: dark;
  }
}

:root.dark {
  color-scheme: dark;
}
</style>

<style scoped>
.layout {
  height: 100vh;
}

.logo {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border-bottom: 1px solid var(--n-border-color);
}

.logo-text {
  font-size: 18px;
  font-weight: 600;
  color: var(--n-text-color);
  white-space: nowrap;
}

.header {
  height: 64px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.content {
  padding: 24px;
  background-color: var(--n-color);
  overflow-y: auto;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>