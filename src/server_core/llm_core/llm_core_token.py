# llm_core/llm_core_token.py

"""
Token 计算与管理模块
支持双数据源智能切换：
- 优先使用大模型 API 返回的精确 usage 数据
- 当 API 不返回时，自动回退到 tiktoken 手动估算
"""
import time
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
import tiktoken
from loguru import logger

@dataclass
class TokenUsage:
    """Token 使用量统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    source: str = field(default="manual", repr=True)  # "api" | "manual"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "source": self.source
        }


@dataclass
class TokenizerInfo:
    """Tokenizer 元数据"""
    model_name: str
    encoding_name: str
    is_fallback: bool
    estimated_accuracy: str  # "high" | "medium" | "low"


class TokenManager:
    """
    Token 管理核心类
    智能数据源切换：API返回 > 手动估算
    """
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.tokenizer = self._get_tokenizer(model_name)
        # 存储最近一次 API 返回的 usage
        self._last_api_usage: Optional[TokenUsage] = None
        # API 数据有效期（秒），超过此时间则视为过期，回退到手动计算
        self._api_usage_expiry: float = 30.0
        # 记录 API usage 的获取时间
        self._last_api_usage_time: float = 0.0

        logger.info(
            f"TokenManager 初始化完成 | "
            f"模型: {model_name} | "
            f"编码器: {self.tokenizer.name}"
        )

    def _get_tokenizer(self, model_name: str) -> tiktoken.Encoding:
        """获取 tokenizer"""
        model_tokenizer_map = {
            "qwen": "gpt-3.5-turbo",
            "llama": "gpt-3.5-turbo",
            "gemma": "gpt-3.5-turbo",
        }

        try:
            return tiktoken.encoding_for_model(model_name)
        except KeyError:
            pass

        for prefix, mapped_model in model_tokenizer_map.items():
            if prefix in model_name.lower():
                logger.info(
                    f"模型 '{model_name}' 映射到 tokenizer '{mapped_model}'"
                )
                return tiktoken.encoding_for_model(mapped_model)

        logger.warning(
            f"tiktoken 不支持模型 '{model_name}'，"
            f"降级使用 'cl100k_base' 编码器"
        )
        return tiktoken.get_encoding("cl100k_base")

    def record_api_usage(self, usage: Optional[Union[Dict[str, int], TokenUsage]]) -> None:
        """
        记录大模型 API 返回的 usage 数据

        Args:
            usage: API 返回的 usage 数据（dict 或 TokenUsage 对象）
                  如果为 None 或空，则忽略
        """
        if not usage:
            logger.debug("API usage 为空，未记录")
            return

        # 在底层已经统一好了不同大模型对于usage的处理
        if isinstance(usage, TokenUsage):
            api_usage = usage
            api_usage.source = "api"
        else:
            api_usage = TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                source="api"
            )

        self._last_api_usage = api_usage
        self._last_api_usage_time = time.time()

        logger.debug(
            f"记录 API usage | "
            f"Prompt: {api_usage.prompt_tokens} | "
            f"Completion: {api_usage.completion_tokens} | "
            f"Total: {api_usage.total_tokens}"
        )

    def get_current_usage(self, prefer_api: bool = True) -> TokenUsage:
        """
        获取当前 Token 使用情况（智能数据源切换）

        Args:
            prefer_api: 是否优先使用 API 数据（默认 True）

        Returns:
            TokenUsage 对象，包含数据来源标记

        Notes:
            - 如果 prefer_api=True 且 API 数据在有效期内，直接返回 API 数据
            - 否则回退到手动估算
        """
        current_time = time.time()

        # 检查 API 数据是否有效
        if prefer_api and self._last_api_usage:
            time_elapsed = current_time - self._last_api_usage_time
            if time_elapsed <= self._api_usage_expiry:
                logger.debug(
                    f"使用 API Token 数据（{time_elapsed:.1f}s 内）| "
                    f"{self._last_api_usage.prompt_tokens} + "
                    f"{self._last_api_usage.completion_tokens} = "
                    f"{self._last_api_usage.total_tokens}"
                )
                return self._last_api_usage

        # API 数据无效或无数据，回退到手动估算
        logger.debug("API usage 无效/过期，回退到手动估算")
        return self._estimate_manual_usage()

    def _estimate_manual_usage(self) -> TokenUsage:
        """内部方法：创建空的手动 usage（占位符）"""
        return TokenUsage(source="manual")

    def get_context_usage(self, history: List[Any]) -> TokenUsage:
        """
        计算对话上下文的 Token 占用（必须手动计算）

        注意：
        - 上下文占用无法从 API 获得，必须手动估算
        - 此方法不涉及 _last_api_usage

        Args:
            history: 历史消息列表

        Returns:
            TokenUsage 对象，source 始终为 "manual"
        """
        tokens = self.count_messages_tokens(history)
        return TokenUsage(
            prompt_tokens=tokens,
            completion_tokens=0,
            total_tokens=tokens,
            source="manual"
        )

    def count_text_tokens(self, text: str) -> int:
        """计算单段文本的 token 数量"""
        if not isinstance(text, str) or not text:
            return 0
        return len(self.tokenizer.encode(text))

    def count_messages_tokens(
            self,
            messages: List[Any],
            tokens_per_message: int = 3
    ) -> int:
        """计算消息列表的总 token 数量"""
        if not messages:
            return 0

        num_tokens = 0
        for msg in messages:
            # 统一转换为字典
            if hasattr(msg, "to_dict"):
                msg_dict = msg.to_dict()
            elif hasattr(msg, "model_dump"):
                msg_dict = msg.model_dump()
            else:
                msg_dict = msg

            # 计算内容和 role 的 token
            num_tokens += self.count_text_tokens(msg_dict.get("content", ""))
            num_tokens += self.count_text_tokens(msg_dict.get("role", ""))
            num_tokens += tokens_per_message

        # 加上回复前缀的开销
        num_tokens += 3
        return num_tokens

    def estimate_chat_tokens(
            self,
            system_prompt: Optional[str],
            history: List[Any],
            current_input: str
    ) -> TokenUsage:
        """
        估算一次完整对话所需的 token 数量

        Args:
            system_prompt: 系统提示词
            history: 历史消息列表
            current_input: 当前用户输入

        Returns:
            TokenUsage 对象，source 始终为 "manual"

        Notes:
            - 这是预估，不是实际 API 返回值
            - 用于调试和前置检查
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.extend(history)
        messages.append({"role": "user", "content": current_input})

        total = self.count_messages_tokens(messages)

        return TokenUsage(
            prompt_tokens=total,
            completion_tokens=0,
            total_tokens=total,
            source="manual"
        )

    def format_usage_log(
            self,
            usage: Optional[Union[Dict[str, int], TokenUsage]] = None,
            source: str = "AUTO"
    ) -> str:
        """
        格式化 token 使用日志

        Args:
            usage: usage 数据（可选）。如果为 None，自动获取当前 usage
            source: 数据来源标记（"AUTO" | "API" | "MANUAL" | "CONTEXT"）

        Returns:
            格式化的日志字符串
        """
        # 如果未提供 usage，自动获取
        if usage is None:
            if source == "CONTEXT":
                # 上下文场景必须手动计算
                usage_obj = self.get_context_usage([])
            else:
                # 自动选择最佳数据源
                usage_obj = self.get_current_usage(prefer_api=True)
        else:
            # 使用提供的 usage
            if isinstance(usage, TokenUsage):
                usage_obj = usage
            else:
                usage_obj = TokenUsage(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    source="api" if source == "API" else "manual"
                )

        # 根据来源选择前缀和图标
        prefix_map = {
            "API": "API Token统计",
            "MANUAL": "手动估算",
            "CONTEXT": "上下文占用",
            "AUTO": "Token统计"
        }
        prefix = prefix_map.get(source, "Token统计")

        # 添加数据来源标记
        source_icon = "⚡" if usage_obj.source == "api" else "🧮"

        # 格式化输出
        if usage_obj.completion_tokens > 0:
            return (
                f"{prefix} {source_icon} | "
                f"Prompt: {usage_obj.prompt_tokens} | "
                f"Completion: {usage_obj.completion_tokens} | "
                f"Total: {usage_obj.total_tokens}"
            )
        else:
            return (
                f"{prefix} {source_icon} | "
                f"Total: {usage_obj.total_tokens}"
            )

    def get_tokenizer_info(self) -> TokenizerInfo:
        """获取当前 tokenizer 的详细信息"""
        if "cl100k_base" in self.tokenizer.name and "gpt-3.5" not in self.model_name:
            accuracy = "low"
        elif self.model_name in self.tokenizer.name:
            accuracy = "high"
        else:
            accuracy = "medium"

        return TokenizerInfo(
            model_name=self.model_name,
            encoding_name=self.tokenizer.name,
            is_fallback="cl100k_base" in self.tokenizer.name,
            estimated_accuracy=accuracy
        )

    def is_token_limit_approaching(
            self,
            current_tokens: int,
            limit: int,
            threshold: float = 0.85
    ) -> bool:
        """判断 token 使用量是否接近限制"""
        return current_tokens > limit * threshold

    def calculate_chunk_size(
            self,
            available_tokens: int,
            safety_margin: float = 0.1
    ) -> int:
        """计算安全的消息块大小"""
        return int(available_tokens * (1 - safety_margin))

    def clear_api_usage_cache(self):
        """清空 API usage 缓存（用于测试）"""
        self._last_api_usage = None
        self._last_api_usage_time = 0.0
        logger.debug("API usage 缓存已清空")


# 单例工厂
class TokenManagerFactory:
    """TokenManager 工厂类，支持缓存复用"""
    _instances: Dict[str, TokenManager] = {}

    @classmethod
    def get_manager(cls, model_name: str) -> TokenManager:
        if model_name not in cls._instances:
            cls._instances[model_name] = TokenManager(model_name)
        return cls._instances[model_name]

    @classmethod
    def clear_cache(cls):
        cls._instances.clear()
        logger.info("TokenManager 缓存已清空")