import asyncio
from src.modules.websocket_base_module.dto.dto_templates.audio_data_dto import AudioDataTransferObject
from src.modules.websocket_base_module.dto.dto_templates.screenshot_data_dto import ScreenShotDataTransferObject
from src.modules.websocket_base_module.dto.second_dtos import JsonDTO
from loguru import logger
from typing import Callable, List, Optional, Coroutine

class AudioDataDTO:
    """音频数据交互DTO 再次分发给所有使用到了音频数据的相关业务(最后一级分发)"""
    def __init__(self, json_dto : JsonDTO):
        json_dto.register_receiver('audio_data', self._handle_audio_data)    # 注册JSON接收函数
        logger.info("[AudioDataDTO] 音频接收业务已注册")
        self.json_dto = json_dto
        self.audio_data = AudioDataTransferObject()     # 音频数据对象
        # 业务回调列表，延续观察者模式
        self._audio_callbacks: List[Callable[[AudioDataTransferObject], Coroutine]] = []
        # 最新音频缓存 支持同步查询
        self._latest_audio: Optional[AudioDataTransferObject] = None
        # 流式缓冲区 用于大段音频流
        self._stream_buffer: List[AudioDataTransferObject] = []
        logger.info("[AudioDataDTO] 业务接口已初始化")

    async def _handle_audio_data(self, data: dict):
        """处理音频数据"""
        """
        音频数据json格式:
            {
                'Owner': 'server', 
                'isStream': False, 
                'isStart': False, 
                'isEnd': False, 
                'sequence': 0, 
                'data': '', 
                'sampleRate': 16000, 
                'channelCount': 1, 
                'bitDepth': 16, 
                'duration': 0.0, 
                'text': ''
            }
        """
        logger.debug(f"[AudioDataDTO] 收到音频数据")
        # 将dict反序列化到DTO对象
        self.audio_data = AudioDataTransferObject.from_json(data)
        # 缓存最新数据
        self._latest_audio = self.audio_data
        # 如果是流式数据，加入缓冲区
        if self.audio_data.isStream:
            self._stream_buffer.append(self.audio_data)
            if self.audio_data.isEnd:
                logger.info(f"流式音频接收完成，共 {len(self._stream_buffer)} 块")
        # 通知所有注册的回调
        await self._notify_callbacks()

    # 业务发送接口
    async def send_audio_data(self, data: AudioDataTransferObject) -> None:
        """
        发送音频数据

        Args:
            data: 音频数据DTO
        """
        await self.send_audio(
            Owner=data.Owner,
            is_stream=data.isStream,
            is_start=data.isStart,
            is_end=data.isEnd,
            sequence=data.sequence,
            data=data.data,
            sampleRate=data.sampleRate,
            channelCount=data.channelCount,
            bitDepth=data.bitDepth,
            duration=data.duration,
            text=data.text
        )

    async def send_audio(
            self,
            data: bytes,
            is_stream: bool = False,
            is_start: bool = False,
            is_end: bool = False,
            sequence: int = 0,
            **audio_meta
    ) -> None:
        """
        业务层发送音频的便捷接口

        Args:
            data: 原始音频字节
            is_stream: 是否为流式数据
            is_start: 流式数据开始标记
            is_end: 流式数据结束标记
            sequence: 数据块序号
            **audio_meta: 其他音频参数（sampleRate, channelCount等）
        """
        # 填充音频数据到DTO
        self.audio_data.set_dto_data(
            Owner="server" or audio_meta.get('Owner', "server"),
            isStream=is_stream,
            isStart=is_start,
            isEnd=is_end,
            sequence=sequence,
            data=data,
            sampleRate=audio_meta.get('sampleRate', 16000),
            channelCount=audio_meta.get('channelCount', 1),
            bitDepth=audio_meta.get('bitDepth', 16),
            duration=audio_meta.get('duration', 0.0),
            text=audio_meta.get('text', "")
        )
        # 序列化为JSON并发送 自动处理base64和type字段
        json_message = self.audio_data.to_json()
        await self.json_dto.send_json(json_message)
        logger.info(f"音频已发送: sequence={sequence}, 大小={len(data)} bytes")

    # 业务接收接口
    def register_audio_callback(
            self,
            callback: Callable[[AudioDataTransferObject], Coroutine]
    ) -> None:
        """
        业务注册接收回调

        使用示例:
            async def my_audio_handler(audio_dto: AudioDataTransferObject):
                print(f"收到音频: {len(audio_dto.data)} bytes")

            audio_dto.register_audio_callback(my_audio_handler)
        """
        self._audio_callbacks.append(callback)
        logger.debug(f"业务音频回调已注册，当前共 {len(self._audio_callbacks)} 个")

    def unregister_audio_callback(self, callback) -> None:
        """注销业务回调"""
        if callback in self._audio_callbacks:
            self._audio_callbacks.remove(callback)
            logger.debug("业务音频回调已注销")

    def get_latest_audio(self) -> Optional[AudioDataTransferObject]:
        """
        同步获取最新音频数据（轮询模式）

        Returns:
            最新接收到的音频DTO，如果没有则为 None
        """
        return self._latest_audio

    def clear_stream_buffer(self) -> None:
        """清空流式缓冲区"""
        self._stream_buffer.clear()
        logger.debug("流式音频缓冲区已清空")

    # 内部通知机制
    async def _notify_callbacks(self) -> None:
        """通知所有业务回调"""
        if not self._audio_callbacks:
            logger.warning("无业务回调，音频数据未处理")
            return
        tasks = [callback(self.audio_data) for callback in self._audio_callbacks]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug(f"已通知 {len(self._audio_callbacks)} 个业务回调")
    # 异步迭代器 流式时使用
    def __aiter__(self):
        """支持 async for 循环接收流式音频"""
        return self
    async def __anext__(self) -> AudioDataTransferObject:
        """异步迭代器协议"""
        pass

