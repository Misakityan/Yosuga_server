"""
YosugaServer - 主服务端类，串联所有组件。

架构:
  AI <-> YosugaServer <-> DeviceManager <-> 嵌入式设备
                           FunctionRegistry
                           AIPromptBuilder
                           JSONRPCHandler

流程:
  1. 设备连接，发送能力描述JSON
  2. 服务端注册设备+函数
  3. 变更回调触发 -> 服务端更新AI提示词
  4. 用户通过服务端向AI发送请求
  5. 服务端用当前函数构建系统提示词
  6. AI响应函数调用
  7. 服务端解析调用并路由到设备
  8. 设备响应被收集并返回
"""

import json
import logging
import threading
from typing import Optional, Callable, Any

from .device_manager import DeviceManager, DeviceInfo
from .function_registry import FunctionRegistry
from .ai_prompt import AIPromptBuilder
from .json_rpc import JSONRPCHandler, RPCRequest, RPCResponse, RPCError

logger = logging.getLogger(__name__)


class ServerConfig:
    """服务端配置。"""

    def __init__(
        self,
        device_conflict_strategy: str = "rename",
        max_concurrent_calls: int = 10,
        device_timeout: float = 30.0,
    ):
        self.device_conflict_strategy = device_conflict_strategy
        self.max_concurrent_calls = max_concurrent_calls
        self.device_timeout = device_timeout


