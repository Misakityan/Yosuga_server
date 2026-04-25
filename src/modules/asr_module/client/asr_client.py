# asr_module/client/asr_client.py
import asyncio
import time
from pathlib import Path
from typing import Union, Optional
import aiofiles
import aiohttp
import requests
from loguru import logger
from .models import ASRResponse, ASRHealthStatus, ServiceInfo

class ASRException(Exception):
    """ASR服务调用异常"""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class ASRClientConfig:
    """客户端配置"""
    def __init__(
            self,
            base_url: str = "http://localhost:8000",
            timeout: float = 30.0,
            retry_count: int = 2,
            retry_delay: float = 0.5,
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay


# 同步客户端
class ASRClientSync:
    """同步ASR客户端"""
    def __init__(self, config: Optional[ASRClientConfig] = None):
        self.config = config or ASRClientConfig()
        self.session = requests.Session()
        self.session.timeout = self.config.timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """统一请求处理（带重试）"""
        url = f"{self.config.base_url}{endpoint}"

        for attempt in range(self.config.retry_count + 1):
            try:
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt < self.config.retry_count:
                    logger.warning(f"请求失败，重试中 ({attempt + 1}/{self.config.retry_count}): {e}")
                    time.sleep(self.config.retry_delay)
                else:
                    logger.error(f"请求最终失败: {e}")
                    raise ASRException(f"API调用失败: {e}", getattr(e.response, 'status_code', None))

    def transcribe_file(self, file_path: Union[str, Path]) -> ASRResponse:
        """
        转录音频文件

        Args:
            file_path: 音频文件路径

        Returns:
            ASRResponse对象

        Example:
            client = ASRClientSync()
            result = client.transcribe_file("/path/to/audio.wav")
            print(result.data.text)
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        logger.info(f"上传文件: {file_path.name}")

        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f, 'audio/wav')}
            result = self._request('POST', '/transcribe', files=files)

        return ASRResponse(**result)

    def transcribe_bytes(self, audio_data: bytes, filename: str = "audio.wav") -> ASRResponse:
        """
        转录音频字节流

        Args:
            audio_data: 原始音频字节
            filename: 模拟文件名（用于MIME类型推断）

        Returns:
            ASRResponse对象

        Example:
            with open('audio.wav', 'rb') as f:
                audio_bytes = f.read()
            result = client.transcribe_bytes(audio_bytes)
        """
        logger.info(f"上传字节流 ({len(audio_data)} bytes)")

        files = {'file': (filename, audio_data, 'audio/wav')}
        result = self._request('POST', '/transcribe', files=files)

        return ASRResponse(**result)

    def health_check(self) -> ASRHealthStatus:
        """健康检查"""
        result = self._request('GET', '/health')
        return ASRHealthStatus(**result)

    def get_service_info(self) -> ServiceInfo:
        """获取服务信息"""
        result = self._request('GET', '/')
        return ServiceInfo(**result)


# 异步客户端
class ASRClientAsync:
    """异步ASR客户端"""
    def __init__(self, config: Optional[ASRClientConfig] = None):
        self.config = config or ASRClientConfig()
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            )

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """统一异步请求（带重试）"""
        await self._ensure_session()
        url = f"{self.config.base_url}{endpoint}"

        for attempt in range(self.config.retry_count + 1):
            try:
                async with self._session.request(method, url, **kwargs) as response:
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ClientError as e:
                if attempt < self.config.retry_count:
                    logger.warning(f"请求失败，重试中 ({attempt + 1}/{self.config.retry_count}): {e}")
                    await asyncio.sleep(self.config.retry_delay)
                else:
                    logger.error(f"请求最终失败: {e}")
                    raise ASRException(f"API调用失败: {e}", getattr(e, 'status', None))

    async def transcribe_file(self, file_path: Union[str, Path]) -> ASRResponse:
        """异步转录音频文件"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        logger.info(f"上传文件: {file_path.name}")

        async with aiofiles.open(file_path, 'rb') as f:
            audio_data = await f.read()

        return await self.transcribe_bytes(audio_data, file_path.name)

    async def transcribe_bytes(self, audio_data: bytes, filename: str = "audio.wav") -> ASRResponse:
        """异步转录音频字节流"""
        logger.info(f"上传字节流 ({len(audio_data)} bytes)")
        await self._ensure_session()    # 确保session已创建
        form = aiohttp.FormData()       # 创建表单数据
        form.add_field('file', audio_data, filename=filename, content_type='audio/wav') # 添加文件字段
        result = await self._request('POST', '/transcribe', data=form)       # 发送POST请求
        return ASRResponse(**result)    # 返回结果

    async def health_check(self) -> ASRHealthStatus:
        """异步健康检查"""
        result = await self._request('GET', '/health')
        return ASRHealthStatus(**result)

    async def get_service_info(self) -> ServiceInfo:
        """异步获取服务信息"""
        result = await self._request('GET', '/')
        return ServiceInfo(**result)

# 工厂函数
def create_asr_client(use_async: bool = False, **config_kwargs) -> Union[ASRClientSync, ASRClientAsync]:
    """
    创建客户端工厂函数

    Args:
        use_async: 是否创建异步客户端
        **config_kwargs: ASRClientConfig参数

    Returns:
        同步或异步客户端实例
    """
    config = ASRClientConfig(**config_kwargs)
    if use_async:
        return ASRClientAsync(config)
    return ASRClientSync(config)