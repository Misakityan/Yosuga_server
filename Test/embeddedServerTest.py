
import socket
import struct
import threading
import json
import os
from typing import Optional

from openai import OpenAI  # 确保 pip install openai

from src.server_core.yosuga_embedded_server.device_manager import DeviceManager, DeviceInfo
from src.server_core.yosuga_embedded_server.function_registry import FunctionRegistry
from src.server_core.yosuga_embedded_server.ai_prompt import AIPromptBuilder
from src.server_core.yosuga_embedded_server.json_rpc import JSONRPCHandler, RPCError


class DeviceConnection:
    """管理一个 TCP 设备连接"""
    def __init__(self, sock, addr, server):
        self.sock = sock
        self.addr = addr
        self.server = server
        self.device_id: Optional[str] = None

    def send_msg(self, data: str):
        """发送带长度前缀的消息"""
        encoded = data.encode('utf-8')
        self.sock.sendall(struct.pack('!I', len(encoded)))
        self.sock.sendall(encoded)

    def recv_msg(self) -> Optional[str]:
        try:
            # 读满 4 字节长度前缀
            raw_len = b''
            while len(raw_len) < 4:
                chunk = self.sock.recv(4 - len(raw_len))
                if not chunk:  # 对方关闭连接
                    return None
                raw_len += chunk
            msg_len = struct.unpack('!I', raw_len)[0]

            # 读消息体
            data = b''
            while len(data) < msg_len:
                chunk = self.sock.recv(msg_len - len(data))
                if not chunk:
                    return None
                data += chunk
            return data.decode('utf-8')
        except Exception as e:
            print(f"recv error: {e}")
            return None

    def handle(self):
        try:
            # 只接收第一条能力广告
            caps_str = self.recv_msg()
            if not caps_str:
                return
            print(f"[{self.addr}] Capabilities received")
            device = self.server.register_device(caps_str)
            self.device_id = device.device_id
            self.server.set_connection(device.device_id, self)
            print(f"[{self.addr}] Registered as {device.name} (id={device.device_id})")

            # 此处直接返回，线程结束。后续通信由 call_device 接管。
        except Exception as e:
            print(f"Registration error: {e}")
        finally:
            # 注意：不要关闭 socket！它还要用于后续 call_device
            pass