class ScreenShotDataDTO:
    """截屏数据交互DTO 分发给所有使用到了截屏数据的相关业务(最后一级分发)"""
    def __init__(self, json_dto : JsonDTO):
        json_dto.register_receiver('screenshot_data', self._handle_screenshot_data)    # 注册JSON接收函数
        logger.info("[ScreenShotDataDTO] 截屏接收业务已注册")
        self.json_dto = json_dto
        self.screenshot_data = ScreenShotDataTransferObject()     # 截屏数据对象
        # 业务回调列表，延续观察者模式
        self._screenshot_callbacks: List[Callable[[ScreenShotDataTransferObject], Coroutine]] = []
        # 最新截屏数据缓存 支持同步查询
        self._latest_screenshot: Optional[ScreenShotDataTransferObject] = None
        logger.info("[ScreenShotDataDTO] 业务接口已初始化")

    async def _handle_screenshot_data(self, data: dict):
        """处理截屏数据"""
        """
        截屏数据json格式:
            {
                "Owner": "数据的拥有者(server or client)",
                "isSuccess": "是否截图成功(true or false)"
                "RealTimeScreenShot": "客户端设备的实时截图数据(base64)",
                "Width": "截图的宽度",
                "Height": "截图的高度",
                "DescribeInfo": "设备的描述信息(告知模型以做出更加准确的判断)"
            }
        """
        logger.debug(f"[ScreenShotDataDTO] 收到截屏数据")
        # 将dict反序列化到DTO对象
        self.screenshot_data = ScreenShotDataTransferObject.from_json(data)
        # 缓存最新数据
        self._latest_screenshot = self.screenshot_data
        # 通知所有注册的回调
        await self._notify_callbacks()

    # 业务发送接口
    async def send_screenshot_data(self, data: ScreenShotDataTransferObject) -> None:
        """
        发送音频数据

        Args:
            data: 音频数据DTO
        """
        await self.send_screenshot(
            Owner=data.Owner,
            isSuccess=data.isSuccess,
            RealTimeScreenShot=data.RealTimeScreenShot,
            Width=data.Width,
            Height=data.Height,
            DescribeInfo=data.DescribeInfo,
            LLMResponse=data.LLMResponse
        )

    async def send_screenshot(
            self,
            **screenshot_meta
    ) -> None:
        """
        业务层发送音频的便捷接口
        一般来说，作为发送请求方，不需要填充任何数据

        Args:
            **screenshot_meta: 截屏数据元信息
        """
        # 填充音频数据到DTO
        self.screenshot_data.set_dto_data(
            Owner="server" or screenshot_meta.get('Owner', "server"),
            isSuccess=screenshot_meta.get('isSuccess', False),
            RealTimeScreenShot=screenshot_meta.get('RealTimeScreenShot', ""),
            Width=screenshot_meta.get('Width', 1920),
            Height=screenshot_meta.get('Height', 1080),
            DescribeInfo=screenshot_meta.get('DescribeInfo', False),
            LLMResponse=screenshot_meta.get('LLMResponse', "")
        )
        # 序列化为JSON并发送 自动处理base64和type字段
        json_message = self.screenshot_data.to_json()
        await self.json_dto.send_json(json_message)
        logger.info(f"截屏包已发送")

    # 业务接收接口
    def register_screenshot_callback(
            self,
            callback: Callable[[ScreenShotDataTransferObject], Coroutine]
    ) -> None:
        """
        业务注册接收回调
        """
        self._screenshot_callbacks.append(callback)
        logger.debug(f"业务截屏回调已注册，当前共 {len(self._screenshot_callbacks)} 个")

    def unregister_screenshot_callback(self, callback) -> None:
        """注销业务回调"""
        if callback in self._screenshot_callbacks:
            self._screenshot_callbacks.remove(callback)
            logger.debug("业务截屏回调已注销")

    def get_latest_screenshot(self) -> Optional[ScreenShotDataTransferObject]:
        """
        同步获取最新截屏数据（轮询模式）

        Returns:
            最新接收到的截屏数据DTO，如果没有则为 None
        """
        return self._latest_screenshot

    # 内部通知机制
    async def _notify_callbacks(self) -> None:
        """通知所有业务回调"""
        if not self._screenshot_callbacks:
            logger.warning("无业务回调，截屏数据未处理")
            return
        tasks = [callback(self.screenshot_data) for callback in self._screenshot_callbacks]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug(f"已通知 {len(self._screenshot_callbacks)} 个业务回调")
