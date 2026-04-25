# server_core/core.py

"""
统一业务，对外提供启动接口
业务数据流向：
      Yosuga[User Audio Info Struct]        ->(WebSocket)   Yosuga_server[asr_module]   ->  Text
      Yosuga_server[Come from Yosuga Audio ASR Text]  ->(Func call)   Yosuga_server[llm_core]   ->  Ins and Text

      Yosuga_server[Come from llm_core Text]->(WebSocket)   Yosuga
      Yosuga_server[Come from llm_core Text]->(Func call)   Yosuga_server[TTS]         ->  Audio Data
      Yosuga_server[Audio Data]             ->(WebSocket)   Yosuga

      Yosuga_embedded[Devices Control Info] ->(WebSocket)   Yosuga_server[embedded_core]->  Ins
      Yosuga_embedded[Devices Control Info] ->(Serial)      Yosuga[SerialManager]       ->  ForWord To Yosuga_server
      Yosuga[Come from embedded Info]       ->(WebSocket)   Yosuga_server[llm_core]     ->  Ins

      UI_TARS[Mind and x&y Info]            ->(Func call)   Yosuga_server[llm_core]     ->  Ins
      Yosuga_server[Come from UI_TARS Ins]  ->(WebSocket)   Yosuga

      Yosuga[Live2D Control Info]           ->(WebSocket)   Yosuga_server[llm_core]     ->  Ins
      Yosuga_server[Live2D Control Ins]     ->(Websocket)   Yosuga

      Yosuga_server[agent memory]           ->(Func call)   Yosuga_server[Memory Uint]
"""
import asyncio
from typing import Optional, List, Dict, Any
from loguru import logger
import json
from src.modules.websocket_base_module.dto.third_dtos import (
    AudioDataDTO, AudioDataTransferObject,
    ScreenShotDataDTO, ScreenShotDataTransferObject
)
from src.modules.websocket_base_module.dto.second_dtos import JsonDTO, get_json_dto_instance
from src.modules.websocket_base_module.websocket_core.core_ws_server import WebSocketServer, get_ws_server

from src.modules.device_control_module.device_control_core.ui_tars_.ui_tars_client import UITarsClient, UITarsClientConfig

from src.modules.asr_module.client.asr_client import create_asr_client, ASRClientConfig, ASRClientAsync

from src.modules.tts_module.tts_core.gpt_sovits.gpt_sovits_client import StreamingMode, TTSConfig, GPTSoVITSClient

from src.server_core.llm_core.llm_core import (
    LLMCoreConfig, ModelConfig,
    YosugaLLMCore, ModelProvider,
    LLMCoreAnalysisBase,
    YosugaAudioResponseData, YosugaUITARSResponseData,
    YosugaUITARSRequestData, YosugaEmbeddedResponseData
)

from src.server_core.yosuga_embedded_server import (
    YosugaServer, ServerConfig
)
from src.server_core.yosuga_embedded_server.device_dto import DeviceDataDTO
from src.server_core.llm_core.llm_core_prompt_manager import YosugaEmbedded

from src.modules.websocket_base_module.dto.dto_templates.auto_agent_data_dto import AutoAgentDataTransferObject
from src.config.config import cfg


