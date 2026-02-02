# gpt_sovits/gpt_sovits_client.py
import asyncio
import json
from loguru import logger
from enum import Enum
from pathlib import Path
from typing import AsyncGenerator, Optional, Union, Dict, Any
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field, validator


class APIError(Exception):
    """API调用异常"""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error {status_code}: {message}")


class StreamingMode(Enum):
    """流式模式枚举"""
    DISABLED = 0          # 非流式
    BEST_QUALITY = 1      # 最佳质量（慢）
    MEDIUM_QUALITY = 2    # 中等质量
    FASTEST = 3          # 最快响应（较低质量）


class TTSConfig(BaseModel):
    """TTS请求配置模型"""
    text: str = Field(..., description="待合成文本")
    text_lang: str = Field(..., description="文本语言: zh/en/ja/ko/cantonese")
    ref_audio_path: str = Field(..., description="参考音频路径")
    prompt_lang: str = Field(..., description="提示文本语言")

    # 可选参数
    prompt_text: str = Field(default="", description="参考音频提示文本")
    aux_ref_audio_paths: list = Field(default_factory=list, description="辅助参考音频")
    top_k: int = Field(default=5, ge=1, le=100, description="Top-K采样")
    top_p: float = Field(default=1.0, ge=0.1, le=1.0, description="Top-P采样")
    temperature: float = Field(default=1.0, ge=0.1, le=1.0, description="采样温度")
    text_split_method: str = Field(default="cut5", description="文本分割方法")    # 默认按照标点符号切分
    batch_size: int = Field(default=8, ge=1, le=200, description="批处理大小")
    speed_factor: float = Field(default=1.0, ge=0.6, le=1.65, description="语速倍率")

    # 流式相关
    streaming_mode: Union[bool, int, StreamingMode] = Field(default=False, description="流式模式")
    media_type: str = Field(default="wav", description="输出格式: wav/raw/ogg/aac") # 输出格式

    # 高级参数
    repetition_penalty: float = Field(default=1.35, ge=1.0, le=2.0)     # 惩罚参数
    sample_steps: int = Field(default=32, ge=10, le=100)                # 采样步数
    parallel_infer: bool = Field(default=True)                          # 并行推理

    @validator('text_lang', 'prompt_lang')
    def validate_language(cls, v):
        """验证语言代码"""
        valid_langs = {'zh', 'en', 'ja', 'ko', 'cantonese'}
        if v.lower() not in valid_langs:
            raise ValueError(f"Unsupported language: {v}. Must be one of {valid_langs}")
        return v.lower()

    @validator('media_type')
    def validate_media_type(cls, v):
        """验证媒体类型"""
        valid_types = {'wav', 'raw', 'ogg', 'aac'}
        if v not in valid_types:
            raise ValueError(f"Unsupported media_type: {v}")
        return v

    def build_request(self) -> Dict[str, Any]:
        """构建API请求数据"""
        data = self.dict(exclude_none=True)
        # 处理流式模式
        if isinstance(self.streaming_mode, StreamingMode):
            data['streaming_mode'] = self.streaming_mode.value
        return data


