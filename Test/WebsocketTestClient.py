import asyncio
import json
from websockets.asyncio.client import connect

async def test_all_types():
    """测试三种消息类型"""
    async with connect("ws://localhost:8765") as ws:
        print("=== 测试JSON消息 ===")
        await ws.send(json.dumps({
            "type": "chat",
            "content": "你好服务器！"
        }))
        print(f"收到: {await ws.recv()}")

        print("\n=== 测试文本消息 ===")
        await ws.send("这是纯文本消息")
        print(f"收到: {await ws.recv()}")

        print("\n=== 测试二进制消息 ===")
        await ws.send(b"\x00\x01\x02\x03\x04")
        print(f"收到: {await ws.recv()}")

if __name__ == "__main__":
    asyncio.run(test_all_types())