"""
Yosuga Server 系统诊断模块 - TCP端口连通性版本
生产级健康检查与自检工具（不依赖HTTP接口）
"""
import asyncio
import json
import socket
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse
import psutil
from loguru import logger

class HealthStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    CHECKING = "checking"

@dataclass
class CheckResult:
    """单项检查结果"""
    name: str
    status: HealthStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp
        }

@dataclass
class DiagnosticsReport:
    """完整诊断报告"""
    overall_status: HealthStatus
    checks: List[CheckResult]
    summary: Dict[str, int]
    generated_at: float = field(default_factory=time.time)
    version: str = "1.1.0"

    def to_dict(self) -> dict:
        return {
            "overall_status": self.overall_status.value,
            "checks": [c.to_dict() for c in self.checks],
            "summary": self.summary,
            "generated_at": self.generated_at,
            "version": self.version
        }

class SystemDiagnostics:
    """系统诊断核心类 - TCP端口连通性检测"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self._find_config_path()
        self._timeout_seconds = 3

    def _find_config_path(self) -> Path:
        """自动查找配置文件路径"""
        markers = ['settings.json', 'pyproject.toml']
        current = Path(__file__).resolve().parent.parent.parent.parent

        for path in [current, *current.parents]:
            if (path / 'settings.json').exists():
                return path / 'settings.json'
            if path == path.parent:
                break
        return current / 'settings.json'

    async def _check_tcp_port(self, host: str, port: int) -> Tuple[bool, float, Optional[str]]:
        """
        基础TCP端口连通性检查

        Returns:
            (是否连通, 延迟ms, 错误信息)
        """
        start = time.time()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self._timeout_seconds
            )
            writer.close()
            await writer.wait_closed()
            latency = (time.time() - start) * 1000
            return True, latency, None
        except asyncio.TimeoutError:
            return False, self._timeout_seconds * 1000, "连接超时"
        except ConnectionRefusedError:
            return False, (time.time() - start) * 1000, "连接被拒绝"
        except Exception as e:
            return False, (time.time() - start) * 1000, str(e)

    def _parse_url(self, url: str) -> Tuple[str, int]:
        """
        从URL解析主机和端口
        支持 http://host:port/path 格式
        """
        try:
            parsed = urlparse(url)
            host = parsed.hostname or 'localhost'
            if parsed.port:
                port = parsed.port
            elif parsed.scheme == 'https':
                port = 443
            elif parsed.scheme == 'http':
                port = 80
            else:
                port = 80
            return host, port
        except Exception:
            if ':' in url:
                parts = url.split(':')
                if len(parts) >= 2:
                    last_part = parts[-1].split('/')[0]
                    try:
                        return parts[-2].replace('//', ''), int(last_part)
                    except:
                        pass
            return 'localhost', 80

    async def check_asr(self, url: str = "http://localhost:20260") -> CheckResult:
        """检查ASR服务 - TCP端口连通性"""
        host, port = self._parse_url(url)
        if port == 80 and '20260' in url:
            port = 20260

        is_open, latency, error = await self._check_tcp_port(host, port)

        if is_open:
            return CheckResult(
                name="ASR服务",
                status=HealthStatus.HEALTHY,
                message=f"端口可连通 {host}:{port}",
                details={"host": host, "port": port, "protocol": "TCP"},
                latency_ms=latency
            )
        else:
            return CheckResult(
                name="ASR服务",
                status=HealthStatus.UNHEALTHY,
                message=f"端口不可达 {host}:{port} - {error}",
                details={"host": host, "port": port, "error": error},
                latency_ms=latency
            )

    async def check_tts(self, host: str = "localhost", port: int = 20261) -> CheckResult:
        """检查TTS服务 - TCP端口连通性"""
        is_open, latency, error = await self._check_tcp_port(host, port)

        if is_open:
            return CheckResult(
                name="TTS服务",
                status=HealthStatus.HEALTHY,
                message=f"端口可连通 {host}:{port}",
                details={"host": host, "port": port},
                latency_ms=latency
            )
        else:
            return CheckResult(
                name="TTS服务",
                status=HealthStatus.UNHEALTHY,
                message=f"端口不可达 {host}:{port} - {error}",
                details={"host": host, "port": port, "error": error},
                latency_ms=latency
            )

    async def check_ai_service(self, base_url: str, api_key: Optional[str] = None) -> CheckResult:
        """检查AI服务 - TCP端口连通性"""
        host, port = self._parse_url(base_url)

        is_open, latency, error = await self._check_tcp_port(host, port)

        if is_open:
            return CheckResult(
                name="AI服务",
                status=HealthStatus.HEALTHY,
                message=f"端口可连通 {host}:{port}",
                details={"host": host, "port": port, "base_url": base_url},
                latency_ms=latency
            )
        else:
            return CheckResult(
                name="AI服务",
                status=HealthStatus.UNHEALTHY,
                message=f"端口不可达 {host}:{port} - {error}",
                details={"host": host, "port": port, "error": error},
                latency_ms=latency
            )

    async def check_auto_agent(self, base_url: str) -> CheckResult:
        """检查Auto Agent服务 - TCP端口连通性"""
        host, port = self._parse_url(base_url)

        is_open, latency, error = await self._check_tcp_port(host, port)

        if is_open:
            return CheckResult(
                name="自动代理服务",
                status=HealthStatus.HEALTHY,
                message=f"端口可连通 {host}:{port}",
                details={"host": host, "port": port},
                latency_ms=latency
            )
        else:
            return CheckResult(
                name="自动代理服务",
                status=HealthStatus.UNHEALTHY,
                message=f"端口不可达 {host}:{port} - {error}",
                details={"host": host, "port": port, "error": error},
                latency_ms=latency
            )

    async def check_config_file(self) -> CheckResult:
        """检查配置文件合法性"""
        try:
            if not self.config_path.exists():
                return CheckResult(
                    name="配置文件",
                    status=HealthStatus.UNHEALTHY,
                    message=f"配置文件不存在: {self.config_path}"
                )

            with open(self.config_path, 'r', encoding='utf-8') as f:
                content = f.read()
                config = json.loads(content)

            required_sections = ['ai', 'tts', 'asr']
            missing = [s for s in required_sections if s not in config]

            if missing:
                return CheckResult(
                    name="配置文件",
                    status=HealthStatus.UNHEALTHY,
                    message=f"缺少配置节: {', '.join(missing)}",
                    details={"missing_sections": missing}
                )

            return CheckResult(
                name="配置文件",
                status=HealthStatus.HEALTHY,
                message=f"配置合法，含 {len(config)} 个配置节",
                details={"sections": list(config.keys())}
            )

        except json.JSONDecodeError as e:
            return CheckResult(
                name="配置文件",
                status=HealthStatus.UNHEALTHY,
                message=f"JSON格式错误: {str(e)}"
            )
        except Exception as e:
            return CheckResult(
                name="配置文件",
                status=HealthStatus.UNHEALTHY,
                message=f"读取失败: {str(e)}"
            )

    async def check_model_files(self, config: Optional[Dict] = None) -> CheckResult:
        """检查模型文件存在性"""
        try:
            if config is None:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

            checks = {}
            missing = []
            project_root = self.config_path.parent

            if 'tts' in config:
                tts = config['tts']
                gpt_path = tts.get('gpt_model_name', '')
                sovits_path = tts.get('sovits_model_name', '')

                if gpt_path:
                    full_path = project_root / gpt_path
                    exists = full_path.exists()
                    checks['gpt_model'] = {"path": str(full_path), "exists": exists}
                    if not exists:
                        missing.append(f"GPT模型: {gpt_path}")

                if sovits_path:
                    full_path = project_root / sovits_path
                    exists = full_path.exists()
                    checks['sovits_model'] = {"path": str(full_path), "exists": exists}
                    if not exists:
                        missing.append(f"SoVITS模型: {sovits_path}")

            if missing:
                return CheckResult(
                    name="模型文件",
                    status=HealthStatus.UNHEALTHY,
                    message=f"缺少 {len(missing)} 个模型文件",
                    details={"missing": missing, "checks": checks}
                )

            return CheckResult(
                name="模型文件",
                status=HealthStatus.HEALTHY,
                message="所有配置模型文件已找到",
                details={"checks": checks}
            )

        except Exception as e:
            return CheckResult(
                name="模型文件",
                status=HealthStatus.UNKNOWN,
                message=f"检查失败: {str(e)}"
            )

    async def check_ports(self, ports: Optional[List[int]] = None) -> CheckResult:
        """检查关键端口占用情况"""
        if ports is None:
            ports = [8089, 20260, 20261, 8765]

        try:
            current_pid = psutil.Process().pid
            current_ports = set()

            proc = psutil.Process(current_pid)
            for conn in proc.connections(kind='inet'):
                if conn.status == 'LISTEN':
                    current_ports.add(conn.lport)

            occupied_by_others = []
            for port in ports:
                if port in current_ports:
                    continue

                for p in psutil.process_iter(['pid', 'name']):
                    try:
                        for conn in p.connections(kind='inet'):
                            if conn.lport == port:
                                occupied_by_others.append({
                                    "port": port,
                                    "pid": p.pid,
                                    "name": p.name()
                                })
                                break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

            if occupied_by_others:
                return CheckResult(
                    name="端口占用",
                    status=HealthStatus.UNHEALTHY,
                    message=f"{len(occupied_by_others)} 个端口被占用",
                    details={"conflicts": occupied_by_others}
                )

            return CheckResult(
                name="端口占用",
                status=HealthStatus.HEALTHY,
                message="关键端口可用",
                details={"checked_ports": list(ports), "self_ports": list(current_ports)}
            )

        except Exception as e:
            return CheckResult(
                name="端口占用",
                status=HealthStatus.UNKNOWN,
                message=f"检查失败: {str(e)}"
            )

    async def run_full_diagnostics(self) -> DiagnosticsReport:
        """执行完整系统体检"""
        logger.info("开始系统体检(TCP模式)...")
        checks = []

        checks.append(await self.check_config_file())
        checks.append(await self.check_ports())

        service_results = await self._check_services_tcp()
        checks.extend(service_results)

        checks.append(await self.check_model_files())

        summary = {
            "healthy": sum(1 for c in checks if c.status == HealthStatus.HEALTHY),
            "unhealthy": sum(1 for c in checks if c.status == HealthStatus.UNHEALTHY),
            "unknown": sum(1 for c in checks if c.status == HealthStatus.UNKNOWN),
            "total": len(checks)
        }

        if summary["unhealthy"] == 0:
            overall = HealthStatus.HEALTHY
        elif summary["unhealthy"] <= summary["healthy"]:
            overall = HealthStatus.UNKNOWN
        else:
            overall = HealthStatus.UNHEALTHY

        report = DiagnosticsReport(
            overall_status=overall,
            checks=checks,
            summary=summary
        )

        logger.info(f"体检完成: {summary['healthy']}/{summary['total']} 项正常")
        return report

    async def _check_services_tcp(self) -> List[CheckResult]:
        """检查各项服务 - 纯TCP连通性"""
        results = []

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            if 'asr' in config:
                asr_url = config['asr'].get('url', 'http://localhost:20260')
                results.append(await self.check_asr(asr_url))
            else:
                results.append(CheckResult(
                    name="ASR服务",
                    status=HealthStatus.UNKNOWN,
                    message="配置中未启用ASR"
                ))

            if 'tts' in config:
                tts_cfg = config['tts']
                results.append(await self.check_tts(
                    tts_cfg.get('host', 'localhost'),
                    tts_cfg.get('port', 20261)
                ))
            else:
                results.append(CheckResult(
                    name="TTS服务",
                    status=HealthStatus.UNKNOWN,
                    message="配置中未启用TTS"
                ))

            if 'ai' in config:
                ai_cfg = config['ai']
                results.append(await self.check_ai_service(
                    ai_cfg.get('base_url', 'http://localhost:1234/v1')
                ))
            else:
                results.append(CheckResult(
                    name="AI服务",
                    status=HealthStatus.UNKNOWN,
                    message="配置中未启用AI"
                ))

            if 'auto_agent' in config:
                aa_cfg = config['auto_agent']
                results.append(await self.check_auto_agent(
                    aa_cfg.get('base_url', 'http://localhost:1234/v1')
                ))
            else:
                results.append(CheckResult(
                    name="自动代理服务",
                    status=HealthStatus.UNKNOWN,
                    message="配置中未启用自动代理"
                ))

        except Exception as e:
            logger.error(f"服务检查失败: {e}")
            results.append(CheckResult(
                name="服务检查",
                status=HealthStatus.UNHEALTHY,
                message=f"配置加载失败: {str(e)}"
            ))

        return results

    async def quick_check_module(self, module_name: str, config: Dict) -> CheckResult:
        """快速检查单个模块 - TCP连通性"""
        if module_name == "asr":
            url = config.get('url', 'http://localhost:20260')
            return await self.check_asr(url)
        elif module_name == "tts":
            return await self.check_tts(
                config.get('host', 'localhost'),
                config.get('port', 20261)
            )
        elif module_name == "ai":
            return await self.check_ai_service(
                config.get('base_url', 'http://localhost:1234/v1')
            )
        elif module_name == "auto_agent":
            return await self.check_auto_agent(
                config.get('base_url', 'http://localhost:1234/v1')
            )
        elif module_name == "llm_core":
            from src.server_view.backend.core_manager import get_status
            status = get_status()
            if status.is_running:
                return CheckResult(
                    name="LLM核心",
                    status=HealthStatus.HEALTHY,
                    message="核心进程运行中",
                    details={"uptime": status.uptime, "pid": status.pid}
                )
            else:
                return CheckResult(
                    name="LLM核心",
                    status=HealthStatus.UNHEALTHY,
                    message="核心进程未启动"
                )
        else:
            return CheckResult(
                name=module_name,
                status=HealthStatus.UNKNOWN,
                message="未知模块"
            )

_diagnostics_instance: Optional[SystemDiagnostics] = None

async def get_diagnostics() -> SystemDiagnostics:
    """获取诊断实例（单例）"""
    global _diagnostics_instance
    if _diagnostics_instance is None:
        _diagnostics_instance = SystemDiagnostics()
    return _diagnostics_instance