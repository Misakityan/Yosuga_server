"""
函数注册表 - 维护所有设备的全局函数表。

这是所有已连接设备的所有函数的汇总视图。
注册表在运行时动态更新：随设备连接/断开而更新。
"""

import copy
import json
import threading
from enum import Enum
from typing import Optional, Callable


class FuncType(Enum):
    CTRL_NORET = "ctrl_noret"
    CTRL_RET = "ctrl_ret"
    DATA_RET = "data_ret"
    NORET_NODATA = "noret_nodata"

    @classmethod
    def from_str(cls, s: str) -> "FuncType":
        for ft in cls:
            if ft.value == s:
                return ft
        return cls.CTRL_NORET


class ParamInfo:
    """单个函数参数的描述符"""

    def __init__(self, name: str = "", description: str = "",
                 param_type: str = "int", optional: bool = False):
        self.name = name
        self.description = description
        self.type = param_type
        self.optional = optional

    @classmethod
    def from_dict(cls, d: dict) -> "ParamInfo":
        return cls(
            name=d.get("name", ""),
            description=d.get("description", ""),
            param_type=d.get("type", "int"),
            optional=d.get("optional", False),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "optional": self.optional,
        }

    def __repr__(self) -> str:
        return f"ParamInfo({self.name}: {self.type})"


class FunctionInfo:
    """整个系统中单个函数的完整描述符。

    包含函数名、描述、参数信息、类型以及提供该函数的设备。
    """

    def __init__(
        self,
        name: str = "",
        description: str = "",
        func_type: FuncType = FuncType.CTRL_NORET,
        params: Optional[list] = None,
        device_id: str = "",
        device_name: str = "",
    ):
        self.name = name
        self.description = description
        self.func_type = func_type
        self.params = params or []
        self.device_id = device_id
        self.device_name = device_name

    @classmethod
    def from_device_func(cls, func_dict: dict, device_id: str, device_name: str) -> "FunctionInfo":
        raw_params = func_dict.get("params", [])
        params = [ParamInfo.from_dict(p) if isinstance(p, dict) else ParamInfo()
                  for p in raw_params]
        return cls(
            name=func_dict.get("name", ""),
            description=func_dict.get("description", ""),
            func_type=FuncType.from_str(func_dict.get("type", "ctrl_noret")),
            params=params,
            device_id=device_id,
            device_name=device_name,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.func_type.value,
            "params": [p.to_dict() for p in self.params],
            "device_id": self.device_id,
            "device_name": self.device_name,
        }

    def __repr__(self) -> str:
        return f"FunctionInfo({self.name} @ {self.device_name})"


class FunctionRegistry:
    """所有设备上所有函数的全局注册表。

    维护:
    - functions_by_name: dict[str, FunctionInfo] - 按名称快速查找
    - functions_by_device: dict[str, list[FunctionInfo]] - 按设备查找

    线程安全。变更时触发回调。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._functions_by_name: dict[str, FunctionInfo] = {}
        self._functions_by_device: dict[str, list[FunctionInfo]] = {}
        self._on_change: Optional[Callable] = None

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, cb: Optional[Callable]):
        self._on_change = cb

    def _notify(self):
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                pass

    def add_device_functions(self, device_id: str, device_name: str,
                             func_list: list[dict]):
        """添加或更新某个设备的所有函数。"""
        with self._lock:
            self._remove_device_functions_locked(device_id)
            func_infos = []
            for func_dict in func_list:
                fi = FunctionInfo.from_device_func(func_dict, device_id, device_name)
                func_infos.append(fi)
                self._functions_by_name[fi.name] = fi
            self._functions_by_device[device_id] = func_infos
        self._notify()

    def _remove_device_functions_locked(self, device_id: str):
        """移除设备函数，不加锁（调用者必须持有锁）。"""
        funcs = self._functions_by_device.pop(device_id, [])
        for fi in funcs:
            self._functions_by_name.pop(fi.name, None)

    def remove_device_functions(self, device_id: str):
        """移除某个设备的所有函数。"""
        with self._lock:
            self._remove_device_functions_locked(device_id)
        self._notify()

    def get_function(self, name: str) -> Optional[FunctionInfo]:
        with self._lock:
            return self._functions_by_name.get(name)

    def get_all_functions(self) -> list[FunctionInfo]:
        with self._lock:
            return list(self._functions_by_name.values())

    def get_device_functions(self, device_id: str) -> list[FunctionInfo]:
        with self._lock:
            return list(self._functions_by_device.get(device_id, []))

    def function_count(self) -> int:
        with self._lock:
            return len(self._functions_by_name)

    def to_function_list(self) -> list[dict]:
        return [fi.to_dict() for fi in self.get_all_functions()]

    def to_json(self) -> str:
        return json.dumps(self.to_function_list(), indent=2, ensure_ascii=False)

    def find_device_for_function(self, func_name: str) -> Optional[str]:
        fi = self.get_function(func_name)
        return fi.device_id if fi else None
