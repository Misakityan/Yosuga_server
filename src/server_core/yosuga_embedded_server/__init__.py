"""
Yosuga 服务端 - 面向AI的嵌入式设备JSON-RPC框架。

管理多个嵌入式设备，每个设备暴露AI可调用的函数。
服务端维护全局函数注册表、生成描述可用能力的AI提示词，
并在AI和设备之间路由JSON-RPC调用。
"""

from .device_manager import DeviceManager, DeviceInfo, DeviceState
from .function_registry import FunctionRegistry, FunctionInfo, ParamInfo, FuncType
from .ai_prompt import AIPromptBuilder
from .json_rpc import JSONRPCHandler, RPCRequest, RPCResponse, RPCError
from .server import YosugaServer, ServerConfig
from .device_dto import DeviceDataDTO

__version__ = "0.1.0"
