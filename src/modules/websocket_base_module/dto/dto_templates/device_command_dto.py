"""
设备命令 DTO - 服务端向客户端发送嵌入式设备控制指令
"""

from pydantic import Field, BaseModel
from datetime import datetime, timezone


class DeviceCommandDataTransferObject(BaseModel):
    """设备命令数据传输对象"""
    device_id: str = Field(default="", description="目标设备ID")
    payload: str = Field(default="", description="JSON-RPC 调用字符串")

    def to_json(self) -> dict:
        return {
            "type": "device_command",
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "data": self.model_dump()
        }