class YosugaServerCore:
    """
    异步单例类
    """

    _instance: Optional["YosugaServerCore"] = None
    _lock = asyncio.Lock()

    # 组合必要的工具类
    ws_server: WebSocketServer
    json_dto: JsonDTO
    audio_dto: AudioDataDTO
    screenshot_dto: ScreenShotDataDTO

    asr_client: ASRClientAsync          # 异步asr client
    tts_client: GPTSoVITSClient         # tts client
    auto_agent_client: UITarsClient     # GUI自动化agent

    llm_core: YosugaLLMCore = None      # llm core

    embedded_server: YosugaServer       # 嵌入式设备管理框架
    device_dto: DeviceDataDTO           # 设备数据分发器

    # @classmethod
    # async def get_instance(cls) -> "YosugaServerCore":
    #     """异步单例工厂"""
    #     if cls._instance is None:
    #         async with cls._lock:
    #             if cls._instance is None:
    #                 logger.info("Initializing YosugaServerCore...")
    #                 # 创建实例
    #                 instance = cls.__new__(cls)
    #
    #                 # 按依赖顺序初始化数据分发器
    #                 instance.ws_server = await get_ws_server()
    #                 instance.json_dto = await get_json_dto_instance(instance.ws_server)
    #                 instance.audio_dto = AudioDataDTO(instance.json_dto)            # 音频分发器
    #                 instance.audio_dto.register_audio_callback(instance._handle_audio_data) # 注册音频处理函数
    #                 instance.screenshot_dto = ScreenShotDataDTO(instance.json_dto)  # 截图分发器
    #                 instance.screenshot_dto.register_screenshot_callback(instance._handle_screenshot_data)  # 注册截图处理函数
    #
    #                 instance.asr_client = create_asr_client(use_async=True, base_url=cfg.asr.url)
    #                 instance.tts_client = GPTSoVITSClient(host=cfg.tts.host, port=cfg.tts.port, debug=True)
    #                 # 切换GPT_SoVITS模型
    #                 await instance.tts_client.set_gpt_weights(cfg.tts.gpt_model_name)
    #                 await instance.tts_client.set_sovits_weights(cfg.tts.sovits_model_name)
    #
    #                 instance.auto_agent_client = UITarsClient(UITarsClientConfig(
    #                     deployment_type=cfg.auto_agent.deployment_type,
    #                     base_url=cfg.auto_agent.base_url,
    #                     model_name=cfg.auto_agent.model_name,
    #                     temperature=cfg.auto_agent.temperature,
    #                     max_tokens=cfg.auto_agent.max_tokens
    #                 ))
    #
    #                 instance.llm_core = YosugaLLMCore(
    #                     model_config=ModelConfig(       # TODO 同上
    #                         provider=ModelProvider.OPENAI,
    #                         model_name=cfg.ai.model_name,
    #                         base_url=cfg.ai.base_url,
    #                         api_key=cfg.ai.api_key,
    #                         temperature=cfg.ai.temperature,
    #                         max_tokens=cfg.ai.max_tokens
    #                     ),
    #                     core_config=LLMCoreConfig(      # TODO 同上
    #                         max_context_tokens=cfg.llm_core.max_context_tokens,
    #                         enable_history=cfg.llm_core.enable_history,
    #                         role_setting=cfg.llm_core.role_character,
    #                         language=cfg.llm_core.language,      # 回复使用语言
    #                         auto_dispatch=True,
    #                         dispatch_async=True  # 启用异步分发
    #                     )
    #                 )
    #                 instance.register_llm_core_analysis()   # 注册解析器
    #                 instance.register_llm_core_action()     # 注册分发器
    #                 instance.llm_core.register_overflow_handler(instance._handle_overflow_logger)   # 注册上下文溢出处理回调
    #
    #                 cls._instance = instance
    #                 logger.success("YosugaServerCore initialized")
    #     return cls._instance
    @classmethod
    async def get_instance(cls) -> "YosugaServerCore":
        """异步单例工厂"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    logger.info("Initializing YosugaServerCore...")

                    # 强制初始化配置
                    from src.config.config import _ensure_initialized
                    from dataclasses import asdict, is_dataclass

                    real_cfg = _ensure_initialized()

                    # 辅助函数：递归转换为 dict
                    def to_dict(obj):
                        if isinstance(obj, dict):
                            return obj
                        if is_dataclass(obj) and not isinstance(obj, type):
                            return asdict(obj)
                        return {}

                    # 提取各个配置段并转换为 dict（关键修复）
                    cfg_dict = {
                        'ai': to_dict(getattr(real_cfg, 'ai', {})),
                        'tts': to_dict(getattr(real_cfg, 'tts', {})),
                        'asr': to_dict(getattr(real_cfg, 'asr', {})),
                        'auto_agent': to_dict(getattr(real_cfg, 'auto_agent', {})),
                        'llm_core': to_dict(getattr(real_cfg, 'llm_core', {})),
                    }

                    logger.debug(f"配置提取完成: ai={type(cfg_dict['ai'])}, tts={type(cfg_dict['tts'])}")

                    # 创建实例
                    instance = cls.__new__(cls)

                    # 按依赖顺序初始化数据分发器
                    instance.ws_server = await get_ws_server()
                    instance.json_dto = await get_json_dto_instance(instance.ws_server)
                    instance.audio_dto = AudioDataDTO(instance.json_dto)
                    instance.audio_dto.register_audio_callback(instance._handle_audio_data)
                    instance.screenshot_dto = ScreenShotDataDTO(instance.json_dto)
                    instance.screenshot_dto.register_screenshot_callback(instance._handle_screenshot_data)

                    # ASR 客户端
                    asr_cfg = cfg_dict.get('asr', {})
                    instance.asr_client = create_asr_client(
                        use_async=True,
                        base_url=asr_cfg.get('url', 'http://localhost:20260/')
                    )

                    # TTS 客户端
                    tts_cfg = cfg_dict.get('tts', {})
                    instance.tts_client = GPTSoVITSClient(
                        host=tts_cfg.get('host', 'localhost'),
                        port=tts_cfg.get('port', 20261),
                        debug=True
                    )

                    # 切换 GPT_SoVITS 模型
                    # await instance.tts_client.set_gpt_weights(
                    #     tts_cfg.get('gpt_model_name', 'GPT_weights_v2Pro/Yosuga_Airi-e32.ckpt')
                    # )
                    # await instance.tts_client.set_sovits_weights(
                    #     tts_cfg.get('sovits_model_name', 'SoVITS_weights_v2Pro/Yosuga_Airi_e16_s864.pth')
                    # )

                    # Auto Agent 客户端
                    auto_cfg = cfg_dict.get('auto_agent', {})
                    instance.auto_agent_client = UITarsClient(UITarsClientConfig(
                        deployment_type=auto_cfg.get('deployment_type', 'lmstudio'),
                        base_url=auto_cfg.get('base_url', 'http://localhost:1234/v1'),
                        model_name=auto_cfg.get('model_name', 'ui-tars-1.5-7b@q4_k_m'),
                        temperature=auto_cfg.get('temperature', 0.1),
                        max_tokens=auto_cfg.get('max_tokens', 16384)
                    ))

                    # LLM Core
                    ai_cfg = cfg_dict.get('ai', {})
                    llm_cfg = cfg_dict.get('llm_core', {})

                    instance.llm_core = YosugaLLMCore(
                        model_config=ModelConfig(
                            provider=ModelProvider.OPENAI,
                            model_name=ai_cfg.get('model_name', 'qwen/qwen3-4b-2507'),
                            base_url=ai_cfg.get('base_url', 'http://localhost:1234/v1'),
                            api_key=ai_cfg.get('api_key'),
                            temperature=ai_cfg.get('temperature', 0.4),
                            max_tokens=ai_cfg.get('max_tokens', 8192)
                        ),
                        core_config=LLMCoreConfig(
                            max_context_tokens=llm_cfg.get('max_context_tokens', 2048),
                            enable_history=llm_cfg.get('enable_history', True),
                            role_setting=llm_cfg.get('role_character',
                                                     '你是由Misakiotoha开发的助手稲葉愛理ちゃん，可以和用户一起玩游戏，聊天，做各种事情，性格抽象，没事爱整整活。'),
                            language=llm_cfg.get('language', '中文'),
                            auto_dispatch=True,
                            dispatch_async=True
                        )
                    )

                    # 注册 YosugaEmbedded 提示词模块
                    instance.llm_core.register_prompt_module(YosugaEmbedded())
                    logger.info("[Core] 嵌入式设备提示词模块已注册")

                    # 初始化嵌入式设备管理框架
                    instance.embedded_server = YosugaServer(
                        config=ServerConfig(
                            device_conflict_strategy="rename",
                            max_concurrent_calls=10,
                            device_timeout=30.0,
                        )
                    )
                    instance.device_dto = DeviceDataDTO(
                        instance.json_dto, instance.embedded_server
                    )
                    # 当 YosugaServer 需要发送 RPC 到设备时，通过 WebSocket 发出 device_command
                    instance.embedded_server.on_device_message = (
                        instance._on_device_message
                    )
                    # 当设备能力变更时，更新 LLM 系统提示词中的状态表
                    instance.embedded_server.on_capabilities_changed = (
                        instance._on_capabilities_changed
                    )
                    logger.success("[Core] 嵌入式设备管理框架已初始化")

                    # 注册设备 RPC 响应回调（设备结果回来后喂回 LLM）
                    instance.device_dto.register_device_callback(
                        instance._on_device_rpc_response
                    )
                    instance._pending_rpc: Optional[dict] = None

                    instance.register_llm_core_analysis()
                    instance.register_llm_core_action()
                    instance.llm_core.register_overflow_handler(instance._handle_overflow_logger)

                    cls._instance = instance
                    logger.success("YosugaServerCore initialized")

        return cls._instance


    def register_llm_core_action(self):
        """
        注册llm_core的分发器
        """
        if self.llm_core is None:
            raise Exception("LLMCore is not initialized")
        self.llm_core.register_action_handler("audio_text", self._handle_audio_response, is_async=True)
        self.llm_core.register_action_handler("auto_agent", self._handle_auto_agent, is_async=True)
        self.llm_core.register_action_handler("call_auto_agent", self._handle_call_auto_agent, is_async=True)
        self.llm_core.register_action_handler("embedded_control", self._handle_embedded_control, is_async=True)
        self.llm_core.set_fallback_handler(self._handle_fallback)

    def register_llm_core_analysis(self):
        """
        注册llm_core的输出解析器
        """
        if self.llm_core is None:
            raise Exception("LLMCore is not initialized")
        self.llm_core.register_analysis_model(YosugaAudioResponseData)
        self.llm_core.register_analysis_model(YosugaUITARSResponseData)
        self.llm_core.register_analysis_model(YosugaUITARSRequestData)
        self.llm_core.register_analysis_model(YosugaEmbeddedResponseData)

    def _handle_overflow_logger(self, history: List[Any], metadata: Dict[str, Any]):
        """上下文溢出记录，仅打印日志"""
        print(f"   上下文溢出！")
        print(f"   模型: {metadata['model']}")
        print(f"   消息数: {metadata['message_count']}")
        print(f"   Token: {metadata['estimated_tokens']}/{metadata['limit']}")
        print(f"   即将遗忘 {len(history) // 2} 条旧消息")

    async def _handle_audio_data(self, audio_data: AudioDataTransferObject):
        """
        音频数据接收call back
        Yosuga_server只有接受到每次这个audio数据才会跑一次
        """
        logger.info("Received audio data")
        # 在此处客户端发送的音频数据必定不是流式数据(考虑客户端发送数据给服务端往往是在本地的，速度极快)
        # 将音频数据发送给asr转换成文本信息，音频数据格式为wav
        # TODO: 考虑在此处做一个简单的vad检测，如果客户端发送的音频是静音的，则不把请求发给llm_core
        asr_response = await self.asr_client.transcribe_bytes(audio_data.data)
        if not asr_response.success:
            logger.error(f"ASR failed: {asr_response.error}")
        asr_result = asr_response.data  # 获取asr结果
        # 将asr结果发送给llm_core进行处理
        llm_result = await self.llm_core.interact(
            user_input={    # 构造用户输入信息
                "text": asr_result.text,
                "confidence": asr_result.confidence
            }
        )   # llm_core会自动进行处理并通过执行器异步返回各种相关的数据

    async def _handle_screenshot_data(self, screenshot_data: ScreenShotDataTransferObject):
        """
        屏幕截图数据接收call back
        将llm_core的回复封装后提交给auto_agent模块，获得自动化agent的返回之后再返回给llm_core
        """
        logger.info(f"Received screenshot data {len(screenshot_data.RealTimeScreenShot)}")
        if not screenshot_data.isSuccess: # 如果客户端截图失败
            logger.error("Screenshot failed")
            return  # 直接提前结束回调，不向llm_core发送结果
        # TODO 对于设备描述信息(screenshot_data.DescribeInfo)，考虑加入到auto_agent的输入中，增强识别准确率
        # 构造请求 异步调用
        logger.debug(f"screenshot_data.LLMResponse(来自llm_core向auto_agent的输入): {screenshot_data.LLMResponse}")
        logger.debug(f"客户端设备信息: {screenshot_data.DescribeInfo}")
        auto_agent_response: str = await self.auto_agent_client.call_async(screenshot_data.LLMResponse,
                                                                           screenshot_data.RealTimeScreenShot)
        logger.debug(f"auto_agent_response(auto_agent原生返回结果): {auto_agent_response}")
        # 将auto_agent的返回结果发送给llm_core
        await self.llm_core.interact(
            user_input={  # 构造auto_agent输入信息
                "auto_agent": auto_agent_response
            }
        )

    async def _handle_audio_response(self, data: YosugaAudioResponseData):
        """
        llm_core异步处理器：语音回复
        将llm_core的回复封装后提交给tts模块，调用tts模块中的流式返回，并将流式frame返回给Yosuga客户端
        """
        if data.type == "audio_text":
            logger.info("Handling audio response")
            try:
                # 使用最快模式流式输出
                chunk_count = 0
                # async for chunk in await self.tts_client.tts(
                #         text=data.response_text,
                #         ref_audio_path="uploaded_audio/test_voice.wav", # TODO 需要替换成config或者后续设计情感系统
                #         text_lang="ja",
                #         prompt_lang="ja",
                #         prompt_text="もう!こんなところで何やってるんだよ!",  # 参考语音的真实文本
                #         streaming_mode=StreamingMode.FASTEST,  # 模式3：快速流式
                #         media_type="wav"
                # ):
                async for chunk in await self.tts_client.tts(
                    text=data.response_text,
                    ref_audio_path="uploaded_audio/kq.wav", # TODO 需要替换成config或者后续设计情感系统
                    text_lang="zh",
                    prompt_lang="zh",
                    prompt_text="电闪雷鸣虽然有点吓人，但璃月港的防雷防火工事是一流的，不用担心。",  # 参考语音的真实文本
                    streaming_mode=StreamingMode.FASTEST,  # 模式3：快速流式
                    media_type="wav"
                ):
                    chunk_count += 1
                    # print(f"🎵 收到音频块 #{chunk_count}: {len(chunk.audio_data)} bytes")
                    if chunk_count == 1:    # 如果是第一个音频块
                        # 构造音频首包发送给客户端
                        await self.audio_dto.send_audio_data(
                            AudioDataTransferObject(
                                data=chunk.audio_data,
                                isStream=True,
                                isStart=True,
                                sequence=chunk_count,
                                isEnd=False,
                                text=data.response_text
                            )
                        )
                    else:   # 如果不是第一个音频块，则发送中间包给客户端
                        await self.audio_dto.send_audio_data(
                            AudioDataTransferObject(
                                data=chunk.audio_data,
                                isStream=True,
                                isStart=False,
                                sequence=chunk_count,
                                isEnd=False,
                                text=data.response_text
                            )
                        )
                print(f"流式TTS完成！共{chunk_count}个音频块")
                # 构造音频尾包发送给客户端(虚假的音频数据)
                await self.audio_dto.send_audio_data(
                    AudioDataTransferObject(
                        data=b"0",
                        isStream=True,
                        isStart=False,
                        sequence=chunk_count + 1,
                        isEnd=True,
                        text=data.response_text
                    )
                )
            except Exception as e:
                print(f"流式错误: {e}")
            return {"status": "success", "executed": data.response_text}
        return None

    async def _handle_auto_agent(self, data: YosugaUITARSResponseData):
        """
        llm_core异步处理器：处理自动化操作
        将llm_core的回复封装后提交给Yosuga客户端，由客户端进行执行相关的GUI自动化操作
        """
        # 构造并发送回复数据
        await self.json_dto.send_json(
            AutoAgentDataTransferObject.from_json(data.to_dict()).to_json()
        )
        return {"status": "success", "executed": data.Action}

    async def _handle_call_auto_agent(self, data: YosugaUITARSRequestData):
        """
        llm_core异步处理器：处理llm_core调用auto_agent需求
        向客户端请求当前界面的截图，请求成功后由_handle_screenshot_data函数完成剩下的任务
        """
        if data.type == "call_auto_agent":
            logger.info("LLM Calling auto agent")
            # 向客户端请求当前界面的截图的base64编码 加入llm回复的信息到截图请求DTO当中 方便_handle_screenshot_data构造请求
            await self.screenshot_dto.send_screenshot_data(ScreenShotDataTransferObject(LLMResponse=data.llm_translation))
        return {"status": "success", "executed": data.type}

    async def _handle_embedded_control(self, data: YosugaEmbeddedResponseData):
        """
        llm_core异步处理器：嵌入式设备控制
        将LLM输出的 JSON-RPC 调用列表交由 YosugaServer 框架处理并路由到对应设备
        """
        logger.info(f"Handling embedded control: {len(data.calls)} calls")

        results = self.embedded_server.process_ai_response(json.dumps(data.calls))
        logger.info(f"Embedded control results: {results}")

        # 保存 pending RPC 信息，等设备异步响应回来后喂回 LLM
        if results and len(results) > 0:
            first_call = results[0]
            self._pending_rpc = {
                "device_id": first_call.get("device_id"),
                "method": first_call.get("method"),
                "call_id": first_call.get("id"),
                "original_response_text": data.response_text or "",
            }

        # 如果 LLM 同时返回了需要回复用户的文本，通过 TTS 播报
        if data.response_text:
            try:
                chunk_count = 0
                # async for chunk in await self.tts_client.tts(
                #     text=data.response_text,
                #     ref_audio_path="uploaded_audio/test_voice.wav",
                #     text_lang="ja",
                #     prompt_lang="ja",
                #     prompt_text="もう!こんなところで何やってるんだよ!",
                #     streaming_mode=StreamingMode.FASTEST,
                #     media_type="wav"
                # ):
                async for chunk in await self.tts_client.tts(
                    text=data.response_text,
                    ref_audio_path="uploaded_audio/kq.wav", # TODO 需要替换成config或者后续设计情感系统
                    text_lang="zh",
                    prompt_lang="zh",
                    prompt_text="电闪雷鸣虽然有点吓人，但璃月港的防雷防火工事是一流的，不用担心。",  # 参考语音的真实文本
                    streaming_mode=StreamingMode.FASTEST,  # 模式3：快速流式
                    media_type="wav"
                ):
                    chunk_count += 1
                    if chunk_count == 1:
                        await self.audio_dto.send_audio_data(
                            AudioDataTransferObject(
                                data=chunk.audio_data,
                                isStream=True, isStart=True,
                                sequence=chunk_count, isEnd=False,
                                text=data.response_text
                            )
                        )
                    else:
                        await self.audio_dto.send_audio_data(
                            AudioDataTransferObject(
                                data=chunk.audio_data,
                                isStream=True, isStart=False,
                                sequence=chunk_count, isEnd=False,
                                text=data.response_text
                            )
                        )
                await self.audio_dto.send_audio_data(
                    AudioDataTransferObject(
                        data=b"0",
                        isStream=True, isStart=False,
                        sequence=chunk_count + 1, isEnd=True,
                        text=data.response_text
                    )
                )
            except Exception as e:
                logger.error(f"Embedded control TTS error: {e}")

        return {"status": "success", "calls": len(data.calls)}

    def _on_device_rpc_response(self, device_id: str, payload: dict):
        """DeviceDataDTO 回调：设备 RPC 响应回来时触发，喂回 LLM"""
        if self._pending_rpc and self._pending_rpc.get("device_id") == device_id:
            call_id = payload.get("id")
            if call_id is None or call_id == self._pending_rpc.get("call_id"):
                pending = self._pending_rpc
                self._pending_rpc = None
                asyncio.create_task(self._continue_with_device_result(device_id, payload, pending))

    async def _continue_with_device_result(self, device_id: str, payload: dict, pending: dict):
        """设备 RPC 结果回来后，喂回 LLM 生成最终回复并 TTS"""
        method = pending.get("method", "unknown")
        original_text = pending.get("original_response_text", "")

        result_str = json.dumps(payload.get("result", payload), ensure_ascii=False)
        followup_input = (
            f"你之前请求设备 {device_id} 执行了 {method} 操作，"
            f"现在设备返回了结果：{result_str}。\n"
            f"你之前的回复是：'{original_text}'\n"
            f"请基于设备返回的实际结果，用自然语言重新组织回复，告诉用户结果。"
        )

        try:
            llm_result = await self.llm_core.interact(user_input={"text": followup_input})
            logger.info(f"[Core] 设备结果回送 LLM 完成: {llm_result}")
        except Exception as e:
            logger.error(f"[Core] 设备结果回送 LLM 失败: {e}")

    def _on_device_message(self, device_id: str, rpc_call: str) -> Optional[str]:
        """YosugaServer 的设备消息回调：通过 WebSocket 发送 RPC 到客户端"""
        logger.info(f"[Core] 发送设备命令到 {device_id}")
        asyncio.create_task(self.device_dto.send_device_command(device_id, rpc_call))
        return None

    def _on_capabilities_changed(self, capabilities: dict):
        """设备能力变更回调：更新 LLM 系统提示词中的状态表"""
        functions_str = json.dumps(capabilities.get("functions", []), ensure_ascii=False, indent=2)
        device_str = json.dumps(capabilities.get("devices", {}), ensure_ascii=False, indent=2)
        state_table = (
            f"【当前在线设备】\n{device_str}\n\n"
            f"【设备可用函数】\n{functions_str}"
        )
        self.llm_core.core_config.system_state_table = state_table
        logger.info(f"[Core] 系统状态表已更新 | 设备: {capabilities.get('device_count', 0)} 台 | 函数: {capabilities.get('function_count', 0)} 个")

    def _handle_fallback(self, data: LLMCoreAnalysisBase):
        """
        llm_core同步处理器：回退处理器
        """
        logger.debug(f"    [Fallback] 未知类型数据: {data.type}, 内容: {data.model_dump_json()}")

    async def run(self):
        """启动服务器"""
        logger.info("Yosuga Server Websocket Core 启动中...")
        await self.ws_server.run(host="0.0.0.0")


# 使用方式
async def main():
    core = await YosugaServerCore.get_instance()
    await core.run()


if __name__ == '__main__':
    asyncio.run(main())