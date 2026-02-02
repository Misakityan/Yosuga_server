# llm_core/llm_core.py

"""
Yosuga Server LLM 核心控制模块
负责整合Prompt管理、模型调用、输出解析、上下文记忆管理以及生命周期维护。
作为系统的"大脑"，对外提供统一的高级交互接口。
"""
import asyncio
import json
import time
from typing import List, Dict, Any, Optional, Callable, Union, Type
from loguru import logger
from pydantic import BaseModel, Field
# 引入已有的模块
from src.modules.text_ai_module.text_ai_core.general_text_ai_req import (
    UnifiedLLM, ModelConfig, ChatMessage, ModelResponse, ModelProvider
)
from src.server_core.llm_core.llm_core_analysis import (
    LLMCoreAnalysisManager, LLMCoreAnalysisBase, YosugaAudioResponseData, YosugaUITARSResponseData, YosugaUITARSRequestData
)
from src.server_core.llm_core.llm_core_dispatcher import LLMCoreActionDispatcher
from src.server_core.llm_core.llm_core_prompt_manager import (
    LLMCorePromptManager, LLMCorePromptBase,
    YosugaAudioASRText, YosugaUITARS, YosugaLive2DControl
)
from src.server_core.llm_core.llm_core_prompts import YOSUGA_SYSTEM_PROMPT_SCH
from src.server_core.llm_core.llm_core_token import TokenManager, TokenUsage

# 类型定义：上下文溢出回调函数签名
# 参数1: 溢出的历史记录列表
# 参数2: 相关的元数据
ContextOverflowCallback = Callable[[List[ChatMessage], Dict[str, Any]], None]

class LLMCoreConfig(BaseModel):
    """LLM Core 运行时配置"""
    max_context_tokens: int = Field(default=2000, description="上下文最大Token数(估算值,不包括System prompt)，超出触发重置")
    enable_history: bool = Field(default=True, description="是否启用历史对话记忆")
    language: str = Field(default="zh_CN", description="回复语言设定")
    role_setting: str = Field(default="", description="llm角色扮演")
    auto_dispatch: bool = Field(default=True, description="是否自动分发到动作处理器")
    dispatch_async: bool = Field(default=False, description="分发是否使用异步模式")
    memory: str = Field(default="", description="llm记忆")
    system_state_table: str = Field(default="", description="Yosuga系统状态表")



