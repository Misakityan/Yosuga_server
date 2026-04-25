"""
设备管理器 - 管理多个嵌入式设备的连接。

每个设备由唯一ID标识（自动生成或客户端提供）。
管理器处理设备注册、重复检测，并维护设备ID与其功能表的映射。
"""

import time
import threading
from enum import Enum
from typing import Optional, Callable, Any


class DeviceState(Enum):
    """设备连接的当前状态。"""
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    REGISTERED = "registered"


class DeviceInfo:
    """嵌入式设备的信息。

    存储设备的能力、身份和连接元数据。
    除 device_id 外，所有字段均由设备自身提供。
    """

    def __init__(
        self,
        device_id: str,
        name: str = "",
        description: str = "",
        firmware_version: str = "",
        hardware_version: str = "",
        functions: Optional[list] = None,
    ):
        self.device_id = device_id
        self.name = name
        self.description = description
        self.firmware_version = firmware_version
        self.hardware_version = hardware_version
        self.functions = functions or []
        self.state = DeviceState.DISCONNECTED
        self.last_seen: float = 0.0
        self.connected_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "description": self.description,
            "firmware_version": self.firmware_version,
            "hardware_version": self.hardware_version,
            "state": self.state.value,
            "last_seen": self.last_seen,
            "connected_at": self.connected_at,
            "register_time": self.connected_at,
            "functions": self.functions,
            "function_count": len(self.functions),
        }

    def __repr__(self) -> str:
        return f"DeviceInfo({self.device_id}, {self.name}, state={self.state.value})"


class DeviceManager:
    """管理所有连接到服务端的嵌入式设备。

    功能:
    - 未提供时自动生成设备ID
    - 可配置策略处理重复设备名
    - 跟踪连接状态和最后活跃时间戳
    - 提供设备状态变更的回调
    """

    class ConflictStrategy(Enum):
        """处理重复设备名的策略。"""
        REJECT = "reject"
        RENAME = "rename"
        REPLACE = "replace"

    def __init__(self, conflict_strategy: str = "rename"):
        self._devices: dict[str, "DeviceInfo"] = {}
        self._lock = threading.Lock()
        self._next_id = 1
        self._conflict_strategy = DeviceManager.ConflictStrategy(conflict_strategy)
        self._on_device_change: Optional[Callable[[str, "DeviceInfo"], Any]] = None

    @property
    def on_device_change(self) -> Optional[Callable[[str, "DeviceInfo"], Any]]:
        """设备添加、更新或移除时的回调。
        签名: callback(event_type: str, device: DeviceInfo)
        event_type: 'added', 'updated', 'removed'
        """
        return self._on_device_change

    @on_device_change.setter
    def on_device_change(self, cb: Optional[Callable[[str, "DeviceInfo"], Any]]):
        self._on_device_change = cb

    def _notify(self, event: str, device: "DeviceInfo"):
        if self._on_device_change:
            try:
                self._on_device_change(event, device)
            except Exception:
                pass

    def _generate_id(self) -> str:
        """生成唯一的设备ID。"""
        while True:
            dev_id = f"device_{self._next_id}"
            self._next_id += 1
            if dev_id not in self._devices:
                return dev_id

    def register_from_json(self, json_data: dict) -> "DeviceInfo":
        """从设备的能力描述JSON注册或更新设备。

        期望的JSON格式:
        {
            "_device_id": "...",     # 可选的显式设备 ID（来自客户端转发）
            "device": {
                "name": "...",
                "description": "...",
                "firmware_version": "...",
                "hardware_version": "..."
            },
            "functions": [ ... ]
        }

        返回 DeviceInfo 对象。
        策略为 REJECT 时，发生冲突会抛出 ValueError。
        """
        device_data = json_data.get("device", {})
        name = device_data.get("name", "")
        description = device_data.get("description", "")

        with self._lock:
            explicit_id = json_data.get("_device_id", "")
            device_id = explicit_id if explicit_id else self._resolve_identity(name)
            device = DeviceInfo(
                device_id=device_id,
                name=name,
                description=description,
                firmware_version=device_data.get("firmware_version", ""),
                hardware_version=device_data.get("hardware_version", ""),
                functions=json_data.get("functions", []),
            )
            device.state = DeviceState.REGISTERED
            now = time.time()
            device.last_seen = now
            device.connected_at = now

            existing = self._find_by_name(name)
            is_new = device_id not in self._devices

            if existing and existing.device_id != device_id:
                if self._conflict_strategy == DeviceManager.ConflictStrategy.REJECT:
                    raise ValueError(f"Device name conflict: '{name}' already registered")
            elif existing and existing.device_id == device_id:
                is_new = False

            self._devices[device_id] = device
            is_new_flag = is_new
            device_ref = device

        self._notify("added" if is_new_flag else "updated", device_ref)
        return device_ref

    def _resolve_identity(self, name: str) -> str:
        """将设备名解析为唯一的设备ID。"""
        existing = self._find_by_name(name)
        if existing:
            if self._conflict_strategy == DeviceManager.ConflictStrategy.RENAME:
                return self._generate_id()
            elif self._conflict_strategy == DeviceManager.ConflictStrategy.REJECT:
                raise ValueError(f"Device name conflict: '{name}' already registered")
            elif self._conflict_strategy == DeviceManager.ConflictStrategy.REPLACE:
                return existing.device_id
        return self._generate_id()

    def _find_by_name(self, name: str) -> Optional["DeviceInfo"]:
        for dev in self._devices.values():
            if dev.name == name:
                return dev
        return None

    def get_device(self, device_id: str) -> Optional["DeviceInfo"]:
        with self._lock:
            return self._devices.get(device_id)

    def get_device_by_name(self, name: str) -> Optional["DeviceInfo"]:
        return self._find_by_name(name)

    def remove_device(self, device_id: str) -> bool:
        with self._lock:
            device = self._devices.pop(device_id, None)
            if device:
                device.state = DeviceState.DISCONNECTED
                self._notify("removed", device)
                return True
            return False

    def get_all_devices(self) -> list["DeviceInfo"]:
        with self._lock:
            return list(self._devices.values())

    def device_count(self) -> int:
        with self._lock:
            return len(self._devices)

    def touch_device(self, device_id: str):
        with self._lock:
            device = self._devices.get(device_id)
            if device:
                device.last_seen = time.time()

    def to_dict(self) -> dict:
        return {
            "devices": [d.to_dict() for d in self.get_all_devices()],
            "count": self.device_count(),
        }

    def get_device_for_function(self, function_name: str) -> Optional[str]:
        """Find which device provides a specific function name.
        Returns device_id or None if not found.
        """
        with self._lock:
            for dev_id, dev in self._devices.items():
                for func in dev.functions:
                    if func.get("name") == function_name:
                        return dev_id
            return None
