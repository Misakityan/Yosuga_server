import asyncio
from contextlib import suppress

from loguru import logger
from src.config.config import cfg
from datetime import datetime
from src.server_core.core import YosugaServerCore

def init():
    """
    Yosuga_server 初始化
    """
    
    # 初始化日志系统
    logger.add(
        f"{cfg.log_dir}/Yosuga_server-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log",
               encoding="utf-8")
    logger.info("Yosuga_server 启动")
    logger.info(f"日志文件目录见: {cfg.log_dir} 目录")
    

async def main():
    core = await YosugaServerCore.get_instance()
    try:
        await core.run()
    except asyncio.CancelledError:
        pass  # 正常取消，不打印堆栈
    finally:
        # 清理未关闭的 aiohttp sessions
        import aiohttp
        pending = [t for t in asyncio.all_tasks()
                   if t is not asyncio.current_task()]
        for task in pending:
            task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.gather(*pending, return_exceptions=True)


if __name__ == "__main__":
    init()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nYosuga服务端已停止喵~~~")
    