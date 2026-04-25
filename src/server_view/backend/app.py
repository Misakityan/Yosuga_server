"""
Yosuga Server Web UI - FastAPI Backend with Socket.IO
"""
import asyncio
import json
import logging
import sys
import time
import psutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, Set

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import socketio

# 项目根目录
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.server_view.backend.core_manager import (
    start_core, stop_core, get_status, get_core_status
)
from src.server_view.backend.diagnostics import get_diagnostics, HealthStatus, CheckResult

# Socket.IO 服务器
sio = socketio.AsyncServer(
    cors_allowed_origins="*",
    async_mode="asgi",
    logger=False,
    engineio_logger=False
)

# 跟踪已连接的客户端
connected_clients: Set[str] = set()

# RPC 响应转发回调标志（只注册一次）
_rpc_forwarder_registered: bool = False

# 日志广播处理器
class SocketIOLogHandler(logging.Handler):
    """将Python标准日志发送到Socket.IO"""
    def __init__(self, sio_server):
        super().__init__()
        self.sio = sio_server
        self.setLevel(logging.DEBUG)

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._broadcast(msg, record.levelname))
            except RuntimeError:
                pass
        except Exception:
            pass

    async def _broadcast(self, message: str, level: str):
        try:
            await self.sio.emit('log_line', {
                'line': message,
                'timestamp': time.time(),
                'level': level
            })
        except Exception:
            pass

def setup_logging(sio_server):
    """配置日志系统 - 减少HTTP访问日志噪音"""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 清除现有处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 控制台处理器 - 过滤掉频繁的系统信息HTTP请求日志
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s'
    ))

    # 添加过滤器，排除频繁的HTTP轮询日志
    def filter_http_poll(record):
        msg = record.getMessage()
        # 过滤掉 /api/system/info 和 /api/core/status 的GET请求日志
        if 'GET /api/system/info' in msg or 'GET /api/core/status' in msg:
            return False
        return True

    console.addFilter(filter_http_poll)
    root_logger.addHandler(console)

    # Socket.IO处理器
    sio_handler = SocketIOLogHandler(sio_server)
    sio_handler.setLevel(logging.DEBUG)
    sio_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s - %(message)s'
    ))
    root_logger.addHandler(sio_handler)

    # 设置yosuga logger
    yosuga_logger = logging.getLogger("yosuga")
    yosuga_logger.setLevel(logging.DEBUG)

    return root_logger

# 系统状态监控
async def system_monitor_task():
    """后台任务：定期采集并广播系统状态"""
    while True:
        try:
            # 只有有客户端连接时才采集数据
            if connected_clients:
                # 采集系统数据
                cpu = psutil.cpu_percent(interval=0.1)
                mem = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                proc = psutil.Process()

                system_data = {
                    "cpu": {"percent": cpu, "count": psutil.cpu_count()},
                    "memory": {
                        "total": mem.total, "available": mem.available,
                        "percent": mem.percent, "used": mem.used, "free": mem.free
                    },
                    "disk": {
                        "total": disk.total, "used": disk.used,
                        "free": disk.free, "percent": (disk.used/disk.total)*100
                    },
                    "process": {
                        "memory_percent": proc.memory_percent(),
                        "cpu_percent": proc.cpu_percent(interval=0.1),
                        "threads": proc.num_threads(),
                        "uptime": time.time() - proc.create_time()
                    },
                    "timestamp": time.time()
                }

                # 广播给所有客户端
                await sio.emit('system_stats', {
                    'success': True,
                    'data': system_data
                })

                # 同时广播核心状态（实时推送）
                core_status = get_core_status()
                await sio.emit('core_status', {
                    'success': True,
                    'data': core_status
                })

        except Exception as e:
            logging.error(f"系统监控任务异常: {e}")

        # 1秒间隔，比HTTP轮询更实时
        await asyncio.sleep(1)

# FastAPI 应用
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    logger = setup_logging(sio)
    logger.info("Yosuga Server Web UI 启动")

    monitor_task = asyncio.create_task(system_monitor_task())
    logger.info("系统监控任务已启动")

    yield

    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

    # 清理诊断模块
    try:
        diag = await get_diagnostics()
        # 诊断模块无需要关闭的资源，但保留钩子
    except:
        pass

    logger.info("应用关闭")
    stop_core()
