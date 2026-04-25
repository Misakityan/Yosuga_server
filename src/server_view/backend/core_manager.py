"""
Yosuga Server 核心进程管理器
"""
import asyncio
import threading
import time
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

# 全局状态
_core_instance: Optional[Any] = None
_core_thread: Optional[threading.Thread] = None
_core_start_time: Optional[float] = None
_core_stop_event: threading.Event = threading.Event()  # 停止信号
_core_lock = threading.Lock()
_logger: Optional[logging.Logger] = None


@dataclass
class CoreStatus:
    is_running: bool = False
    pid: int = 0
    uptime: float = 0.0
    error: Optional[str] = None
    thread_alive: bool = False
    start_time: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_running": self.is_running,
            "pid": self.pid,
            "uptime": round(self.uptime, 1),
            "error": self.error,
            "thread_alive": self.thread_alive,
            "start_time": self.start_time
        }

import os
def get_status() -> CoreStatus:
    """获取当前核心状态"""
    global _core_thread, _core_start_time, _core_instance

    with _core_lock:
        status = CoreStatus()

        if _core_thread is not None:
            status.thread_alive = _core_thread.is_alive()
            status.pid = os.getpid()

        if _core_start_time and (status.thread_alive or _core_instance is not None):
            status.uptime = time.time() - _core_start_time
            status.is_running = True
            status.start_time = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(_core_start_time))

        return status


def _setup_loguru_logging(log_queue: Optional[Any] = None):
    """配置loguru，同时转发到标准logging以便Socket.IO捕获"""
    try:
        from loguru import logger
        import logging

        logger.remove()

        # 关键：添加一个sink将loguru日志转发到标准logging
        class LoguruToStandard:
            def write(self, message):
                # 解析loguru格式提取level
                record = message.record
                level = record["level"].name
                # 获取标准logger并发送
                std_logger = logging.getLogger("yosuga")
                if level == "DEBUG":
                    std_logger.debug(record["message"])
                elif level == "INFO":
                    std_logger.info(record["message"])
                elif level == "SUCCESS":
                    std_logger.info(record["message"])
                elif level == "WARNING":
                    std_logger.warning(record["message"])
                elif level == "ERROR":
                    std_logger.error(record["message"])
                elif level == "CRITICAL":
                    std_logger.critical(record["message"])

            def flush(self):
                pass

        # 添加转发处理器
        logger.add(LoguruToStandard(), format="{message}")

        # 文件日志
        from src.config.config import cfg
        log_dir = Path(cfg.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            f"{log_dir}/Yosuga_server-{{time:YYYY-MM-DD_HH-mm-ss}}.log",
            encoding="utf-8",
            rotation="100 MB"
        )

        return logger
    except Exception as e:
        print(f"Loguru配置错误: {e}")
        return None


def _run_core_thread(project_root: Path):
    """在独立线程中运行YosugaServerCore"""
    global _core_instance, _core_start_time, _core_stop_event, _logger

    _core_stop_event.clear()

    try:
        sys.path.insert(0, str(project_root))

        from src.server_core.core import YosugaServerCore
        from src.config.config import cfg

        # 配置loguru并获取logger
        logger = _setup_loguru_logging()
        if logger:
            logger.info("Yosuga_server 在线程中启动")
            _logger = logger

        async def run_core():
            global _core_instance
            try:
                _core_instance = await YosugaServerCore.get_instance()

                if logger:
                    logger.success(f"YosugaServerCore 初始化完成，线程ID: {threading.current_thread().ident}")

                # 运行核心，同时检查停止信号
                core_task = asyncio.create_task(_core_instance.run())

                # 等待任务完成或收到停止信号
                while not core_task.done():
                    if _core_stop_event.is_set():
                        core_task.cancel()
                        try:
                            await core_task
                        except asyncio.CancelledError:
                            if logger:
                                logger.info("核心收到停止信号，正在关闭...")
                        break
                    await asyncio.sleep(0.1)

                if logger:
                    logger.info("核心事件循环已结束")

            except asyncio.CancelledError:
                if logger:
                    logger.info("核心任务已取消")
            except Exception as e:
                if logger:
                    logger.exception(f"核心运行异常: {e}")
                raise

        # 运行异步核心
        asyncio.run(run_core())

    except Exception as e:
        import traceback
        error_msg = f"核心线程异常: {str(e)}\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr)
        if _logger:
            _logger.error(error_msg)
    finally:
        _core_instance = None
        if logger:
            logger.info("核心线程已退出")


def start_core(project_root: Path) -> tuple[bool, Optional[str]]:
    """启动Yosuga核心"""
    global _core_thread, _core_start_time, _core_stop_event

    with _core_lock:
        if _core_thread is not None and _core_thread.is_alive():
            return True, None  # 已经在运行

        _core_start_time = None
        _core_stop_event.clear()

        try:
            _core_thread = threading.Thread(
                target=_run_core_thread,
                args=(project_root,),
                name="YosugaServerCore",
                daemon=True
            )
            _core_thread.start()
            _core_start_time = time.time()  # 立即记录

            time.sleep(0.5)

            if not _core_thread.is_alive():
                _core_start_time = None
                return False, "核心线程未能启动"

            return True, None

        except Exception as e:
            _core_start_time = None
            return False, str(e)


def stop_core() -> tuple[bool, Optional[str]]:
    """停止Yosuga核心"""
    global _core_thread, _core_start_time, _core_stop_event

    with _core_lock:
        if _core_thread is None or not _core_thread.is_alive():
            _core_thread = None
            _core_start_time = None
            return True, None  # 已经停止

        try:
            # 发送停止信号
            _core_stop_event.set()

            # 等待线程结束（带超时）
            _core_thread.join(timeout=10.0)

            was_alive = _core_thread.is_alive()
            _core_thread = None

            if was_alive:
                # 线程还在运行，但已经发送了停止信号
                # 由于daemon=True，主进程退出时会强制终止
                _core_start_time = None
                return True, "核心停止信号已发送，正在后台停止"

            _core_start_time = None
            return True, None

        except Exception as e:
            return False, str(e)


# 兼容旧接口
def get_core_status() -> Dict[str, Any]:
    return get_status().to_dict()