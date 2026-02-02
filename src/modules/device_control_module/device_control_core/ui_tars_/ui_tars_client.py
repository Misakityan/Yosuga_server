# ui_tars_/ui_tars_client.py
from typing import Optional
from loguru import logger
import asyncio
from src.modules.text_ai_module.text_ai_core.general_text_ai_req import (
    UnifiedLLM,
    ModelConfig,
    ModelProvider,
    ChatMessage,
)
from pydantic import BaseModel, Field
from src.modules.device_control_module.device_control_core.ui_tars_.ui_tars_prompts import UI_TARS_SYSTEM_PROMPT


class UITarsClientConfig(BaseModel):
    """UI-TARS 客户端配置"""
    deployment_type: str = Field(default="lmstudio", description="部署类型")
    base_url: str = Field(default="http://localhost:1234/v1", description="API地址")
    model_name: str = Field(default="ui-tars", description="模型名称")
    api_key: Optional[str] = Field(default=None, description="API密钥")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8192, ge=2048, le=128000)
    timeout: int = Field(default=30, ge=5, le=300)

    # UI-TARS-1.5 强制输出格式
    system_prompt: str = Field(
        default=UI_TARS_SYSTEM_PROMPT   # 使用本项目自定义的输出格式约束
    )

    def to_model_config(self) -> ModelConfig:
        """转换为 UnifiedLLM 配置"""
        # 映射部署类型到 ModelProvider
        provider_map = {
            "lmstudio": ModelProvider.LM_STUDIO,
            "vllm": ModelProvider.CUSTOM,
            "cloud": ModelProvider.OPENAI,
            "ollama": ModelProvider.OLLAMA
        }
        provider = provider_map.get(self.deployment_type, ModelProvider.CUSTOM)
        return ModelConfig(
            provider=provider,
            model_name=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            custom_headers={"User-Agent": "UI-TARS-Client/1.0"}
        )

class UITarsClient:
    """
    UI-TARS 通用客户端 (基于 UnifiedLLM)
    图片相关信息请直接传入相应的base64
    """
    def __init__(self, config: UITarsClientConfig):
        self.config = config
        # 复用 UnifiedLLM，自动处理所有部署类型
        self.llm = UnifiedLLM(config.to_model_config())

        logger.info(f"UI-TARS 客户端初始化: {config.deployment_type} @ {config.base_url}")
        logger.info(f"   模型: {config.model_name} | 温度: {config.temperature}")

    async def call_async(self, instruction: str, image_base64: str) -> str:
        """异步调用 UI-TARS"""
        # 构建消息
        messages = self._build_messages(instruction, image_base64)
        try:
            # 使用 UnifiedLLM 的异步接口
            response = await asyncio.to_thread(
                self.llm.chat,
                messages=messages,
                streaming=False
            )
            return response.content
        except Exception as e:
            logger.error(f"UI-TARS 调用失败: {e}")
            raise

    def call_sync(self, instruction: str, image_base64: str) -> str:
        """同步调用 UI-TARS"""
        messages = self._build_messages(instruction, image_base64)
        try:
            response = self.llm.chat(
                messages=messages,
                streaming=False
            )

            return response.content
        except Exception as e:
            logger.error(f"UI-TARS 调用失败: {e}")
            raise

    def stream_async(self, instruction: str, image_base64: str):
        """流式调用 (异步生成器)"""
        messages = self._build_messages(instruction, image_base64)
        # UnifiedLLM 自动处理流式
        return self.llm.stream_chat(messages=messages)

    def _build_messages(self, instruction: str, image_base64: str) -> list:
        """构建 OpenAI 格式消息"""
        return [
            ChatMessage(
                role="system",
                content=self.config.system_prompt
            ),
            ChatMessage(
                role="user",
                content=[
                    {"type": "text", "text": instruction},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        }
                    }
                ]
            )
        ]