class YosugaServer:
    """主服务端，协调设备、函数和AI交互。"""

    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig()
        self.device_manager = DeviceManager(
            conflict_strategy=self.config.device_conflict_strategy
        )
        self.function_registry = FunctionRegistry()
        self.ai_prompt = AIPromptBuilder()
        self._lock = threading.Lock()
        self._call_id_counter = 0

        # 挂载变更通知
        self.device_manager.on_device_change = self._on_device_change
        self.function_registry.on_change = self._on_functions_change

        # 外部集成回调
        self.on_capabilities_changed: Optional[Callable[[dict], Any]] = None
        self.on_device_message: Optional[Callable[[str, str], Optional[str]]] = None

    def _on_device_change(self, event: str, device: DeviceInfo):
        logger.info("Device %s: %s", event, device.device_id)
        if event == "removed":
            self.function_registry.remove_device_functions(device.device_id)
        elif event in ("added", "updated"):
            if device.state.value == "registered":
                self.function_registry.add_device_functions(
                    device.device_id,
                    device.name,
                    device.functions or [],
                )

    def _on_functions_change(self):
        if self.on_capabilities_changed:
            try:
                self.on_capabilities_changed(self.get_capabilities_summary())
            except Exception as e:
                logger.error("capabilities callback error: %s", e)

    def _next_call_id(self) -> int:
        with self._lock:
            self._call_id_counter += 1
            return self._call_id_counter

    def register_device(self, device_json_str: str) -> DeviceInfo:
        """从设备的JSON能力描述注册设备。

        Args:
            device_json_str: 设备发来的JSON字符串

        Returns:
            已注册设备的 DeviceInfo
        """
        data = json.loads(device_json_str)
        return self.device_manager.register_from_json(data)

    def register_device_from_dict(self, device_json: dict, device_id: str = "") -> DeviceInfo:
        """从字典注册设备（格式同JSON）。
        Args:
            device_json: 设备能力描述字典
            device_id: 可选的显式设备 ID（来自客户端转发，覆盖自动生成）
        """
        if device_id:
            device_json = dict(device_json)
            device_json["_device_id"] = device_id
        return self.device_manager.register_from_json(device_json)

    def remove_device(self, device_id: str) -> bool:
        """移除设备及其函数。"""
        return self.device_manager.remove_device(device_id)

    def build_ai_system_prompt(self) -> str:
        """构建当前AI系统提示词。"""
        functions = self.function_registry.to_function_list()
        return self.ai_prompt.build_system_prompt(functions)

    def process_ai_response(self, response_text: str) -> list[dict]:
        """解析AI响应为RPC调用并路由到设备。

        Args:
            response_text: AI返回的原始文本

        Returns:
            包含设备响应结果的字典列表
        """
        calls = self.ai_prompt.parse_ai_response(response_text)
        if not calls:
            return [{"error": "无法将AI响应解析为RPC调用"}]

        results = []
        for call in calls:
            method = call.get("method")
            params = call.get("params", {})
            call_id = call.get("id", self._next_call_id())

            # 查找哪个设备提供此函数
            func_info = self.function_registry.get_function(method)
            if not func_info:
                results.append({
                    "id": call_id,
                    "method": method,
                    "error": {"code": RPCError.METHOD_NOT_FOUND,
                              "message": f"未找到函数 '{method}'"},
                })
                continue

            device_id = func_info.device_id
            device = self.device_manager.get_device(device_id)
            if not device:
                results.append({
                    "id": call_id,
                    "method": method,
                    "error": {"code": RPCError.DEVICE_NOT_FOUND,
                              "message": f"设备 '{device_id}' 不可用"},
                })
                continue

            # 构建发送给设备的RPC调用
            rpc_call = JSONRPCHandler.build_call(method, params, call_id)

            # 如果有设备消息回调，使用它
            if self.on_device_message:
                try:
                    response_str = self.on_device_message(device_id, rpc_call)
                    if response_str:
                        resp = JSONRPCHandler.parse_response(response_str)
                        if resp:
                            if resp.is_success():
                                results.append({
                                    "id": call_id,
                                    "method": method,
                                    "device_id": device_id,
                                    "result": resp.result,
                                })
                            else:
                                results.append({
                                    "id": call_id,
                                    "method": method,
                                    "device_id": device_id,
                                    "error": resp.error.to_dict(),
                                })
                        else:
                            results.append({
                                "id": call_id,
                                "method": method,
                                "error": {"code": RPCError.PARSE_ERROR,
                                          "message": "Invalid response from device"},
                            })
                    else:
                        results.append({
                            "id": call_id,
                            "method": method,
                            "device_id": device_id,
                            "result": None,
                            "note": "notification (no response expected)",
                        })
                except Exception as e:
                    results.append({
                        "id": call_id,
                        "method": method,
                        "error": {"code": RPCError.DEVICE_ERROR,
                                  "message": str(e)},
                    })
            else:
                results.append({
                    "id": call_id,
                    "method": method,
                    "device_id": device_id,
                    "note": "No on_device_message callback set - call would be routed here",
                })

        return results

    def list_devices(self) -> list[dict]:
        """获取所有在线设备的字典列表"""
        return [d.to_dict() for d in self.device_manager.get_all_devices()]

    def send_rpc(self, device_id: str, rpc_call: str) -> Optional[str]:
        """向指定设备发送 RPC 调用并返回响应"""
        if self.on_device_message:
            return self.on_device_message(device_id, rpc_call)
        return None

    def get_capabilities_summary(self) -> dict:
        """获取所有能力的摘要（供外部使用）。"""
        return {
            "device_count": self.device_manager.device_count(),
            "function_count": self.function_registry.function_count(),
            "devices": self.device_manager.to_dict(),
            "functions": self.function_registry.to_function_list(),
        }

    def process_device_message(self, device_id: str, message: str) -> str:
        """处理设备发来的消息。

        设备发送:
        - 能力描述（注册）
        - RPC响应

        如有需要返回响应字符串。
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return JSONRPCHandler.build_error_response(
                RPCError.PARSE_ERROR, "Invalid JSON"
            )

        # 检查是否为能力描述（包含"device"和"functions"）
        if isinstance(data, dict) and "device" in data and "functions" in data:
            device = self.register_device_from_dict(data)
            return json.dumps({"status": "registered", "device_id": device.device_id})

        # 检查是否为RPC响应
        if isinstance(data, dict) and ("result" in data or "error" in data):
            # 仅确认 - 响应由回调处理
            return json.dumps({"status": "received"})

        # 可能是转发调用或其他消息
        return JSONRPCHandler.build_error_response(
            RPCError.INVALID_REQUEST, "Unknown message type"
        )
