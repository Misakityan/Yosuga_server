# dto/dto_base.py
from abc import ABC
from typing import Callable, Coroutine, Any, Dict
from src.modules.websocket_base_module.websocket_core.core_ws_server import WebSocketServer

class MessageDTO(ABC):
    """DTO基类"""

    def __init__(
            self,
            ws_server : WebSocketServer,  # WebSocketServer单例
    ):
        # 保存服务器实例（用于发送）
        self.ws_server = ws_server

    # 便捷属性，DTO层直接调用
    @property
    def send_binary(self):
        return self.ws_server.send_binary

    @property
    def send_text(self):
        return self.ws_server.send_text

    @property
    def send_json(self):
        return self.ws_server.send_json