@dataclass
class AudioResponse:
    """音频响应包装类"""
    audio_data: bytes
    sample_rate: int = 32000

    def save(self, path: Union[str, Path]) -> None:
        """保存音频文件"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            f.write(self.audio_data)
        logger.info(f"Audio saved to {path}, size: {len(self.audio_data)} bytes")


class GPTSoVITSClient:
    """
    GPT-SoVITS异步API客户端

    完整支持所有TTS功能：
    - 文本合成（流式/非流式）
    - 模型切换（GPT/SoVITS）
    - 参考音频设置
    - 服务器控制
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9880, debug: bool = False):
        """
        初始化客户端

        Args:
            host: API服务器地址
            port: API端口
            debug: 是否开启调试模式
        """
        self.base_url = f"http://{host}:{port}"
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(30.0, connect=5.0)
        )
        self.debug_mode = debug
        logger.info(f"GPT-SoVITS Client initialized: {self.base_url}")

    async def __aenter__(self) -> "GPTSoVITSClient":
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()

    async def close(self):
        """关闭HTTP连接"""
        await self.client.aclose()
        logger.info("Client connection closed")

    def _log_debug(self, message: str, **kwargs):
        """调试日志"""
        if self.debug_mode:
            logger.debug(f"{message} | {kwargs}")

    async def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """统一响应处理"""
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'application/json' in content_type:
                return response.json()
            return {"status": "success", "content": response.content}
        else:
            try:
                error_data = response.json()
                raise APIError(response.status_code, error_data.get('message', 'Unknown error'))
            except json.JSONDecodeError:
                raise APIError(response.status_code, response.text)

    # 核心TTS接口
    async def tts(
        self,
        text: str,
        ref_audio_path: str,
        text_lang: str = "zh",
        prompt_lang: str = "zh",
        streaming_mode: StreamingMode = StreamingMode.DISABLED,     # 默认禁用流式
        media_type: str = "wav",
        **kwargs
    ) -> Union[AudioResponse, AsyncGenerator[AudioResponse, None]]:
        """
        文本转语音（支持流式）

        Args:
            text: 待合成文本
            ref_audio_path: 参考音频路径（服务器本地路径或URL）
            text_lang: 文本语言
            prompt_lang: 提示语言
            streaming_mode: 流式模式
            media_type: 输出格式
            **kwargs: 其他TTS参数

        Returns:
            非流式: AudioResponse对象
            流式: AsyncGenerator[AudioResponse, None]异步生成器

        Example:
            # 非流式
            audio = await client.tts("你好", "ref.wav")

            # 流式
            async for chunk in client.tts("你好", "ref.wav", streaming_mode=StreamingMode.FASTEST):
                process(chunk.audio_data)
        """
        config = TTSConfig(
            text=text,
            ref_audio_path=ref_audio_path,
            text_lang=text_lang,
            prompt_lang=prompt_lang,
            streaming_mode=streaming_mode,
            media_type=media_type,
            **kwargs
        )

        self._log_debug("TTS Request", config=config.dict())

        if streaming_mode == StreamingMode.DISABLED:
            # 非流式模式
            response = await self.client.post("/tts", json=config.build_request())
            if response.status_code != 200:
                raise APIError(response.status_code, await response.text())

            return AudioResponse(
                audio_data=response.content,
                sample_rate=32000  # 默认采样率
            )
        else:
            # 流式模式
            config.parallel_infer = False   # 强制关闭并行推理，避免与流式冲突
            config.batch_size = 1           # 流式下batch_size必须为1
            async def stream_generator():
                async with self.client.stream(
                    "POST", "/tts",
                    json=config.build_request(),
                    timeout=httpx.Timeout(60.0)  # 流式需要更长超时
                ) as response:
                    if response.status_code != 200:
                        raise APIError(response.status_code, await response.aread())

                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield AudioResponse(audio_data=chunk)

            return stream_generator()

    # 模型管理接口
    async def set_gpt_weights(self, weights_path: str) -> bool:
        """
        切换GPT模型权重

        Args:
            weights_path: 权重文件路径（服务器本地路径）

        Returns:
            bool: 是否成功

        Example:
            await client.set_gpt_weights("models/s1bert.ckpt")
        """
        if not weights_path:
            raise ValueError("weights_path cannot be empty")

        params = {"weights_path": weights_path}
        response = await self.client.get("/set_gpt_weights", params=params)
        result = await self._handle_response(response)

        logger.info(f"GPT weights switched to: {weights_path}")
        return True

    async def set_sovits_weights(self, weights_path: str) -> bool:
        """
        切换SoVITS模型权重

        Args:
            weights_path: 权重文件路径（服务器本地路径）

        Returns:
            bool: 是否成功
        """
        if not weights_path:
            raise ValueError("weights_path cannot be empty")

        params = {"weights_path": weights_path}
        response = await self.client.get("/set_sovits_weights", params=params)
        await self._handle_response(response)

        logger.info(f"SoVITS weights switched to: {weights_path}")
        return True

    # 参考音频管理
    async def set_refer_audio(
        self,
        audio_source: Union[str, Path, bytes],
        audio_name: Optional[str] = None
    ) -> bool:
        """
        设置参考音频（支持多种输入方式）

        Args:
            audio_source: 音频文件路径（str/Path）或音频数据（bytes）
            audio_name: 音频文件名（仅bytes输入时需要）

        Returns:
            bool: 是否成功

        Example:
            # 方式1: 服务器本地文件
            await client.set_refer_audio("/path/to/audio.wav")

            # 方式2: 上传音频数据
            with open("audio.wav", "rb") as f:
                await client.set_refer_audio(f.read(), "audio.wav")
        """
        if isinstance(audio_source, (str, Path)):
            # GET方式：服务器本地路径
            params = {"refer_audio_path": str(audio_source)}
            response = await self.client.get("/set_refer_audio", params=params)
            await self._handle_response(response)
            logger.info(f"Reference audio set: {audio_source}")
        else:
            # POST方式：上传音频数据
            if not audio_name:
                raise ValueError("audio_name is required when uploading bytes")

            files = {"audio_file": (audio_name, audio_source, "audio/wav")}
            response = await self.client.post("/set_refer_audio", files=files)
            await self._handle_response(response)
            logger.info(f"Reference audio uploaded: {audio_name}")

        return True

    # 服务器控制
    async def control_command(self, command: str) -> bool:
        """
        发送控制命令

        Args:
            command: 命令类型 - "restart" 或 "exit"

        Returns:
            bool: 是否成功

        Warning:
            "exit"命令会终止API服务器进程！
        """
        if command not in ["restart", "exit"]:
            raise ValueError("Command must be 'restart' or 'exit'")

        response = await self.client.get("/control", params={"command": command})
        await self._handle_response(response)

        logger.warning(f"Control command executed: {command}")
        return True

    # 高级快捷方法
    async def get_server_info(self) -> Dict[str, Any]:
        """获取服务器状态信息"""
        # 通过调用根路径或自定义health接口
        try:
            response = await self.client.get("/")
            return {"status": "online", "detail": response.text}
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    async def batch_tts(
        self,
        texts: list[str],
        ref_audio_path: str,
        **kwargs
    ) -> list[AudioResponse]:
        """
        批量TTS合成

        Args:
            texts: 文本列表
            ref_audio_path: 参考音频
            **kwargs: 其他TTS参数

        Returns:
            list[AudioResponse]: 音频响应列表
        """
        tasks = [
            self.tts(text, ref_audio_path, **kwargs)
            for text in texts
        ]
        return await asyncio.gather(*tasks)


# 异步上下文管理器辅助函数
async def create_client(*args, **kwargs) -> GPTSoVITSClient:
    """快速创建客户端实例"""
    return GPTSoVITSClient(*args, **kwargs)