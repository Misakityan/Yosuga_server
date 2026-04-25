"""
JSON-RPC 2.0 协议处理器。

处理AI、服务端和嵌入式设备之间JSON-RPC消息的
解析、验证、构建和路由
"""

import json
from typing import Optional


class RPCError(Exception):
    """JSON-RPC错误，包含标准错误码"""

    # 标准 JSON-RPC 错误码
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # 自定义错误码
    DEVICE_NOT_FOUND = -32000
    DEVICE_ERROR = -32001
    TIMEOUT = -32002

    def __init__(self, code: int, message: str, data: Optional[dict] = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"[{code}] {message}")

    def to_dict(self) -> dict:
        err = {"code": self.code, "message": self.message}
        if self.data:
            err["data"] = self.data
        return err


class RPCRequest:
    """表示一个JSON-RPC 2.0请求"""

    def __init__(self, method: str, params: Optional[dict] = None,
                 request_id: Optional[int] = None):
        self.method = method
        self.params = params or {}
        self.id = request_id

    def is_notification(self) -> bool:
        return self.id is None

    def to_dict(self) -> dict:
        req = {
            "jsonrpc": "2.0",
            "method": self.method,
        }
        if self.params:
            req["params"] = self.params
        if self.id is not None:
            req["id"] = self.id
        return req

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "RPCRequest":
        return cls(
            method=d["method"],
            params=d.get("params"),
            request_id=d.get("id"),
        )

    def __repr__(self) -> str:
        return f"RPCRequest(method={self.method}, id={self.id})"


class RPCResponse:
    """表示一个JSON-RPC 2.0响应"""

    def __init__(self, result: Optional[dict] = None,
                 error: Optional[RPCError] = None,
                 request_id: Optional[int] = None):
        self.result = result
        self.error = error
        self.id = request_id

    def is_success(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict:
        resp = {"jsonrpc": "2.0"}
        if self.id is not None:
            resp["id"] = self.id
        if self.error:
            resp["error"] = self.error.to_dict()
        else:
            resp["result"] = self.result
        return resp

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def success(cls, result: Optional[dict], request_id: Optional[int]) -> "RPCResponse":
        return cls(result=result, request_id=request_id)

    @classmethod
    def error(cls, code: int, message: str, request_id: Optional[int] = None) -> "RPCResponse":
        return cls(error=RPCError(code, message), request_id=request_id)

    def __repr__(self) -> str:
        if self.error:
            return f"RPCResponse(error={self.error.message}, id={self.id})"
        return f"RPCResponse(result={self.result}, id={self.id})"


class JSONRPCHandler:
    """处理JSON-RPC协议解析和响应构建"""

    @staticmethod
    def parse_request(json_str: str) -> Optional[RPCRequest]:
        """将JSON字符串解析为RPCRequest"""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None
        if data.get("jsonrpc") != "2.0":
            return None
        if "method" not in data or not isinstance(data["method"], str):
            return None

        return RPCRequest.from_dict(data)

    @staticmethod
    def parse_request_batch(json_str: str) -> Optional[list[RPCRequest]]:
        """将JSON字符串解析为RPCRequest列表（用于批量调用）"""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        if isinstance(data, dict):
            req = JSONRPCHandler.parse_request(json_str)
            return [req] if req else None

        if isinstance(data, list):
            results = []
            for item in data:
                item_str = json.dumps(item)
                req = JSONRPCHandler.parse_request(item_str)
                if req:
                    results.append(req)
            return results if results else None

        return None

    @staticmethod
    def validate_request(request: dict) -> Optional[RPCError]:
        """验证原始请求字典。无效时返回RPCError"""
        if not isinstance(request, dict):
            return RPCError(RPCError.INVALID_REQUEST, "request must be a JSON object")
        if request.get("jsonrpc") != "2.0":
            return RPCError(RPCError.INVALID_REQUEST, "jsonrpc must be '2.0'")
        if "method" not in request:
            return RPCError(RPCError.INVALID_REQUEST, "missing method")
        if not isinstance(request["method"], str) or not request["method"]:
            return RPCError(RPCError.INVALID_REQUEST, "method must be a non-empty string")
        params = request.get("params")
        if params is not None and not isinstance(params, dict):
            return RPCError(RPCError.INVALID_PARAMS, "params must be a JSON object")
        return None

    @staticmethod
    def build_error_response(code: int, message: str,
                             request_id: Optional[int] = None) -> str:
        """构建JSON-RPC错误响应字符串"""
        resp = RPCResponse.error(code, message, request_id)
        return resp.to_json()

    @staticmethod
    def build_success_response(result: Optional[dict],
                               request_id: Optional[int] = None) -> str:
        """构建JSON-RPC成功响应字符串"""
        resp = RPCResponse.success(result, request_id)
        return resp.to_json()

    @staticmethod
    def build_call(method: str, params: Optional[dict] = None,
                   call_id: Optional[int] = None) -> str:
        """构建JSON-RPC调用字符串（服务端 -> 设备）"""
        req = RPCRequest(method, params, call_id)
        return req.to_json()

    @staticmethod
    def is_response(json_str: str) -> bool:
        """检查JSON字符串是否为JSON-RPC响应"""
        try:
            data = json.loads(json_str)
            if isinstance(data, dict):
                return "result" in data or "error" in data
            return False
        except json.JSONDecodeError:
            return False

    @staticmethod
    def parse_response(json_str: str) -> Optional[RPCResponse]:
        """将JSON字符串解析为RPCResponse"""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None
        if data.get("jsonrpc") != "2.0":
            return None

        request_id = data.get("id")
        if "error" in data:
            err_data = data["error"]
            return RPCResponse.error(
                err_data.get("code", RPCError.INTERNAL_ERROR),
                err_data.get("message", "unknown error"),
                request_id,
            )
        elif "result" in data:
            return RPCResponse.success(data["result"], request_id)
        return None
