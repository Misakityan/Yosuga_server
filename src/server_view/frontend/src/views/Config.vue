<template>
  <div class="config-page">
    <n-card title="全局配置管理" :bordered="false">
      <template #header-extra>
        <n-space>
          <n-button @click="fetchConfig" :loading="loading">
            <template #icon><n-icon><refresh-icon /></n-icon></template>
            刷新
          </n-button>
          <n-button type="primary" @click="handleSave" :loading="saving">
            <template #icon><n-icon><save-icon /></n-icon></template>
            保存更改
          </n-button>
          <n-button @click="showJson = true">
            <template #icon><n-icon><code-icon /></n-icon></template>
            查看JSON
          </n-button>
        </n-space>
      </template>

      <n-tabs type="line" animated v-model:value="activeTab">
        <!-- AI 模型配置 -->
        <n-tab-pane name="ai" tab="AI 模型">
          <n-alert type="info" style="margin-bottom: 16px" :show-icon="false">
            配置主对话AI服务，支持OpenAI、DeepSeek或本地LM Studio
          </n-alert>

          <n-form
            v-if="formData.ai"
            :model="formData.ai"
            label-placement="left"
            label-width="140px"
            require-mark-placement="right-hanging"
          >
            <n-form-item label="API Key">
              <n-input
                v-model:value="formData.ai.api_key"
                type="password"
                placeholder="sk-xxxxxxxxxxxxxxxx"
                show-password-on="click"
              />
              <template #feedback>留空使用本地模型或无需认证的端点</template>
            </n-form-item>

            <n-form-item label="Base URL">
              <n-input
                v-model:value="formData.ai.base_url"
                placeholder="http://localhost:1234/v1"
              />
              <template #feedback>API端点地址，本地LM Studio通常为 http://localhost:1234/v1</template>
            </n-form-item>

            <n-form-item label="模型名称">
              <n-input
                v-model:value="formData.ai.model_name"
                placeholder="qwen/qwen3-4b-2507"
              />
              <template #feedback>例如: gpt-4, deepseek-chat, qwen/qwen3-4b-2507</template>
            </n-form-item>

            <n-form-item label="Temperature">
              <n-space align="center" style="width: 100%">
                <n-slider
                  v-model:value="formData.ai.temperature"
                  :min="0"
                  :max="2"
                  :step="0.1"
                  style="width: 200px"
                />
                <n-input-number
                  v-model:value="formData.ai.temperature"
                  :min="0"
                  :max="2"
                  :step="0.1"
                  style="width: 100px"
                />
              </n-space>
              <template #feedback>控制随机性: 0=确定性, 1=平衡, 2=创造性</template>
            </n-form-item>

            <n-form-item label="Max Tokens">
              <n-input-number
                v-model:value="formData.ai.max_tokens"
                :min="256"
                :max="32768"
                style="width: 200px"
              />
              <template #feedback>单次回复最大token数，通常设为8192</template>
            </n-form-item>

            <n-form-item label="超时时间(秒)">
              <n-input-number
                v-model:value="formData.ai.timeout"
                :min="5"
                :max="300"
                style="width: 200px"
              />
              <template #feedback>API请求超时时间</template>
            </n-form-item>
          </n-form>
        </n-tab-pane>

        <!-- TTS 语音合成配置 -->
        <n-tab-pane name="tts" tab="语音合成 (TTS)">
          <n-alert type="info" style="margin-bottom: 16px" :show-icon="false">
            GPT-SoVITS 语音合成服务配置
          </n-alert>

          <n-form
            v-if="formData.tts"
            :model="formData.tts"
            label-placement="left"
            label-width="140px"
          >
            <n-form-item label="启用 TTS">
              <n-switch v-model:value="formData.tts.enabled" />
            </n-form-item>

            <n-divider title-placement="left">服务端连接</n-divider>

            <n-form-item label="主机地址">
              <n-input
                v-model:value="formData.tts.host"
                placeholder="localhost"
              />
            </n-form-item>

            <n-form-item label="端口">
              <n-input-number
                v-model:value="formData.tts.port"
                :min="1"
                :max="65535"
                style="width: 200px"
              />
              <template #feedback>GPT-SoVITS API默认端口 9880 或 20261</template>
            </n-form-item>

            <n-form-item label="API Key">
              <n-input
                v-model:value="formData.tts.api_key"
                type="password"
                placeholder="可选"
                show-password-on="click"
              />
            </n-form-item>

            <n-divider title-placement="left">模型配置</n-divider>

            <n-form-item label="GPT模型路径">
              <n-input
                v-model:value="formData.tts.gpt_model_name"
                placeholder="GPT_weights_v2Pro/Yosuga_Airi-e32.ckpt"
              />
              <template #feedback>相对于项目根目录的路径</template>
            </n-form-item>

            <n-form-item label="SoVITS模型路径">
              <n-input
                v-model:value="formData.tts.sovits_model_name"
                placeholder="SoVITS_weights_v2Pro/Yosuga_Airi_e16_s864.pth"
              />
              <template #feedback>相对于项目根目录的路径</template>
            </n-form-item>

            <n-divider title-placement="left">音频设置</n-divider>

            <n-form-item label="参考音频路径">
              <n-input
                v-model:value="formData.tts.reference_audio"
                placeholder="./using/reference.wav"
              />
              <template #feedback>用于声音克隆的参考音频文件路径</template>
            </n-form-item>

            <n-form-item label="流式输出">
              <n-switch v-model:value="formData.tts.streaming" />
              <template #feedback>启用流式传输可降低延迟</template>
            </n-form-item>

            <n-form-item label="语速倍率">
              <n-space align="center" style="width: 100%">
                <n-slider
                  v-model:value="formData.tts.speed"
                  :min="0.6"
                  :max="1.65"
                  :step="0.05"
                  style="width: 200px"
                />
                <span style="min-width: 50px">{{ formData.tts.speed }}x</span>
              </n-space>
            </n-form-item>
          </n-form>
        </n-tab-pane>

        <!-- ASR 语音识别配置 -->
        <n-tab-pane name="asr" tab="语音识别 (ASR)">
          <n-alert type="info" style="margin-bottom: 16px" :show-icon="false">
            Faster-Whisper 语音识别服务配置
          </n-alert>

          <n-form
            v-if="formData.asr"
            :model="formData.asr"
            label-placement="left"
            label-width="140px"
          >
            <n-form-item label="启用 ASR">
              <n-switch v-model:value="formData.asr.enabled" />
            </n-form-item>

            <n-form-item label="服务 URL">
              <n-input
                v-model:value="formData.asr.url"
                placeholder="http://localhost:20260/"
              />
              <template #feedback>ASR API端点地址，默认端口20260</template>
            </n-form-item>

            <n-form-item label="模型名称">
              <n-input
                v-model:value="formData.asr.model_name"
                placeholder="fast-whisper"
              />
              <template #feedback>使用的ASR模型标识</template>
            </n-form-item>

            <n-form-item label="API Key">
              <n-input
                v-model:value="formData.asr.api_key"
                type="password"
                placeholder="可选"
                show-password-on="click"
              />
            </n-form-item>
          </n-form>
        </n-tab-pane>

        <!-- 自动代理配置 -->
        <n-tab-pane name="auto_agent" tab="自动代理 (Agent)">
          <n-alert type="info" style="margin-bottom: 16px" :show-icon="false">
            UI-TARS 自动化操作代理配置，用于GUI控制
          </n-alert>

          <n-form
            v-if="formData.auto_agent"
            :model="formData.auto_agent"
            label-placement="left"
            label-width="140px"
          >
            <n-form-item label="启用自动代理">
              <n-switch v-model:value="formData.auto_agent.enabled" />
            </n-form-item>

            <n-form-item label="部署类型">
              <n-select
                v-model:value="formData.auto_agent.deployment_type"
                :options="[
                  { label: 'LM Studio (本地)', value: 'lmstudio' },
                  { label: 'vLLM (本地服务器)', value: 'vllm' },
                  { label: 'Ollama (本地)', value: 'ollama' },
                  { label: '云端 API', value: 'cloud' }
                ]"
                style="width: 200px"
              />
            </n-form-item>

            <n-form-item label="Base URL">
              <n-input
                v-model:value="formData.auto_agent.base_url"
                placeholder="http://localhost:1234/v1"
              />
              <template #feedback>UI-TARS模型服务端点</template>
            </n-form-item>

            <n-form-item label="模型名称">
              <n-input
                v-model:value="formData.auto_agent.model_name"
                placeholder="ui-tars-1.5-7b@q4_k_m"
              />
              <template #feedback>例如: ui-tars-1.5-7b, ui-tars-2.0-7b-sft</template>
            </n-form-item>

            <n-form-item label="API Key">
              <n-input
                v-model:value="formData.auto_agent.api_key"
                type="password"
                placeholder="可选，云端服务时需要"
                show-password-on="click"
              />
            </n-form-item>

            <n-form-item label="Temperature">
              <n-space align="center" style="width: 100%">
                <n-slider
                  v-model:value="formData.auto_agent.temperature"
                  :min="0"
                  :max="1"
                  :step="0.05"
                  style="width: 200px"
                />
                <n-input-number
                  v-model:value="formData.auto_agent.temperature"
                  :min="0"
                  :max="1"
                  :step="0.05"
                  style="width: 100px"
                />
              </n-space>
              <template #feedback>UI任务建议低温度(0.1-0.3)提高准确性</template>
            </n-form-item>

            <n-form-item label="Max Tokens">
              <n-input-number
                v-model:value="formData.auto_agent.max_tokens"
                :min="2048"
                :max="128000"
                :step="1024"
                style="width: 200px"
              />
              <template #feedback>UI-TARS需要较大token数来处理截图，建议16384+</template>
            </n-form-item>
          </n-form>
        </n-tab-pane>

        <!-- LLM 核心配置 -->
        <n-tab-pane name="llm_core" tab="LLM 核心">
          <n-alert type="info" style="margin-bottom: 16px" :show-icon="false">
            Yosuga LLM Core 行为配置
          </n-alert>

          <n-form
            v-if="formData.llm_core"
            :model="formData.llm_core"
            label-placement="left"
            label-width="140px"
          >
            <n-form-item label="启用 LLM核心">
              <n-switch v-model:value="formData.llm_core.enabled" />
            </n-form-item>

            <n-form-item label="启用历史记录">
              <n-switch v-model:value="formData.llm_core.enable_history" />
              <template #feedback>开启后LLM会记住对话上下文</template>
            </n-form-item>

            <n-form-item label="最大上下文 Tokens">
              <n-input-number
                v-model:value="formData.llm_core.max_context_tokens"
                :min="512"
                :max="32768"
                :step="512"
                style="width: 200px"
              />
              <template #feedback>上下文长度限制，超出会触发记忆清理</template>
            </n-form-item>

            <n-form-item label="回复语言">
              <n-select
                v-model:value="formData.llm_core.language"
                :options="[
                  { label: '日本语 (Japanese)', value: '日本语' },
                  { label: '中文 (Chinese)', value: 'zh_CN' },
                  { label: 'English', value: 'en' }
                ]"
                style="width: 200px"
              />
            </n-form-item>

            <n-form-item label="角色设定">
              <n-input
                v-model:value="formData.llm_core.role_character"
                type="textarea"
                :rows="6"
                placeholder="输入角色设定..."
              />
              <template #feedback>
                定义AI助手的性格、背景和行为方式
                <n-button text type="primary" size="tiny" @click="resetRoleToDefault">
                  恢复默认
                </n-button>
              </template>
            </n-form-item>
          </n-form>
        </n-tab-pane>
      </n-tabs>
    </n-card>

    <!-- JSON预览模态框 -->
    <n-modal v-model:show="showJson" title="当前配置 (JSON)" style="width: 800px">
      <n-card>
        <n-code :code="jsonPreview" language="json" style="max-height: 500px; overflow: auto;" />
        <n-space justify="end" style="margin-top: 16px;">
          <n-button @click="copyJson">复制到剪贴板</n-button>
          <n-button @click="showJson = false">关闭</n-button>
        </n-space>
      </n-card>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue'
