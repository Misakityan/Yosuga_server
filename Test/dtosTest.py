from src.modules.websocket_base_module.dto.second_dtos import get_json_dto_instance
from src.modules.websocket_base_module.dto.third_dtos import AudioDataDTO
from src.modules.websocket_base_module.websocket_core.core_ws_server import get_ws_server
import asyncio
from loguru import logger
async def main():
    # 获取WebSocket服务器单例
    ws_server = await get_ws_server()
    # 获取二级json分发器单例
    json_dto = await get_json_dto_instance(ws_server)

    # 创建DTO实例（自动注册接收函数）
    audio_dto = AudioDataDTO(json_dto)

    logger.info("所有DTO接收器已注册，等待客户端连接...")

    # 启动服务器（阻塞）
    try:
        await ws_server.run("localhost", 8765)
    except asyncio.CancelledError:
        logger.info("服务器任务已取消，正在优雅退出...")
    finally:
        logger.info("服务器已停止")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✓ 服务器已手动终止（按 Ctrl+C）")