class YosugaServer:
    """整合设备管理、函数注册、AI 交互的服务端"""
    def __init__(self, deepseek_api_key: str):
        self.device_manager = DeviceManager()
        self.function_registry = FunctionRegistry()
        self.ai_prompt = AIPromptBuilder()
        self._lock = threading.Lock()
        self._call_id_counter = 0

        # 关联设备变更
        self.device_manager.on_device_change = self._on_device_change
        self.function_registry.on_change = self._on_functions_change

        # DeepSeek 客户端
        self.ai_client = OpenAI(
            api_key=deepseek_api_key,
            base_url="https://api.deepseek.com"
        )

        # 设备连接表：device_id -> DeviceConnection
        self._connections: dict[str, DeviceConnection] = {}

    def _on_device_change(self, event: str, device: DeviceInfo):
        print(f"Device event: {event} {device.device_id}")
        if event == "removed":
            self.function_registry.remove_device_functions(device.device_id)
            conn = self._connections.pop(device.device_id, None)
            if conn and conn.sock:
                try:
                    conn.sock.close()
                except Exception:
                    pass
        elif event in ("added", "updated"):
            if device.state.value == "registered":
                self.function_registry.add_device_functions(
                    device.device_id,
                    device.name,
                    device.functions or [],
                )

    def _on_functions_change(self):
        print(f"Functions updated, total: {self.function_registry.function_count()}")

    def register_device(self, caps_json: str) -> DeviceInfo:
        data = json.loads(caps_json)
        return self.device_manager.register_from_json(data)

    def remove_device(self, device_id: str):
        self.device_manager.remove_device(device_id)

    def set_connection(self, device_id: str, conn: DeviceConnection):
        with self._lock:
            self._connections[device_id] = conn

    def call_device(self, device_id: str, method: str, params: dict, call_id: int) -> dict:
        conn = self._connections.get(device_id)
        if not conn:
            return {"error": {"code": RPCError.DEVICE_NOT_FOUND,
                              "message": f"Device {device_id} not connected"}}

        req = JSONRPCHandler.build_call(method, params, call_id)
        try:
            conn.send_msg(req)
            resp_str = conn.recv_msg_with_timeout(timeout=5.0)
            if resp_str is None:
                # 超时或连接断开
                self.remove_device(device_id)  # 自动清理
                return {"error": {"code": RPCError.TIMEOUT, "message": "Device timeout or disconnected"}}

            resp = JSONRPCHandler.parse_response(resp_str)
            if resp and resp.is_success():
                return {"result": resp.result}
            elif resp and resp.error:
                return {"error": resp.error.to_dict()}
            else:
                return {"error": {"code": RPCError.PARSE_ERROR, "message": "Invalid response"}}
        except Exception as e:
            self.remove_device(device_id)
            return {"error": {"code": RPCError.DEVICE_ERROR, "message": str(e)}}

    def process_device_message(self, device_id: str, message: str) -> str:
        """处理从设备主动发来的消息（如 RPC 响应）"""
        # 在这个架构中，设备不会主动发消息，所有交互都由服务端发起
        # 这里仅作为占位，返回空
        return ""

    def handle_user_request(self, user_input: str) -> str:
        """处理用户自然语言请求：调用 AI，执行函数，返回最终答案"""
        # 1. 构建系统提示（包含当前所有函数）
        func_list = self.function_registry.to_function_list()
        system_prompt = self.ai_prompt.build_system_prompt(func_list)

        # 2. 调用 DeepSeek
        print("Calling DeepSeek...")
        try:
            response = self.ai_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.0,  # 确保输出稳定
            )
            ai_text = response.choices[0].message.content.strip()
            print(f"AI response:\n{ai_text}")
        except Exception as e:
            return f"AI error: {e}"

        # 3. 解析 AI 返回的调用
        calls = self.ai_prompt.parse_ai_response(ai_text)
        if not calls:
            return "Failed to parse AI response as JSON-RPC calls"

        # 4. 逐个执行调用
        results = []
        for idx, call in enumerate(calls):
            method = call.get("method")
            params = call.get("params", {})
            call_id = idx + 1  # 简单自增 ID

            # 找到该函数所属设备
            func_info = self.function_registry.get_function(method)
            if not func_info:
                results.append(f"❌ Unknown function: {method}")
                continue

            device_id = func_info.device_id
            print(f"Routing '{method}' to device {device_id}")

            # 发送给设备
            dev_resp = self.call_device(device_id, method, params, call_id)
            if "error" in dev_resp:
                results.append(f"❌ {method}: {dev_resp['error']['message']}")
            else:
                results.append(f"✅ {method}: {dev_resp.get('result', 'ok')}")

        # 5. 汇总结果返回
        summary = "\n".join(results)
        print(f"Task result:\n{summary}")
        return summary


# ========== 修改 DeviceConnection 的 recv_msg 支持超时 ==========

def recv_msg_with_timeout(self, timeout: float = 5.0) -> Optional[str]:
    """接收带长度前缀的消息，带超时"""
    self.sock.settimeout(timeout)
    try:
        return self.recv_msg()
    except socket.timeout:
        return None
    finally:
        self.sock.settimeout(None)

DeviceConnection.recv_msg_with_timeout = recv_msg_with_timeout  # monkey-patch


# ========== 主函数 ==========
def main():


    server = YosugaServer("")

    # 启动 TCP 监听，接收设备连接
    def accept_connections():
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('0.0.0.0', 9555))
        listener.listen(5)
        print("Server listening on port 9555...")
        while True:
            sock, addr = listener.accept()
            print(f"New connection from {addr}")
            conn = DeviceConnection(sock, addr, server)
            # 在连接注册后，关联 device_id 需要等到能力广告，暂存一下
            # 我们在 handle 中收到能力后再设置 server.set_connection
            threading.Thread(target=conn.handle, daemon=True).start()

    threading.Thread(target=accept_connections, daemon=True).start()

    # 简单交互循环
    print("\nEnter your requests (type 'quit' to exit):")
    while True:
        try:
            user_input = input("> ")
        except EOFError:
            break
        if user_input.lower() in ('quit', 'exit'):
            break
        if not user_input.strip():
            continue
        result = server.handle_user_request(user_input)
        print("---\n" + result + "\n---")

if __name__ == "__main__":
    main()