import { useMessage } from 'naive-ui'
import {
  RefreshOutline as RefreshIcon,
  SaveOutline as SaveIcon,
  CodeWorkingOutline as CodeIcon
} from '@vicons/ionicons5'
import axios from 'axios'

const message = useMessage()
const activeTab = ref('ai')
const loading = ref(false)
const saving = ref(false)
const showJson = ref(false)

// 完整的配置数据结构（与后端config.py完全对应）
const formData = reactive({
  ai: {
    api_key: '',
    base_url: '',
    model_name: '',
    timeout: 30,
    temperature: 0.7,
    max_tokens: 8192
  },
  tts: {
    enabled: true,
    api_key: null as string | null,
    gpt_model_name: '',
    sovits_model_name: '',
    host: 'localhost',
    port: 20261,
    reference_audio: './using/reference.wav',
    streaming: true,
    speed: 1.0
  },
  asr: {
    enabled: true,
    api_key: null as string | null,
    model_name: 'fast-whisper',
    url: 'http://localhost:20260/'
  },
  auto_agent: {
    enabled: true,
    api_key: null as string | null,
    deployment_type: 'lmstudio',
    model_name: 'ui-tars-1.5-7b@q4_k_m',
    base_url: 'http://localhost:1234/v1',
    temperature: 0.1,
    max_tokens: 16384
  },
  llm_core: {
    enabled: true,
    role_character: '你是由Misakiotoha开发的助手稲葉愛理ちゃん，可以和用户一起玩游戏，聊天，做各种事情，性格抽象，没事爱整整活。',
    max_context_tokens: 2048,
    enable_history: true,
    language: '日本语'
  }
})