fastapi_app = FastAPI(
    title="Yosuga Server Web UI",
    version="1.0.0",
    lifespan=lifespan
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@fastapi_app.post("/api/diagnostics/run")
async def run_diagnostics():
    """执行完整系统体检"""
    try:
        diag = await get_diagnostics()
        report = await diag.run_full_diagnostics()
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@fastapi_app.get("/api/diagnostics/check/{module}")
async def check_single_module(module: str):
    """检查单个模块状态"""
    try:
        from src.config.config import cfg
        diag = await get_diagnostics()

        # 获取对应配置
        config_map = {
            'asr': cfg.asr,
            'tts': cfg.tts,
            'ai': cfg.ai,
            'auto_agent': cfg.auto_agent,
            'llm_core': cfg.llm_core
        }

        if module not in config_map:
            raise HTTPException(status_code=400, detail=f"未知模块: {module}")

        # 转换为dict
        config_dict = {}
        if hasattr(config_map[module], '__dataclass_fields__'):
            from dataclasses import asdict
            config_dict = asdict(config_map[module])
        else:
            config_dict = dict(config_map[module])

        result = await diag.quick_check_module(module, config_dict)
        return {"success": True, "data": result.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@fastapi_app.get("/api/diagnostics/health")
async def quick_health_check():
    """快速健康检查（用于负载均衡/心跳）"""
    try:
        from src.server_view.backend.core_manager import get_status
        status = get_status()

        # 简单检查WebSocket服务器是否活着
        ws_ok = len(connected_clients) >= 0  # 总是True，只要能响应

        health = {
            "status": "healthy" if status.is_running else "degraded",
            "web_ui": "up",
            "core_running": status.is_running,
            "websocket_clients": len(connected_clients),
            "timestamp": time.time()
        }

        return health

    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

# Socket.IO ASGI应用
app = socketio.ASGIApp(sio, fastapi_app)

# Socket.IO 事件
@sio.event
async def connect(sid, environ):
    """客户端连接"""
    connected_clients.add(sid)
    print(f"客户端连接: {sid} (当前在线: {len(connected_clients)})")

    # 立即发送一次当前状态（避免前端等待）
    await sio.emit('system', {
        'message': '连接成功',
        'timestamp': time.time(),
        'clients_count': len(connected_clients)
    }, to=sid)

    # 立即推送一次系统状态（前端无需再发HTTP请求）
    try:
        core_status = get_core_status()
        await sio.emit('core_status', {
            'success': True,
            'data': core_status
        }, to=sid)
    except Exception as e:
        logging.error(f"推送初始状态失败: {e}")

@sio.event
async def disconnect(sid):
    """客户端断开"""
    connected_clients.discard(sid)
    print(f"客户端断开: {sid} (当前在线: {len(connected_clients)})")

@sio.on('subscribe_logs')
async def handle_subscribe_logs(sid, data):
    """订阅日志（可指定级别过滤）"""
    level = data.get('level', 'ALL') if isinstance(data, dict) else 'ALL'
    print(f"客户端 {sid} 订阅日志: {level}")
    await sio.emit('system', {'message': f'已订阅日志: {level}'}, to=sid)

@sio.on('control_core')
async def handle_control_core(sid, data):
    """WebSocket方式控制核心"""
    action = data.get('action') if isinstance(data, dict) else None

    if action == 'start':
        try:
            # 检查是否已运行
            status = get_status()
            if status.is_running:
                await sio.emit('core_control_result', {
                    'success': True,
                    'message': '核心已在运行',
                    'data': status.to_dict()
                }, to=sid)
                return

            # 启动核心
            success, error = start_core(project_root)
            if success:
                # 等待一下确保启动成功
                await asyncio.sleep(0.5)
                new_status = get_status()
                # 广播给所有客户端（不仅仅是操作者）
                await sio.emit('core_status', {
                    'success': True,
                    'data': new_status.to_dict(),
                    'message': '核心启动成功'
                })
            else:
                await sio.emit('core_control_result', {
                    'success': False,
                    'error': error or '启动失败'
                }, to=sid)
        except Exception as e:
            await sio.emit('core_control_result', {
                'success': False,
                'error': str(e)
            }, to=sid)

    elif action == 'stop':
        try:
            status = get_status()
            if not status.is_running:
                await sio.emit('core_control_result', {
                    'success': True,
                    'message': '核心已停止',
                    'data': status.to_dict()
                }, to=sid)
                return

            success, error = stop_core()
            if success:
                await asyncio.sleep(0.5)  # 等待停止完成
                new_status = get_status()
                await sio.emit('core_status', {
                    'success': True,
                    'data': new_status.to_dict(),
                    'message': '核心已停止'
                })
            else:
                await sio.emit('core_control_result', {
                    'success': False,
                    'error': error or '停止失败'
                }, to=sid)
        except Exception as e:
            await sio.emit('core_control_result', {
                'success': False,
                'error': str(e)
            }, to=sid)


# 设备管理 Socket.IO 事件
@sio.on('get_devices')
async def handle_get_devices(sid):
    """获取当前所有在线设备列表"""
    try:
        from src.server_core.core import YosugaServerCore
        core = await YosugaServerCore.get_instance()
        devices = core.embedded_server.list_devices()
        await sio.emit('devices_list', {
            'success': True,
            'data': devices
        }, to=sid)
    except Exception as e:
        await sio.emit('devices_list', {
            'success': False,
            'error': str(e)
        }, to=sid)

@sio.on('send_device_rpc')
async def handle_send_device_rpc(sid, data):
    """向指定设备发送 RPC 命令"""
    device_id = data.get('device_id') if isinstance(data, dict) else None
    rpc_call = data.get('rpc_call') if isinstance(data, dict) else None
    if not device_id or not rpc_call:
        await sio.emit('device_rpc_result', {
            'success': False,
            'error': '缺少 device_id 或 rpc_call'
        }, to=sid)
        return
    try:
        from src.server_core.core import YosugaServerCore
        core = await YosugaServerCore.get_instance()

        # 注册一次性的 RPC 响应转发回调
        global _rpc_forwarder_registered
        if not _rpc_forwarder_registered:
            async def forward_rpc_response(dev_id: str, payload: dict):
                await sio.emit('device_rpc_response', {
                    'device_id': dev_id,
                    'payload': payload
                })
            core.device_dto.on_rpc_response = forward_rpc_response
            _rpc_forwarder_registered = True

        core.embedded_server.send_rpc(device_id, rpc_call)
        await sio.emit('device_rpc_result', {
            'success': True,
            'device_id': device_id,
            'message': 'RPC 命令已发送到设备'
        }, to=sid)
    except Exception as e:
        await sio.emit('device_rpc_result', {
            'success': False,
            'error': str(e)
        }, to=sid)

# 设备管理 REST API
@fastapi_app.get("/api/devices")
async def get_devices_api():
    """获取所有在线设备（HTTP 备用）"""
    try:
        from src.server_core.core import YosugaServerCore
        core = await YosugaServerCore.get_instance()
        devices = core.embedded_server.list_devices()
        return {"success": True, "data": devices}
    except Exception as e:
        return {"success": False, "error": str(e)}

@sio.on('check_module_health')
async def handle_check_module(sid, data):
    """WebSocket方式检查模块健康"""
    module = data.get('module') if isinstance(data, dict) else None
    if not module:
        await sio.emit('module_health_result', {
            "success": False,
            "error": "未指定模块"
        }, to=sid)
        return

    try:
        from src.config.config import cfg
        diag = await get_diagnostics()

        config_map = {
            'asr': cfg.asr,
            'tts': cfg.tts,
            'ai': cfg.ai,
            'auto_agent': cfg.auto_agent,
            'llm_core': cfg.llm_core
        }

        if module not in config_map:
            await sio.emit('module_health_result', {
                "success": False,
                "error": f"未知模块: {module}"
            }, to=sid)
            return

        # 转换配置
        config_dict = {}
        if hasattr(config_map[module], '__dataclass_fields__'):
            from dataclasses import asdict
            config_dict = asdict(config_map[module])
        else:
            config_dict = dict(config_map[module])

        result = await diag.quick_check_module(module, config_dict)

        await sio.emit('module_health_result', {
            "success": True,
            "module": module,
            "data": result.to_dict()
        }, to=sid)

        # 同时广播给所有客户端更新模块状态
        await sio.emit('module_status_update', {
            "module": module,
            "status": result.to_dict()
        })

    except Exception as e:
        await sio.emit('module_health_result', {
            "success": False,
            "error": str(e)
        }, to=sid)

# REST API
@fastapi_app.get("/api/system/info")
async def get_system_info():
    """HTTP备用接口 - 减少日志"""
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        proc = psutil.Process()

        return {
            "success": True,
            "data": {
                "cpu": {"percent": cpu, "count": psutil.cpu_count()},
                "memory": {
                    "total": mem.total, "available": mem.available,
                    "percent": mem.percent, "used": mem.used, "free": mem.free
                },
                "disk": {
                    "total": disk.total, "used": disk.used,
                    "free": disk.free, "percent": (disk.used/disk.total)*100
                },
                "process": {
                    "memory_percent": proc.memory_percent(),
                    "cpu_percent": proc.cpu_percent(interval=0.1),
                    "threads": proc.num_threads(),
                    "uptime": time.time() - proc.create_time()
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.get("/api/core/status")
async def get_core_status_api():
    """HTTP备用接口"""
    return {"success": True, "data": get_core_status()}

@fastapi_app.post("/api/core/start")
async def start_core_api():
    """HTTP备用接口"""
    try:
        status = get_status()
        if status.is_running:
            return {"success": True, "data": status.to_dict(), "message": "核心已在运行"}

        success, error = start_core(project_root)
        if not success:
            raise HTTPException(status_code=500, detail=error or "启动失败")

        # 等待初始化完成
        for _ in range(20):
            await asyncio.sleep(0.5)
            status = get_status()
            if status.is_running:
                # 通过WebSocket广播状态更新（给所有连接的客户端）
                await sio.emit('core_status', {
                    'success': True,
                    'data': status.to_dict(),
                    'message': '核心启动成功'
                })
                return {"success": True, "data": status.to_dict(), "message": "核心启动成功"}

        status = get_status()
        return {"success": True, "data": status.to_dict(), "message": "核心启动中..."}

    except HTTPException:
        raise
    except Exception as e:
        status = get_status()
        if status.is_running:
            return {"success": True, "data": status.to_dict(), "message": "核心已启动"}
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.post("/api/core/stop")
async def stop_core_api():
    """HTTP备用接口"""
    try:
        status = get_status()
        if not status.is_running:
            return {"success": True, "data": status.to_dict(), "message": "核心已停止"}

        success, error = stop_core()
        if success:
            for _ in range(20):
                await asyncio.sleep(0.5)
                status = get_status()
                if not status.is_running:
                    # 广播状态更新
                    await sio.emit('core_status', {
                        'success': True,
                        'data': status.to_dict(),
                        'message': '核心已停止'
                    })
                    return {"success": True, "data": status.to_dict(), "message": "核心已停止"}

            status = get_status()
            return {"success": True, "data": status.to_dict(), "message": error or "核心停止中..."}
        else:
            raise HTTPException(status_code=500, detail=error or "停止失败")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.get("/api/modules/status")
async def get_modules_status():
    """模块状态"""
    try:
        from src.config.config import cfg
        return {
            "success": True,
            "data": {
                "asr": {"enabled": cfg.asr.enabled},
                "tts": {"enabled": cfg.tts.enabled},
                "ai": {"enabled": cfg.ai.api_key is not None},
                "auto_agent": {"enabled": cfg.auto_agent.enabled},
                "llm_core": {"enabled": cfg.llm_core.enabled}
            }
        }
    except:
        return {
            "success": True,
            "data": {
                "asr": {"enabled": True}, "tts": {"enabled": True},
                "ai": {"enabled": True}, "auto_agent": {"enabled": True},
                "llm_core": {"enabled": True}
            }
        }

@fastapi_app.get("/api/config")
async def get_config():
    from src.config.config import cfg
    return {"success": True, "data": cfg.to_dict()}

@fastapi_app.post("/api/config/{section}")
async def update_config(section: str, data: Dict[str, Any]):
    from src.config.config import cfg
    cfg.update({section: data})
    return {"success": True, "message": "配置已更新"}

@fastapi_app.post("/api/config/reload")
async def reload_config():
    from src.config.config import cfg
    cfg.reload()
    return {"success": True, "message": "配置已重载"}

@fastapi_app.get("/api/preferences")
async def get_preferences():
    prefs_path = Path(__file__).parent / "user_preferences.json"
    if prefs_path.exists():
        with open(prefs_path, 'r', encoding='utf-8') as f:
            return {"success": True, "data": json.load(f)}
    return {"success": True, "data": {}}

@fastapi_app.post("/api/preferences")
async def save_preferences(data: Dict[str, Any]):
    prefs_path = Path(__file__).parent / "user_preferences.json"
    with open(prefs_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return {"success": True, "message": "偏好已保存"}

# 静态文件
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    fastapi_app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

def run_server(host: str = "0.0.0.0", port: int = 8089, debug: bool = False):
    import uvicorn
    uvicorn.run("backend.app:app", host=host, port=port, reload=debug,
                access_log=False)  # 禁用默认访问日志（我们使用自定义过滤器）

if __name__ == "__main__":
    run_server()