"""
通用大语言模型调用框架
支持本地模型(Ollama, LM Studio, llama.cpp)和云端模型(OpenAI, Anthropic, Google, Azure等)
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union, Any, Iterator
import json
import os
from loguru import logger
from dataclasses import dataclass, asdict, field
from enum import Enum
import httpx
from pydantic import BaseModel, Field

class ModelProvider(Enum):
    """支持的模型提供商枚举"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    LLAMA_CPP = "llama_cpp"
    CUSTOM = "custom"


@dataclass
class ModelConfig:
    """模型配置类"""
    provider: ModelProvider
    model_name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_version: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    timeout: int = 30
    streaming: bool = False
    custom_headers: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)


@dataclass
class ChatMessage:
    """聊天消息类"""
    role: str  # system, user, assistant
    content: str
    name: Optional[str] = None

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "role": self.role,
            "content": self.content,
            **({"name": self.name} if self.name else {})
        }


@dataclass
class ModelResponse:
    """模型响应类"""
    content: str            # 响应内容
    model: str              # 模型名称
    usage: Optional[Dict[str, int]] = None  # 使用量
    finish_reason: Optional[str] = None     # 结束原因
    raw_response: Optional[Dict] = None     # 原始响应


def normalize_usage(raw_usage: Optional[Dict[str, Any]], provider: ModelProvider) -> Optional[Dict[str, int]]:
    """
    将不同平台的 usage 字段统一归一化为 OpenAI 标准格式

    Args:
        raw_usage: API 原始返回的 usage 数据
        provider: 模型提供商枚举

    Returns:
        归一化后的 usage 字典，格式：
        {
            "prompt_tokens": int,
            "completion_tokens": int,
            "total_tokens": int
        }
        如果无法归一化则返回 None
    """
    if not raw_usage:
        return None

    # 字段映射表：{provider: (input_key, output_key, total_key)}
    USAGE_FIELD_MAP = {
        ModelProvider.OPENAI: ("prompt_tokens", "completion_tokens", "total_tokens"),
        ModelProvider.AZURE: ("prompt_tokens", "completion_tokens", "total_tokens"),
        ModelProvider.LM_STUDIO: ("prompt_tokens", "completion_tokens", "total_tokens"),
        ModelProvider.LLAMA_CPP: ("prompt_tokens", "completion_tokens", "total_tokens"),
        ModelProvider.OLLAMA: ("prompt_eval_count", "eval_count", None),  # Ollama 没有 total
        ModelProvider.ANTHROPIC: ("input_tokens", "output_tokens", None),
        ModelProvider.GOOGLE: ("promptTokenCount", "candidatesTokenCount", "totalTokenCount"),
    }

    input_key, output_key, total_key = USAGE_FIELD_MAP.get(provider, (None, None, None))

    if input_key is None:
        logger.warning(f"未知的 provider '{provider}'，无法归一化 usage")
        return None

    try:
        # 提取字段值
        prompt_tokens = raw_usage.get(input_key, 0)
        completion_tokens = raw_usage.get(output_key, 0)

        # 处理嵌套字典（如有些 API 的 usage 格式特殊）
        if isinstance(prompt_tokens, dict):
            prompt_tokens = prompt_tokens.get("value", 0)
        if isinstance(completion_tokens, dict):
            completion_tokens = completion_tokens.get("value", 0)

        # 转换为整数
        prompt_tokens = int(prompt_tokens) if prompt_tokens else 0
        completion_tokens = int(completion_tokens) if completion_tokens else 0

        # 计算 total（如果 API 没提供）
        if total_key and total_key in raw_usage:
            total_tokens = int(raw_usage[total_key])
        else:
            total_tokens = prompt_tokens + completion_tokens

        normalized = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens
        }

        logger.debug(f"归一化 usage | {provider} -> OpenAI格式: {normalized}")
        return normalized

    except Exception as e:
        logger.error(f"归一化 usage 失败: {e} | raw_usage: {raw_usage}")
        return None

class BaseLLMClient(ABC):
    """大语言模型客户端基类"""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = None
        self._initialize_client()

    @abstractmethod
    def _initialize_client(self):
        """初始化客户端"""
        pass

    @abstractmethod
    def chat_completion(
            self,
            messages: List[Union[ChatMessage, Dict]],
            **kwargs
    ) -> Union[ModelResponse, Iterator[ModelResponse]]:
        """聊天补全"""
        pass

    @abstractmethod
    def completion(
            self,
            prompt: str,
            **kwargs
    ) -> Union[ModelResponse, Iterator[ModelResponse]]:
        """文本补全"""
        pass

    def format_messages(self, messages: List[Union[ChatMessage, Dict]]) -> List[Dict]:
        """格式化消息列表"""
        formatted = []
        for msg in messages:
            if isinstance(msg, ChatMessage):
                formatted.append(msg.to_dict())
            else:
                formatted.append(msg)
        return formatted


