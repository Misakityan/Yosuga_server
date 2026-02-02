# websocket_core/core_ws_server.py
import asyncio
import json
from typing import Callable, Optional, Dict, Any, List, Coroutine
from websockets.asyncio.server import serve, ServerConnection
from websockets.exceptions import ConnectionClosed
from loguru import logger

# 类型别名
ReceiveCallback = Callable[[Any], Coroutine[Any, Any, None]]
class WebSocketServer:
    """WebSocket服务端核心模块（单例 + 单客户端）
    只管理一个客户端连接，DTO层注册接收函数，服务端只负责分发。
    """
    _instance: Optional["WebSocketServer"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        """同步单例（__init__ 可以是 async）"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        # 防止重复初始化
        if self._initialized:
            return
        self._websocket: Optional[ServerConnection] = None
        self._receivers: Dict[str, List[ReceiveCallback]] = {
            'binary': [],
            'text': [],
            'json': []
        }
        self._connected_event = asyncio.Event()
        self._initialized = True
        logger.info("WebSocketServer 单客户端分发器已初始化")

    # DTO层注册接口
    def register_receiver(self, msg_type: str, callback: ReceiveCallback) -> None:
        """注册接收函数（供DTO层调用）

        Args:
            msg_type: 消息类型（binary/text/json）
            callback: 接收回调，签名为 (data) -> coroutine
        """
        if msg_type in self._receivers:
            self._receivers[msg_type].append(callback)
            logger.debug(f"已注册 {msg_type} 接收器，当前 {msg_type} 类型接收器共 {len(self._receivers[msg_type])} 个")
        else:
            raise ValueError(f"不支持的消息类型: {msg_type}")

    def unregister_receiver(self, msg_type: str, callback: ReceiveCallback) -> None:
        """注销接收函数"""
        if callback in self._receivers[msg_type]:
            self._receivers[msg_type].remove(callback)
            logger.debug(f"已注销 {msg_type} 接收器")

    #  发送接口（供DTO层调用）
    async def send_binary(self, data: bytes):
        """发送二进制数据（唯一客户端）"""
        if self._websocket:
            await self._websocket.send(data)
            logger.trace(f"二进制数据已发送 (长度: {len(data)} bytes)")
        else:
            raise RuntimeError("客户端未连接")

    async def send_text(self, data: str):
        """发送文本数据（唯一客户端）"""
        if self._websocket:
            await self._websocket.send(data)
            logger.trace(f"文本数据已发送 (长度: {len(data)} chars)")
        else:
            raise RuntimeError("客户端未连接")

    async def send_json(self, data: Dict[str, Any]):
        """发送JSON数据（唯一客户端）"""
        if self._websocket:
            try:
                logger.debug(f"准备发送JSON数据: {data}")
                message = json.dumps(data)
                await self._websocket.send(message)
                logger.trace(f"JSON数据已发送: {data}")
            except Exception as e:
                logger.error(f"JSON数据发送失败: {e}")
                raise
        else:
            raise RuntimeError("客户端未连接")

    # 等待连接
    async def wait_for_client(self):
        """阻塞等待客户端连接"""
        await self._connected_event.wait()
        logger.info("客户端已就绪")

    # 内部消息循环
    async def _handle_client(self, websocket: ServerConnection):
        """处理唯一客户端的消息循环"""
        self._websocket = websocket
        self._connected_event.set()
        client_info = f"{websocket.remote_address}" if hasattr(websocket, 'remote_address') else "unknown"
        logger.info(f"客户端已连接: {client_info}")

        try:
            async for message in websocket:
                # 根据消息类型分发到所有注册的接收函数
                if isinstance(message, bytes):
                    await self._dispatch('binary', message)

                elif isinstance(message, str):
                    # 优先尝试JSON解析
                    json_dispatched = False
                    try:
                        data = json.loads(message)
                        await self._dispatch('json', data)
                        json_dispatched = True
                    except json.JSONDecodeError:
                        pass

                    # 如果不是JSON或没有json接收器，尝试text
                    if not json_dispatched:
                        await self._dispatch('text', message)

                else:
                    logger.warning(f"未知消息类型: {type(message)}")
            logger.info("客户端连接已正常关闭")
        except ConnectionClosed as e:
            logger.info(f"客户端连接已关闭: {e}")
        except Exception as e:
            logger.error(f"处理客户端时发生错误: {e}")
        finally:
            self._websocket = None
            self._connected_event.clear()

    async def _dispatch(self, msg_type: str, data: Any):
        """分发消息到所有注册的接收函数"""
        callbacks = self._receivers[msg_type]
        if not callbacks:
            logger.warning(f"无 {msg_type} 接收器，消息被忽略")
            return

        # 并发执行所有回调
        tasks = [callback(data) for callback in callbacks]
        await asyncio.gather(*tasks, return_exceptions=True)

    # 启动服务器
    async def run(self, host: str = "localhost", port: int = 8765, max_msg_size: int = 50*1024*1025):
        """启动WebSocket服务器（阻塞）"""
        logger.info(f"WebSocket服务器启动中... 等待客户端连接 ws://{host}:{port}")

        async def handler_wrapper(connection):
            logger.info(f"新连接请求: {connection.remote_address}")
            await self._handle_client(connection)

        try:
            async with serve(
                    handler=handler_wrapper,  # 使用 wrapper 适配签名
                    host=host,
                    port=port,
                    max_size=max_msg_size,
            ):
                logger.success(f"WebSocket服务器已启动在 ws://{host}:{port}")
                await asyncio.Future()  # 永久阻塞，保持服务器运行
        except Exception as e:
            logger.error(f"WebSocket服务器启动失败: {e}")
            raise


async def get_ws_server() -> WebSocketServer:
    """全局单例获取函数(线程安全)"""
    server = WebSocketServer()  # __new__ 保证单例
    return server