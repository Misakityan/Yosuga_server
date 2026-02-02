# dto/second_dtos.py
import asyncio
from typing import Callable, Optional, Dict, Any, List, Coroutine
from src.modules.websocket_base_module.dto.dto_base import MessageDTO
from loguru import logger

"""
二级分发器，因为没有信号与槽机制，因此使用观察者模式替代
"""
def singleton(cls):     # 单例
    _instance = None
    _lock = asyncio.Lock()
    async def get_instance(*args, **kwargs):
        nonlocal _instance
        if _instance is None:
            async with _lock:
                if _instance is None:
                    _instance = cls(*args, **kwargs)
        return _instance

    cls.get_instance = get_instance
    return cls
# 类型别名
ReceiveCallback = Callable[[Any], Coroutine[Any, Any, None]]
@singleton
class JsonDTO(MessageDTO):
    """针对json消息的二级分发"""
    """
    明确业务json格式：
        {
            "type" : "xxx",
            "timestamp" : "95153...",
            "data" : "{根据业务的不同，有不同的内容}"
        }
    """
    # 因为不同的数据块的json以type字段进行包装，根据type进行正确的数据分发
    def __init__(self, ws_server):
        super().__init__(ws_server)
        self.receivers : Dict[str, List[ReceiveCallback]] = {
            'audio_data' : [],      # 音频数据
            'screenshot_data' : []  # 截图数据
        }
        # 注册json处理callback function
        ws_server.register_receiver('json', self._handle_json)
        logger.info("[JsonDTO] JSON分发器已注册")

    def register_receiver(self, types : str, callback : ReceiveCallback):
        """注册二次分发业务接收函数，供业务DTO调用"""
        if types in self.receivers:
            self.receivers[types].append(callback)
            logger.debug(f"[JsonDTO] 已注册 {types} 接收器，当前共 {len(self.receivers[types])} 个")
        else:
            raise ValueError(f"[JsonDTO] 不支持的分发类型: {types}")

    def unregister_receiver(self, types : str, callback : ReceiveCallback):
        """注销二次分发业务接收函数"""
        if callback in self.receivers[types]:
            self.receivers[types].remove(callback)
            logger.debug(f"[JsonDTO] 已注销 {types} 接收器")

    async def _handle_json(self, data: dict):
        """JSON消息处理"""
        logger.info(f"[JsonDTO] 收到消息")
        logger.debug(f'[JsonDTO] 当前消息时间戳: {data["timestamp"]}')
        # 根据类型进行自动分发
        await self._dispatch(data.get("type"), data["data"])

    async def _dispatch(self, types : str, data : dict):
        """二次分发json数据到相应的接收函数当中"""
        callbacks = self.receivers[types]   # 获取相关types的所有观察者
        if not callbacks:
            logger.info(f"[JsonDTO] 无 {types} 接收器，消息被忽略")
            return
        # 并发执行所有回调
        tasks = [callback(data) for callback in callbacks]
        await asyncio.gather(*tasks, return_exceptions=True)
async def get_json_dto_instance(ws_server) -> JsonDTO:
    return JsonDTO(ws_server)


class EchoDTO(MessageDTO):
    """回声DTO：只处理文本消息 测试用"""

    def __init__(self, ws_server):
        super().__init__(ws_server)
        # 注册文本接收函数
        ws_server.register_receiver('text', self._handle_text)
        logger.info("[EchoDTO] 文本接收器已注册")

    async def _handle_text(self, message: str):
        """文本消息处理"""
        logger.info(f"[EchoDTO] 收到文本: {message}")

        # 业务逻辑
        await self.send_text(f"Echo: {message}")