class OpenAIClient(BaseLLMClient):
    """OpenAI客户端"""

    def _initialize_client(self):
        try:
            from openai import OpenAI

            api_key = self.config.api_key
            if not api_key:
                raise ValueError("OpenAI API密钥未设置")

            self.client = OpenAI(
                api_key=api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout
            )
            logger.info(f"OpenAI客户端初始化成功，base_url: {self.config.base_url}")
        except ImportError:
            logger.error("请安装openai包: pip install openai")
            raise

    def chat_completion(self, messages, **kwargs):
        formatted_messages = self.format_messages(messages)

        # 获取streaming参数，优先使用kwargs中的设置
        streaming = kwargs.get("streaming", self.config.streaming)

        # 合并配置
        params = {
            "model": self.config.model_name,
            "messages": formatted_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "frequency_penalty": kwargs.get("frequency_penalty", self.config.frequency_penalty),
            "presence_penalty": kwargs.get("presence_penalty", self.config.presence_penalty),
            "stream": streaming,  # 使用正确的streaming设置
        }

        logger.info(f"🔧 调用参数: streaming={streaming}")

        if streaming:
            return self._stream_chat_completion(params)
        else:
            return self._normal_chat_completion(params)

    def _normal_chat_completion(self, params):
        """非流式响应处理"""
        logger.info("📡 发送非流式请求...")
        response = self.client.chat.completions.create(**params)
        raw_usage = response.usage
        normalized_usage = normalize_usage(
            raw_usage.model_dump() if hasattr(raw_usage, 'model_dump') else raw_usage,
            ModelProvider.OPENAI
        )
        return ModelResponse(
            content=response.choices[0].message.content,
            model=response.model,
            usage=normalized_usage,
            finish_reason=response.choices[0].finish_reason,
            raw_response=response.model_dump() if hasattr(response, 'model_dump') else response.dict()
        )

    def _stream_chat_completion(self, params):
        """流式响应处理"""
        logger.info("📡 发送流式请求...")
        response_stream = self.client.chat.completions.create(**params)

        full_content = ""
        for chunk in response_stream:
            if chunk.choices[0].delta.content is not None:
                content_chunk = chunk.choices[0].delta.content
                full_content += content_chunk
                yield ModelResponse(
                    content=content_chunk,
                    model=chunk.model,
                    raw_response=chunk.model_dump() if hasattr(chunk, 'model_dump') else chunk.dict()
                )

    def completion(self, prompt, **kwargs):
        # OpenAI 推荐使用 chat_completion，这里保持兼容
        messages = [{"role": "user", "content": prompt}]
        return self.chat_completion(messages, **kwargs)


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude客户端"""

    def _initialize_client(self):
        try:
            from anthropic import Anthropic
            self.client = Anthropic(
                api_key=self.config.api_key or os.getenv("ANTHROPIC_API_KEY"),
                timeout=self.config.timeout
            )
        except ImportError:
            logger.error("请安装anthropic包: pip install anthropic")
            raise

    def chat_completion(self, messages, **kwargs):
        formatted_messages = self.format_messages(messages)

        # Claude 的消息格式转换
        claude_messages = []
        system_message = None

        for msg in formatted_messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                claude_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
                # 明确获取streaming参数

        params = {
            "model": self.config.model_name,
            "messages": claude_messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "stream": kwargs.get("streaming", self.config.streaming),
        }

        if system_message:
            params["system"] = system_message

        if self.config.streaming:
            return self._stream_chat_completion(params)
        else:
            return self._normal_chat_completion(params)

    def _normal_chat_completion(self, params):
        response = self.client.messages.create(**params)
        # Anthropic 返回的usage格式和OpenAI不同，需要进行转换
        raw_usage = response.usage
        normalized_usage = normalize_usage(
            raw_usage.model_dump() if hasattr(raw_usage, 'model_dump') else raw_usage,
            ModelProvider.ANTHROPIC
        )
        return ModelResponse(
            content=response.content[0].text,
            model=response.model,
            usage=normalized_usage,
            finish_reason=response.stop_reason,
            raw_response=response.model_dump() if hasattr(response, 'model_dump') else response.dict()
        )

    def _stream_chat_completion(self, params):
        with self.client.messages.stream(**params) as stream:
            for chunk in stream:
                if chunk.type_ == "content_block_delta":
                    yield ModelResponse(
                        content=chunk.delta.text,
                        model=params["model"],
                        raw_response=chunk.model_dump() if hasattr(chunk, 'model_dump') else chunk.dict()
                    )

    def completion(self, prompt, **kwargs):
        messages = [{"role": "user", "content": prompt}]
        return self.chat_completion(messages, **kwargs)


class OllamaClient(BaseLLMClient):
    """Ollama本地模型客户端"""

    def _initialize_client(self):
        import httpx
        self.base_url = self.config.base_url or "http://localhost:11434"
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=self.config.timeout
        )

    def chat_completion(self, messages, **kwargs):
        formatted_messages = self.format_messages(messages)

        payload = {
            "model": self.config.model_name,
            "messages": formatted_messages,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "top_p": kwargs.get("top_p", self.config.top_p),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            },
            "stream": kwargs.get("streaming", self.config.streaming),
        }

        if self.config.streaming:
            return self._stream_chat_completion(payload)
        else:
            return self._normal_chat_completion(payload)

    def _normal_chat_completion(self, payload):
        response = self.client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        normalized_usage = normalize_usage(data, ModelProvider.OLLAMA)
        return ModelResponse(
            content=data["message"]["content"],
            model=data["model"],
            usage=normalized_usage,
            finish_reason=data.get("done_reason"),
            raw_response=data
        )

    def _stream_chat_completion(self, payload):
        with self.client.stream("POST", "/api/chat", json=payload) as response:
            for line in response.iter_lines():
                if line.strip():
                    try:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield ModelResponse(
                                content=data["message"]["content"],
                                model=data.get("model", self.config.model_name),
                                raw_response=data
                            )
                    except json.JSONDecodeError:
                        continue

    def completion(self, prompt, **kwargs):
        payload = {
            "model": self.config.model_name,
            "prompt": prompt,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "top_p": kwargs.get("top_p", self.config.top_p),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            },
            "stream": kwargs.get("streaming", self.config.streaming),
        }

        if self.config.streaming:
            return self._stream_completion(payload)
        else:
            return self._normal_completion(payload)

    def _normal_completion(self, payload):
        response = self.client.post("/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()

        return ModelResponse(
            content=data["response"],
            model=data["model"],
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
            },
            finish_reason=data.get("done_reason"),
            raw_response=data
        )

    def _stream_completion(self, payload):
        with self.client.stream("POST", "/api/generate", json=payload) as response:
            for line in response.iter_lines():
                if line.strip():
                    try:
                        data = json.loads(line)
                        if "response" in data:
                            yield ModelResponse(
                                content=data["response"],
                                model=data.get("model", self.config.model_name),
                                raw_response=data
                            )
                    except json.JSONDecodeError:
                        continue


class GenericLLMClient(BaseLLMClient):
    """通用HTTP客户端，支持LM Studio和其他兼容OpenAI API的本地模型"""

    def _initialize_client(self):
        import httpx
        self.base_url = self.config.base_url or "http://localhost:1234/v1"
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=self.config.timeout,
            headers=self.config.custom_headers
        )

    def chat_completion(self, messages, **kwargs):
        formatted_messages = self.format_messages(messages)

        # 明确获取 streaming 参数
        streaming = kwargs.get("streaming", self.config.streaming)

        payload = {
            "model": self.config.model_name,
            "messages": formatted_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "stream": streaming,  # 使用明确的 streaming 变量
        }

        logger.info(f"GenericLLMClient 参数: streaming={streaming}")

        if streaming:
            return self._stream_chat_completion(payload)
        else:
            return self._normal_chat_completion(payload)

    def _normal_chat_completion(self, payload):
        logger.info(f"GenericLLMClient 发送非流式请求到: {self.base_url}")
        response = self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        logger.info(f"GenericLLMClient 收到响应，模型: {data.get('model')}")

        return ModelResponse(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            usage=data.get("usage"),
            finish_reason=data["choices"][0].get("finish_reason"),
            raw_response=data
        )

    def _stream_chat_completion(self, payload):
        logger.info(f"GenericLLMClient 发送流式请求到: {self.base_url}")
        with self.client.stream("POST", "/chat/completions", json=payload) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                        if data["choices"][0]["delta"].get("content"):
                            yield ModelResponse(
                                content=data["choices"][0]["delta"]["content"],
                                model=data["model"],
                                raw_response=data
                            )
                    except json.JSONDecodeError:
                        continue

    def completion(self, prompt, **kwargs):
        payload = {
            "model": self.config.model_name,
            "prompt": prompt,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "stream": kwargs.get("streaming", self.config.streaming),
        }

        streaming = kwargs.get("streaming", self.config.streaming)

        if streaming:
            return self._stream_completion(payload)
        else:
            return self._normal_completion(payload)

    def _normal_completion(self, payload):
        response = self.client.post("/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        return ModelResponse(
            content=data["choices"][0]["text"],
            model=data["model"],
            usage=data.get("usage"),
            finish_reason=data["choices"][0].get("finish_reason"),
            raw_response=data
        )

    def _stream_completion(self, payload):
        with self.client.stream("POST", "/completions", json=payload) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                        if data["choices"][0].get("text"):
                            yield ModelResponse(
                                content=data["choices"][0]["text"],
                                model=data["model"],
                                raw_response=data
                            )
                    except json.JSONDecodeError:
                        continue

class UnifiedLLM:
    """
    统一的大语言模型调用类

    支持多种模型提供商：
    - 云端模型：OpenAI, Anthropic, Google, Azure
    - 本地模型：Ollama, LM Studio, llama.cpp

    使用示例：
    ```python
    # 初始化OpenAI客户端
    config = ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="gpt-4",
        api_key="your-api-key"
    )
    llm = UnifiedLLM(config)

    # 聊天补全
    messages = [
        {"role": "system", "content": "你是一个有用的助手"},
        {"role": "user", "content": "你好！"}
    ]
    response = llm.chat(messages)
    print(response.content)

    # 流式响应
    config.streaming = True
    llm.update_config(config)
    for chunk in llm.chat(messages):
        print(chunk.content, end="", flush=True)
    ```
    """

    def __init__(self, config: ModelConfig):
        """
        初始化统一LLM

        Args:
            config: 模型配置
        """
        self.config = config
        self.client = self._create_client()
        logger.info(f"   UnifiedLLM 初始化完成")
        logger.info(f"   提供商: {config.provider}")
        logger.info(f"   模型: {config.model_name}")
        logger.info(f"   流式默认: {config.streaming}")

    def _create_client(self) -> BaseLLMClient:
        """根据配置创建客户端"""
        provider = self.config.provider

        if provider == ModelProvider.OPENAI:
            return OpenAIClient(self.config)
        elif provider == ModelProvider.ANTHROPIC:
            return AnthropicClient(self.config)
        elif provider == ModelProvider.OLLAMA:
            return OllamaClient(self.config)
        elif provider in [ModelProvider.LM_STUDIO, ModelProvider.LLAMA_CPP, ModelProvider.CUSTOM]:
            return GenericLLMClient(self.config)
        elif provider == ModelProvider.GOOGLE:
            # 这里可以扩展Google Gemini支持
            return GenericLLMClient(self.config)
        elif provider == ModelProvider.AZURE:
            # Azure OpenAI需要特殊处理
            return GenericLLMClient(self.config)
        else:
            raise ValueError(f"不支持的模型提供商: {provider}")

    def update_config(self, config: ModelConfig):
        """更新配置并重新创建客户端"""
        self.config = config
        self.client = self._create_client()
        logger.info(f"UnifiedLLM 配置已更新")

    def chat(self, messages: List[Union[ChatMessage, Dict]], **kwargs) -> Union[ModelResponse, Iterator[ModelResponse]]:
        """
        聊天补全

        Args:
            messages: 消息列表
            **kwargs: 其他参数，会覆盖config中的设置

        Returns:
            ModelResponse 或 ModelResponse 的迭代器（流式模式）
        """
        # 明确获取streaming参数
        streaming = kwargs.get("streaming", self.config.streaming)
        logger.info(f"   UnifiedLLM.chat() 调用")
        logger.info(f"   消息数: {len(messages)}")
        logger.info(f"   streaming参数: {streaming}")

        # 调用客户端
        result = self.client.chat_completion(messages, **kwargs)

        # 类型检查（调试用）
        if streaming:
            if not hasattr(result, '__iter__'):
                logger.warning(f"警告: streaming=True 但返回的不是迭代器")
        else:
            if hasattr(result, '__iter__'):
                logger.warning(f"警告: streaming=False 但返回的是迭代器")
            elif not isinstance(result, ModelResponse):
                logger.warning(f"警告: streaming=False 但返回的不是ModelResponse")

        return result

    def complete(self, prompt: str, **kwargs) -> Union[ModelResponse, Iterator[ModelResponse]]:
        """
        文本补全

        Args:
            prompt: 提示文本
            **kwargs: 其他参数

        Returns:
            ModelResponse 或 ModelResponse 的迭代器（流式模式）
        """
        streaming = kwargs.get("streaming", self.config.streaming)
        logger.info(f"   UnifiedLLM.complete() 调用")
        logger.info(f"   prompt长度: {len(prompt)}")
        logger.info(f"   streaming参数: {streaming}")

        return self.client.completion(prompt, **kwargs)

    def stream_chat(self, messages: List[Union[ChatMessage, Dict]], **kwargs) -> Iterator[ModelResponse]:
        """
        流式聊天补全（便捷方法）

        Args:
            messages: 消息列表
            **kwargs: 其他参数

        Returns:
            ModelResponse 的迭代器
        """
        kwargs["streaming"] = True
        logger.info(f"UnifiedLLM.stream_chat() 调用")

        result = self.chat(messages, **kwargs)

        # 确保返回的是迭代器
        if not hasattr(result, '__iter__'):
            raise TypeError("stream_chat 应该返回迭代器，但返回了其他类型")

        return result

    def stream_complete(self, prompt: str, **kwargs) -> Iterator[ModelResponse]:
        """
        流式文本补全（便捷方法）

        Args:
            prompt: 提示文本
            **kwargs: 其他参数

        Returns:
            ModelResponse 的迭代器
        """
        kwargs["streaming"] = True
        logger.info(f"UnifiedLLM.stream_complete() 调用")

        result = self.complete(prompt, **kwargs)

        # 确保返回的是迭代器
        if not hasattr(result, '__iter__'):
            raise TypeError("stream_complete 应该返回迭代器，但返回了其他类型")

        return result


# 快捷函数
def create_llm_client(
        provider: Union[str, ModelProvider],
        model_name: str,
        **kwargs
) -> UnifiedLLM:
    """
    快捷创建LLM客户端

    Args:
        provider: 提供商名称或枚举
        model_name: 模型名称
        **kwargs: 其他配置参数

    Returns:
        UnifiedLLM 实例
    """
    if isinstance(provider, str):
        provider = ModelProvider(provider.lower())

    config = ModelConfig(
        provider=provider,
        model_name=model_name,
        **kwargs
    )

    return UnifiedLLM(config)


# 使用示例
def example_usage():
    """使用示例"""

    # 示例1: 使用OpenAI
    print("示例1: 使用OpenAI")
    openai_config = ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="gpt-3.5-turbo",
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0.8
    )

    try:
        openai_llm = UnifiedLLM(openai_config)
        messages = [
            ChatMessage(role="system", content="你是一个有用的助手"),
            ChatMessage(role="user", content="请用Python写一个Hello World程序")
        ]
        response = openai_llm.chat(messages)
        print(f"响应: {response.content[:100]}...")
    except Exception as e:
        print(f"OpenAI示例错误: {e}")

    # 示例2: 使用Ollama（本地模型）
    print("\n示例2: 使用Ollama（本地模型）")
    ollama_config = ModelConfig(
        provider=ModelProvider.OLLAMA,
        model_name="llama2",
        base_url="http://localhost:11434",
        temperature=0.7,
        streaming=True  # 流式响应
    )

    try:
        ollama_llm = UnifiedLLM(ollama_config)
        messages = [
            {"role": "user", "content": "什么是人工智能？"}
        ]

        print("流式响应:")
        for chunk in ollama_llm.stream_chat(messages):
            print(chunk.content, end="", flush=True)
        print()
    except Exception as e:
        print(f"Ollama示例错误: {e}（请确保Ollama服务正在运行）")

    # 示例3: 使用快捷函数
    print("\n示例3: 使用快捷函数")
    try:
        llm = create_llm_client(
            provider="openai",
            model_name="gpt-3.5-turbo",
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.5
        )

        response = llm.complete("天空为什么是蓝色的？")
        print(f"响应: {response.content[:100]}...")
    except Exception as e:
        print(f"快捷函数示例错误: {e}")