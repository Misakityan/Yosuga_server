import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '@/views/Dashboard.vue'
import Monitor from '@/views/Monitor.vue'
import Devices from '@/views/Devices.vue'
import Config from '@/views/Config.vue'
import Logs from '@/views/Logs.vue'

const routes = [
  {
    path: '/',
    name: 'dashboard',
    component: Dashboard,
    meta: { title: '仪表板' }
  },
  {
    path: '/monitor',
    name: 'monitor',
    component: Monitor,
    meta: { title: '系统监控' }
  },
  {
    path: '/devices',
    name: 'devices',
    component: Devices,
    meta: { title: '设备管理' }
  },
  {
    path: '/config',
    name: 'config',
    component: Config,
    meta: { title: '配置管理' }
  },
  {
    path: '/logs',
    name: 'logs',
    component: Logs,
    meta: { title: '日志查看' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router