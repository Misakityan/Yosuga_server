"""
设备数据 DTO - 处理客户端发来的嵌入式设备数据
通过 WebSocket 的 device_data 类型消息与客户端通信
"""

import json
import time
from typing import Callable, Optional, Coroutine
from loguru import logger


class DeviceDataDTO:
    """设备数据分发器，处理客户端发来的设备注册/响应/事件"""

    def __init__(self, json_dto, embedded_server):
        """
        Args:
            json_dto: JsonDTO 实例，用于注册接收器
            embedded_server: YosugaServer 实例（嵌入式框架）
        """
        json_dto.register_receiver("device_data", self._handle_device_data)
        logger.info("[DeviceDataDTO] 设备数据接收业务已注册")
        self.json_dto = json_dto
        self.embedded_server = embedded_server
        self._device_callbacks: list[Callable] = []
        self.on_rpc_response: Optional[Callable[[str, dict], Coroutine]] = None

    async def _handle_device_data(self, data: dict):
        """处理设备数据的入口

        客户端发来的 device_data JSON 格式:
        {
            "action": "register" | "rpc_response" | "event",
            "device_id": "...",
            "payload": { ... }         # 根据 action 不同而不同
        }
        """
        action = data.get("action", "")
        logger.info(f"[DeviceDataDTO] 收到设备数据, action={action}")

        if action == "register":
            device_id = data.get("device_id", "")
            await self._handle_register(data.get("payload", {}), device_id)
        elif action == "rpc_response":
            await self._handle_rpc_response(
                data.get("device_id", ""),
                data.get("payload", {})
            )
        elif action == "event":
            await self._handle_device_event(
                data.get("device_id", ""),
                data.get("payload", {})
            )
        else:
            logger.warning(f"[DeviceDataDTO] 未知的 action: {action}")

    async def _handle_register(self, payload: dict, device_id: str = ""):
        """处理设备注册

        payload 格式同 YosugaServer 的设备能力描述:
        {
            "device": { "name": "...", "description": "..." },
            "functions": [ { "name": "...", "type": "...", ... } ]
        }
        """
        try:
            device = self.embedded_server.register_device_from_dict(payload, device_id)
            logger.success(f"[DeviceDataDTO] 设备注册成功: {device.name} ({device.device_id})")
        except Exception as e:
            logger.error(f"[DeviceDataDTO] 设备注册失败: {e}")

    async def _handle_rpc_response(self, device_id: str, payload: dict):
        """处理设备返回的 RPC 响应"""
        logger.info(f"[DeviceDataDTO] 收到设备 {device_id} 的 RPC 响应: {payload}")

        if self.on_rpc_response:
            try:
                await self.on_rpc_response(device_id, payload)
            except Exception as e:
                logger.error(f"[DeviceDataDTO] on_rpc_response 回调错误: {e}")

        for cb in self._device_callbacks:
            try:
                cb(device_id, payload)
            except Exception as e:
                logger.error(f"[DeviceDataDTO] 回调执行错误: {e}")

    async def _handle_device_event(self, device_id: str, payload: dict):
        """处理设备主动上报的事件"""
        logger.info(f"[DeviceDataDTO] 收到设备 {device_id} 的事件: {payload}")

    def register_device_callback(self, callback: Callable) -> None:
        """注册设备消息回调"""
        self._device_callbacks.append(callback)

    async def send_device_command(self, device_id: str, rpc_call: str) -> None:
        """向客户端发送设备控制命令

        发送给客户端的 JSON 格式:
        {
            "type": "device_command",
            "data": {
                "device_id": "...",
                "payload": "{\\"jsonrpc\\": \\"2.0\\", ...}"
            }
        }
        """
        payload = {
            "device_id": device_id,
            "payload": rpc_call
        }
        await self.json_dto.send_json({
            "type": "device_command",
            "timestamp": time.time(),
            "data": payload
        })
        logger.info(f"[DeviceDataDTO] 已发送设备命令到 {device_id}")