class YosugaLLMCore:
    """
    Yosuga 服务端 LLM 核心控制器
    """

    def __init__(self, model_config: ModelConfig, core_config: Optional[LLMCoreConfig] = None):
        """
        初始化 LLM Core

        Args:
            model_config: 底层大模型的连接配置
            core_config: 核心业务逻辑配置（上下文限制等）
        """
        self.model_config = model_config
        self.core_config = core_config or LLMCoreConfig()
        # 初始化模型客户端 (UnifiedLLM)
        self.llm_client: UnifiedLLM = UnifiedLLM(self.model_config)
        # 初始化 TokenManager
        self.token_manager = TokenManager(self.model_config.model_name)
        # 初始化Prompt管理器
        self.prompt_manager = LLMCorePromptManager()
        self._register_default_prompts()
        # 上下文记忆存储
        self._history: List[ChatMessage] = []   # 注意：history不包含system prompt，只包含 user/assistant 消息
        # 上下文溢出回调列表
        self._overflow_callbacks: List[ContextOverflowCallback] = []
        logger.info(
            f"YosugaLLMCore 初始化完成 | "
            f"模型: {model_config.model_name} | "
            f"提供商: {model_config.provider}"
        )
        logger.info(
            f"上下文限制: {self.core_config.max_context_tokens} tokens | "
            f"自动分发: {self.core_config.auto_dispatch}"
        )

    def _register_default_prompts(self):
        """注册默认的业务Prompt模块"""
        self.prompt_manager.register(YosugaAudioASRText())
        self.prompt_manager.register(YosugaUITARS())
        # self.prompt_manager.register(YosugaLive2DControl()) # TODO
        logger.info(f"默认Prompt模块注册完成 | 数量: {self.prompt_manager.get_registry_size()}")

    # 系统提示词管理
    def get_system_prompt(self) -> str:
        """
        动态构建当前的 System Prompt
        根据 prompt_manager 中注册的模块实时生成
        """
        return YOSUGA_SYSTEM_PROMPT_SCH.format(
            InputInfo=self.prompt_manager.describe_input(),     # 不变的内容
            OutputInfo=self.prompt_manager.describe_output(),   # 不变的内容
            RoleSetting=self.core_config.role_setting,          # 角色扮演，可热重载
            Language=self.core_config.language,                 # 回复语言，可热重载
            Memory=self.core_config.memory,                     # 记忆，可热重载，请求前更新
            SystemStateTable=self.core_config.system_state_table# 系统状态表，可热重载，每次请求都会更新
        )

    def register_prompt_module(self, prompt_module: LLMCorePromptBase):
        """运行时注册新的 Prompt 业务模块"""
        self.prompt_manager.register(prompt_module)
        logger.info(f"动态注册 Prompt 模块: {prompt_module.type()}")

    def register_analysis_model(self, model_class: Type[LLMCoreAnalysisBase]) -> None:
        """
        注册LLM输出解析模型

        Args:
            model_class: 继承自 LLMCoreAnalysisBase 的数据模型类
        """
        LLMCoreAnalysisManager.register(model_class)
        logger.info(f"注册解析模型: {model_class.type_()}")

    def register_action_handler(
            self,
            type_id: str,
            handler: Callable,
            is_async: bool = False
    ) -> None:
        """
        注册动作处理器

        Args:
            type_id: 与解析模型对应的类型标识
            handler: 处理函数（同步或异步）
            is_async: 是否为异步处理器
        """
        if is_async:
            LLMCoreActionDispatcher.register_async(type_id, handler)
        else:
            LLMCoreActionDispatcher.register(type_id, handler)

    def set_fallback_handler(self, handler: Callable) -> None:
        """设置未注册类型的回退处理器"""
        LLMCoreActionDispatcher.set_fallback(handler)

    # 核心交互接口
    async def interact(
            self,
            user_input: Union[str, Dict[str, Any]],     # 输入(纯文本或结构化字典)
            past_memories: Optional[str] = "",          # 记忆模块检索的相关历史记忆
            system_state_table: Optional[str] = "",     # 系统状态表，可热重载，每次请求都会更新
            auto_dispatch: Optional[bool] = True,       # 是否自动分发，默认为启用
            dispatch_async: Optional[bool] = True       # 是否异步分发，默认为启用
    ) -> Dict[str, List[Any]]:
        """
        核心交互方法：处理输入 -> 组装上下文 -> 调用LLM -> 解析输出

        Args:
            user_input: 用户输入(纯文本或结构化字典)
            past_memories: 记忆模块检索的相关历史记忆
            system_state_table: Yosuga系统状态表(方便llm理解当前系统状态)
            auto_dispatch: 是否自动分发(覆盖默认配置)
            dispatch_async: 是否异步分发(覆盖默认配置)

        Returns:
            分发执行结果字典:
            {
                "success": [{"type": "...", "output": ..., "index": 0}],
                "failed": [{"type": "...", "error": "...", "index": 1}],
                "skipped": ["unknown_type"]
            }

        Raises:
            ValueError: LLM调用或解析失败
            RuntimeError: 分发执行致命错误
        """
        # 输入预处理
        input_content = (
            json.dumps(user_input, ensure_ascii=False)
            if isinstance(user_input, dict)
            else user_input
        )
        logger.info(f"用户输入内容经过json处理后为: {input_content}")

        # 检查并维护上下文
        self._maintain_context_limit()

        # 构建本次请求的消息链
        messages = self._build_request_messages(input_content, past_memories, system_state_table)

        # 调用 LLM
        try:
            llm_response = self._call_llm(messages)
            if llm_response.usage:      # 打印请求消耗的Token数量
                self.token_manager.record_api_usage(llm_response.usage)
                logger.info(self.token_manager.format_usage_log(source="API"))  # 使用 TokenManager 格式化日志
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            raise

        # 统一解析（总是返回列表）
        try:
            parsed_results = LLMCoreAnalysisManager.parse(llm_response.content)
            logger.success(f"解析成功 | 对象数: {len(parsed_results)}")
        except Exception as e:
            logger.error(f"输出解析失败: {e}")
            raise

        # 更新历史记忆
        if self.core_config.enable_history:
            self._add_to_history("user", input_content)
            self._add_to_history("assistant", llm_response.content)

        # 分发执行
        should_dispatch = auto_dispatch if auto_dispatch is not None else self.core_config.auto_dispatch
        if should_dispatch and parsed_results:
            is_async = dispatch_async if dispatch_async is not None else self.core_config.dispatch_async
            if is_async:
                # 直接 await 异步执行，如果调用 asyncio.run() 就会因为重复创建事件循环导致报错
                logger.debug("使用异步模式分发动作")
                return await LLMCoreActionDispatcher._execute_async(parsed_results)
            else:
                # 同步模式保持原样
                return LLMCoreActionDispatcher.execute(parsed_results, run_async=False)
        # 不分发则返回原始解析结果(极少用)
        return {"success": [{"type": obj.type, "output": obj, "index": i}
                            for i, obj in enumerate(parsed_results)],
                "failed": [], "skipped": []}

    def _build_request_messages(
            self,
            current_input: str,
            memories: str,
            system_state_table: str
    ) -> List[ChatMessage]:
        """
        构建完整的LLM消息链
        结构：
        1. System Prompt 构造，包括记忆注入等信息
        2. 历史上下文
        3. 当前用户输入
        """
        # 构建memory与其他信息
        self.core_config.memory = memories
        # 构建系统状态表
        self.core_config.system_state_table = system_state_table
        # 构造 System Prompt
        messages = [ChatMessage(role="system", content=self.get_system_prompt())]

        # 历史上下文
        if self.core_config.enable_history:
            messages.extend(self._history)  # 分开每条消息追加
        # 当前用户输入
        messages.append(ChatMessage(role="user", content=current_input))
        return messages

    def _call_llm(self, messages: List[ChatMessage]) -> ModelResponse:
        """执行LLM调用（非流式）"""
        logger.debug(f"请求LLM | 消息数: {len(messages)}")
        # 预估token使用情况 TODO: (调试用)
        estimated = self.token_manager.estimate_chat_tokens(
            system_prompt=self.get_system_prompt(),
            history=self._history,
            current_input=messages[-1].content if messages else ""
        )
        logger.debug(self.token_manager.format_usage_log(estimated.to_dict(), source="MANUAL"))

        # 强制非流式(结构化输出需要完整JSON)
        response: ModelResponse = self.llm_client.chat(
            messages,
            streaming=False,
            temperature=self.model_config.temperature
        )
        # 记录 API 返回的 usage
        if response.usage:
            self.token_manager.record_api_usage(response.usage)
        logger.debug(f"LLM响应长度: {len(response.content)}")
        return response

    # 上下文与记忆管理
    def _add_to_history(self, role: str, content: str):
        """添加消息到历史"""
        self._history.append(ChatMessage(role=role, content=content))

    def _maintain_context_limit(self) ->None:
        """
        检查上下文是否超出限制
        如果超出，触发溢出回调，并将当前上下文导出，然后清空最近50%的
        """
        if not self.core_config.enable_history:     # 若未启用历史对话记忆
            return
        # 使用 TokenManager 获取上下文占用(手动计算)
        context_usage = self.token_manager.get_context_usage(self._history)
        current_usage = context_usage.total_tokens

        # 使用 TokenManager 格式化日志
        logger.debug(
            self.token_manager.format_usage_log(context_usage.to_dict(), source="CONTEXT")
        )
        limit = self.core_config.max_context_tokens
        # 使用 TokenManager 判断是否接近限制
        if self.token_manager.is_token_limit_approaching(current_usage, limit, threshold=0.85):
            logger.warning(
                f"上下文接近限制: {current_usage}/{limit} "
                f"({current_usage / limit:.1%})"
            )
        if current_usage <= limit:
            return
        # 否则就是溢出
        logger.critical(
            f"上下文溢出！| {current_usage}/{limit} tokens "
            f"({current_usage / limit:.1%}) | 消息: {len(self._history)}"
        )
        # 执行所有注册的溢出处理器
        self._trigger_overflow_callbacks()

        # 智能清理：保留最近50%消息
        keep_messages = max(1, len(self._history) // 2)
        self._history = self._history[-keep_messages:]
        # 求出新的token占有
        new_usage = self._estimate_token_usage()
        logger.success(     # 打印清理前后的token占用变化
            f"清理完成 | Token: {current_usage}→{new_usage} | "
            f"保留消息: {len(self._history)}"
        )

    def _estimate_token_usage(self) -> int:
        """
        使用 TokenManager 计算当前历史记录的 Token 数
        """
        if not self._history:
            return 0
        # 将 ChatMessage 对象转换为字典格式
        history_dicts = [
            {"role": msg.role, "content": msg.content}
            for msg in self._history
        ]

        return self.token_manager.count_messages_tokens(
            history_dicts,
            tokens_per_message=3  # OpenAI 格式开销
        )

    def register_overflow_handler(self, handler: ContextOverflowCallback):
        """
        注册上下文溢出处理器(支持多个目标)
        这个上下文溢出处理器用于将溢出的消息收集并记录，和记忆模块对接
        """
        self._overflow_callbacks.append(handler)
        logger.info(f"注册溢出处理器: {handler.__name__}")

    def _trigger_overflow_callbacks(self):
        """执行所有注册的溢出处理器"""
        if not self._overflow_callbacks:
            return
        # 使用 TokenManager 获取当前占用
        context_usage = self.token_manager.get_context_usage(self._history)
        metadata = {    # 构造详细的元数据
            "reason": "token_limit_exceeded",
            "message_count": len(self._history),
            "estimated_tokens": context_usage.total_tokens,
            "limit": self.core_config.max_context_tokens,
            "timestamp": time.time(),
            "model": self.model_config.model_name
        }
        # 快照当前历史，防止回调修改
        history_snapshot = list(self._history)

        for handler in self._overflow_callbacks:
            try:
                handler(history_snapshot, metadata)
                logger.debug(f"溢出处理器成功: {handler.__name__}")
            except Exception as e:
                logger.error(f"执行上下文溢出回调失败: {handler.__name__}:{e}")

    def clear_context(self):
        """手动清空上下文"""
        self._history.clear()
        logger.info("上下文记忆已清空")

    # 运行时热重载
    def reload_model(self, new_model_config: ModelConfig):
        """
        热重载 LLM 模型配置
        不影响当前的上下文记忆和 System Prompt
        """
        logger.info(f"正在热重载模型: {self.model_config.model_name} -> {new_model_config.model_name}")
        try:
            self.llm_client.update_config(new_model_config)
            self.model_config = new_model_config
            # 重新初始化 TokenManager
            self.token_manager = TokenManager(new_model_config.model_name)
            logger.info("模型热重载成功")
        except Exception as e:
            logger.error(f"模型热重载失败: {e}")
            raise

    def get_context_stats(self) -> Dict[str, Any]:
        """获取详细上下文统计"""
        # 使用 TokenManager 获取当前占用
        context_usage = self.token_manager.get_context_usage(self._history)
        tokenizer_info = self.token_manager.get_tokenizer_info()
        return {
            "message_count": len(self._history),
            "estimated_tokens": context_usage.total_tokens,
            "limit": self.core_config.max_context_tokens,
            "usage_ratio": context_usage.total_tokens / self.core_config.max_context_tokens,
            "model": self.model_config.model_name,
            "tokenizer": tokenizer_info,
            "history_preview": [
                f"{msg.role[:1]}:{msg.content[:30]}..."
                for msg in self._history[-3:]
            ],
            "last_api_usage": self.token_manager._last_api_usage.to_dict() if self.token_manager._last_api_usage else None
        }

    def __repr__(self) -> str:
        return (    # 返回描述信息
            f"YosugaLLMCore(model={self.model_config.model_name}, "
            f"provider={self.model_config.provider.value}, "
            f"history_len={len(self._history)})"
        )


# 使用示例与测试
if __name__ == "__main__":
    import sys

    # 配置日志输出
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")

    print("\n" + "=" * 50)
    print("🚀 Yosuga Server LLM Core 启动测试")
    print("=" * 50 + "\n")

    # 准备模拟的动作处理器 (Mock Handlers)

    # 异步处理器示例：处理语音回复
    async def handle_audio_response(data: LLMCoreAnalysisBase):
        # 这里强制类型转换为具体子类以获取代码提示（实际运行时已经是具体类型）
        if data.type == "audio_text":
            print(f"    [Audio Handler] 正在合成语音: {data.response_text} | 情感: {data.emotion}")
            return {"audio_file": "sample.wav", "duration": 3.5}
        return None

    # 异步处理器示例：处理自动化操作
    async def handle_auto_agent(data: LLMCoreAnalysisBase):
        print(f"    [UI Agent] 收到指令: {data.Action}")
        await asyncio.sleep(1)  # 模拟耗时操作
        print(f"    [UI Agent] 执行动作: {data.Action} -> ({data.x1}, {data.y1})")
        return {"status": "success", "executed": data.Action}

    async def handle_call_auto_agent(data: LLMCoreAnalysisBase):
        print(f"    [Call Agent] 收到内容: {data.type}")
        print(f"    [Call Agent] 收到内容: {data.llm_translation}")

    # 回退处理器
    def handle_fallback(data: LLMCoreAnalysisBase):
        print(f"    [Fallback] 未知类型数据: {data.type}, 内容: {data.model_dump_json()}")

    # 初始化 LLM Core

    # 配置 LM Studio 连接
    # 注意：LM Studio 通常兼容 OpenAI 格式，所以 provider 选 LM_STUDIO 或 OPENAI 均可
    # 如果是本地服务，API Key 可以随意填写
    model_cfg = ModelConfig(
        provider=ModelProvider.LM_STUDIO,
        model_name="qwen/qwen3-4b-2507",
        base_url="http://192.168.1.3:1234/v1",
        api_key="lm-studio",
        temperature=0.3,
        max_tokens=2048
    )

    core_cfg = LLMCoreConfig(
        max_context_tokens=1024,
        enable_history=True,
        role_setting="你是由Misakiotoha开发的Yosuga助手，性格抽象，爱说点小骚话。",
        auto_dispatch=True,
        dispatch_async=True  # 启用异步分发测试
    )

    core = YosugaLLMCore(model_cfg, core_cfg)

    # 注册处理器
    core.register_action_handler("audio_text", handle_audio_response, is_async=True)
    core.register_action_handler("auto_agent", handle_auto_agent, is_async=True)
    core.register_action_handler("call_auto_agent", handle_call_auto_agent, is_async=True)
    core.set_fallback_handler(handle_fallback)

    # 注册解析器
    core.register_analysis_model(YosugaAudioResponseData)
    core.register_analysis_model(YosugaUITARSResponseData)
    core.register_analysis_model(YosugaUITARSRequestData)

    # 交互测试 Loop
    def run_tests():
        # 测试场景 1: 普通对话 (触发 Audio 解析)
        print("\n📝 测试 1: 普通对话 (预期触发 audio_text)")
        asr_input_1 = {
            "text": "你好，Yosuga！请介绍一下你自己，并对我微笑。",
            "confidence": 0.99
        }
        try:
            result = core.interact(
                asr_input_1,
                dispatch_async=True
            )
            print(f"🏁 交互结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        except Exception as e:
            logger.error(f"测试1失败: {e}")

        # 测试场景 2: 复杂指令 (预期同时触发 Audio 和 UI 操作)
        print("\n📝 测试 2: 混合指令 (预期触发 audio_text + auto_agent)")
        # 构造一个复杂的 Prompt 输入，诱导模型输出多条指令
        # 注意：这依赖于模型足够聪明能理解 System Prompt 中的 output schema
        complex_input = """
            [{
                "text": "打开系统设置",
                "confidence": 0.99
            }]
        """

        try:
            result = core.interact(complex_input, dispatch_async=True)
            print(f"🏁 交互结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        except Exception as e:
            logger.error(f"测试2失败: {e}")

        # 热重载测试
        print("\n🔄 测试 3: 模型热重载")
        new_model_cfg = ModelConfig(
            provider=ModelProvider.LM_STUDIO,
            model_name="qwen/qwen3-vl-8b",
            base_url="http://192.168.1.3:1234/v1",
            api_key="lm-studio",
            temperature=0.5
        )

        try:
            core.reload_model(new_model_cfg)
            print("✅ 热重载完成，进行验证对话...")

            # 验证重载后是否还能对话（保留了上下文）
            verify_input = """
                {
                    "text": "系统设置打开了吗",
                    "confidence": 0.95
                },
                {
                    "auto_agent": "Thought: 我注意到屏幕左下角有一个齿轮形状的图标，这正是系统的设置入口。在KDE系统中，这个图标通常用来访问系统设置面板。为了帮助用户打开设置界面，我现在需要点击这个位于屏幕左下方的齿轮图标。
                    Action: click(start_box='<|box_start|>(42,1045)<|box_end|>')"
                }
            }"""
            result = core.interact(verify_input)
            print(f"🏁 重载后回复: {json.dumps(result, ensure_ascii=False, indent=2)}")

        except Exception as e:
            logger.error(f"热重载测试失败: {e}")

        # 查看统计信息
        print("\n📊 最终状态统计:")
        print(core.get_context_stats())

    # 运行测试
    run_tests()