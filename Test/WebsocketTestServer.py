"""
极简 WebSocket 测试服务器 - 修复版本
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Set

import websockets

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

class SimpleWebSocketServer:
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.clients: Set = set()
        
    async def handle_connection(self, websocket, path):
        """处理客户端连接"""
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        self.clients.add(websocket)
        logging.info(f"✅ 客户端连接: {client_id} (当前连接数: {len(self.clients)})")
        
        try:
            # 发送欢迎消息
            welcome = {
                "type": "connect",
                "data": {
                    "message": "WebSocket 服务器连接成功",
                    "client_id": client_id,
                    "server_time": datetime.now().isoformat(),
                    "status": "connected"
                },
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            await websocket.send(json.dumps(welcome))
            
            async for message in websocket:
                await self.handle_message(websocket, client_id, message)
                
        except websockets.exceptions.ConnectionClosed:
            logging.info(f"❌ 客户端断开: {client_id}")
        finally:
            self.clients.discard(websocket)
            logging.info(f"📊 剩余连接: {len(self.clients)}")
    
    async def handle_message(self, websocket, client_id, message):
        """处理收到的消息"""
        logging.info(f"📨 收到消息 from {client_id}: {message}")
        
        try:
            # 尝试解析为 JSON
            data = json.loads(message)
            msg_type = data.get("type", "unknown")
            
            # 根据消息类型回复
            if msg_type == "ping":
                # 心跳响应
                response = {
                    "type": "pong",
                    "data": {
                        "server_time": datetime.now().isoformat(),
                        "latency": "0ms"
                    },
                    "timestamp": int(datetime.now().timestamp() * 1000)
                }
                
            elif msg_type == "login":
                # 登录响应
                username = data.get("data", {}).get("username", "anonymous")
                response = {
                    "type": "login_success",
                    "data": {
                        "user_id": f"user_{abs(hash(username)) % 10000}",
                        "username": username,
                        "status": "authenticated"
                    },
                    "timestamp": int(datetime.now().timestamp() * 1000)
                }
                
            elif msg_type == "chat":
                # 聊天消息回应
                msg_content = data.get("data", {}).get("message", "")
                response = {
                    "type": "chat_response",
                    "data": {
                        "message": f"服务器收到: {msg_content}",
                        "sender": "server",
                        "received_at": datetime.now().isoformat()
                    },
                    "timestamp": int(datetime.now().timestamp() * 1000)
                }
                
            else:
                # 默认回显
                response = {
                    "type": "echo",
                    "data": {
                        "original": data.get("data", {}),
                        "original_type": msg_type,
                        "server_processed_at": datetime.now().isoformat()
                    },
                    "timestamp": int(datetime.now().timestamp() * 1000)
                }
                
            await websocket.send(json.dumps(response))
            
        except json.JSONDecodeError:
            # 不是 JSON，当作纯文本处理
            response = {
                "type": "text_echo",
                "data": {
                    "original": message,
                    "note": "这是文本消息"
                },
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            await websocket.send(json.dumps(response))
    
    async def start(self):
        """启动服务器"""
        logging.info(f"🚀 启动 WebSocket 服务器: ws://{self.host}:{self.port}")
        
        # 创建处理函数包装器（解决参数问题）
        async def connection_handler(websocket, path):
            await self.handle_connection(websocket, path)
        
        # 启动服务器
        server = await websockets.serve(
            connection_handler,
            self.host,
            self.port,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=None,
            max_size=10 * 1024 * 1024
        )
        
        logging.info("📌 服务器已启动，等待连接...")
        logging.info("🛑 按 Ctrl+C 停止服务器")
        
        # 保持服务器运行
        try:
            await asyncio.Future()  # 永久运行
        finally:
            server.close()
            await server.wait_closed()
            logging.info("👋 服务器已关闭")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='极简 WebSocket 测试服务器')
    parser.add_argument('--host', default='localhost', help='监听地址')
    parser.add_argument('--port', type=int, default=8088, help='监听端口')
    
    args = parser.parse_args()
    
    server = SimpleWebSocketServer(args.host, args.port)
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logging.info("👋 服务器被用户中断")

if __name__ == "__main__":
    main()