const defaultRole = '你是由Misakiotoha开发的助手稲葉愛理ちゃん，可以和用户一起玩游戏，聊天，做各种事情，性格抽象，没事爱整整活。'

const jsonPreview = computed(() => {
  return JSON.stringify({
    ai: formData.ai,
    tts: formData.tts,
    asr: formData.asr,
    auto_agent: formData.auto_agent,
    llm_core: formData.llm_core
  }, null, 2)
})

const fetchConfig = async () => {
  loading.value = true
  try {
    const response = await axios.get('/api/config')
    if (response.data.success) {
      const cfg = response.data.data

      // 深度合并配置（确保新字段也能显示）
      Object.assign(formData.ai, cfg.ai || {})
      Object.assign(formData.tts, cfg.tts || {})
      Object.assign(formData.asr, cfg.asr || {})
      Object.assign(formData.auto_agent, cfg.auto_agent || {})
      Object.assign(formData.llm_core, cfg.llm_core || {})
    }
  } catch (error) {
    console.error('获取配置失败:', error)
    message.error('获取配置失败')
  } finally {
    loading.value = false
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    // 保存当前选中的tab对应的配置节
    const section = activeTab.value
    const data = formData[section as keyof typeof formData]

    const response = await axios.post(`/api/config/${section}`, data)

    if (response.data.success) {
      message.success('配置已保存并生效')
    } else {
      message.error('保存失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error: any) {
    console.error('保存配置失败:', error)
    message.error('保存失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    saving.value = false
  }
}

const resetRoleToDefault = () => {
  formData.llm_core.role_character = defaultRole
  message.info('已恢复默认角色设定')
}

const copyJson = () => {
  navigator.clipboard.writeText(jsonPreview.value)
  message.success('已复制到剪贴板')
}

onMounted(() => {
  fetchConfig()
})
</script>

<style scoped>
.config-page {
  max-width: 1000px;
  margin: 0 auto;
}

:deep(.n-form-item-feedback) {
  font-size: 12px;
  color: var(--n-text-color-3);
  line-height: 1.4;
}

:deep(.n-divider) {
  margin: 24px 0 16px 0;
}

:deep(.n-divider__title) {
  font-size: 13px;
  color: var(--n-text-color-3);
  font-weight: 500;
}
</style>