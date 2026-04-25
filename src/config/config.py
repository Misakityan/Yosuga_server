"""
零初始化 JSON 配置管理
用法：from src.config import cfg  # 直接访问，自动初始化
"""
import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional, TypeVar
from dataclasses import dataclass, field, asdict

def _project_root() -> Path:
    """自动查找项目根目录"""
    markers = ['pyproject.toml', 'settings.json', '.gitignore', 'main.py', '.python-version']
    current = Path(__file__).resolve().parent.parent  # src的父目录

    for path in [current, *current.parents]:
        if any((path / m).exists() for m in markers):
            return path
        if path == path.parent:
            break
    return current

# 配置定义

@dataclass
class AIConfig:
    api_key: Optional[str] = "sk-xxxxx"
    base_url: str = "http://localhost:1234/v1"
    model_name: str = "qwen/qwen3-4b-2507"
    timeout: int = 30
    temperature: float = 0.4
    max_tokens: int = 4096


@dataclass
class TTSConfig:
    enabled: bool = True
    api_key: Optional[str] = None
    gpt_model_name: str = "GPT_weights_v2Pro/Yosuga_Airi-e32.ckpt"
    sovits_model_name: str = "SoVITS_weights_v2Pro/Yosuga_Airi_e16_s864.pth"
    host: str = "localhost"
    port: int = 20261
    reference_audio: str = "./using/reference.wav"
    streaming: bool = True
    speed: float = 1.0

@dataclass
class ASRConfig:
    enabled: bool = True
    api_key: Optional[str] = None
    model_name: str = "fast-whisper"
    url: str = "http://localhost:20260/"

@dataclass
class AutoAgentConfig:
    enabled: bool = True
    api_key: Optional[str] = None
    deployment_type: str = "lmstudio"
    model_name: str = "ui-tars-1.5-7b@q4_k_m"
    base_url: str = "http://localhost:1234/v1"
    temperature: float = 0.1
    max_tokens: int = 16384

@dataclass
class LLMConfig:
    enabled: bool = True
    role_character: str = "你是由Misakiotoha开发的助手稲葉愛理ちゃん，可以和用户一起玩游戏，聊天，做各种事情，性格抽象，没事爱整整活。"
    max_context_tokens: int = 2048
    enable_history: bool = True
    language: str = "日本语"

@dataclass
class PathsConfig:
    temp: str = "./tmp/"
    log: str = "./log/"
    using: str = "./using/"


class AppConfig:
    """
    应用主配置
    新增配置分组：1) 上方新建 dataclass  2) 下方 __init__ 添加字段  3) 完成
    """

    def __init__(
        self,
        version: str = "1.0.0",
        debug: bool = False,
        ai: Optional[AIConfig] = None,
        tts: Optional[TTSConfig] = None,
        asr: Optional[ASRConfig] = None,
        auto_agent: Optional[AutoAgentConfig] = None,
        llm_core: Optional[LLMConfig] = None,
        paths: Optional[PathsConfig] = None,
        _config_path: Optional[Path] = None,
        **kwargs
    ):
        # 基础字段
        self.version = version
        self.debug = debug

        # self.ai = ai if ai is not None else AIConfig()
        # self.tts = tts if tts is not None else TTSConfig()
        # self.asr = asr if asr is not None else ASRConfig()
        # self.auto_agent = auto_agent if auto_agent is not None else AutoAgentConfig()
        # self.llm_core = llm_core if llm_core is not None else LLMConfig()
        # self.paths = paths if paths is not None else PathsConfig()

        # 如果是字典则转换，否则使用默认值
        self.ai = AIConfig(**ai) if isinstance(ai, dict) else (ai or AIConfig())
        self.tts = TTSConfig(**tts) if isinstance(tts, dict) else (tts or TTSConfig())
        self.asr = ASRConfig(**asr) if isinstance(asr, dict) else (asr or ASRConfig())
        self.auto_agent = AutoAgentConfig(**auto_agent) if isinstance(auto_agent, dict) else (
                    auto_agent or AutoAgentConfig())
        self.llm_core = LLMConfig(**llm_core) if isinstance(llm_core, dict) else (llm_core or LLMConfig())
        self.paths = PathsConfig(**paths) if isinstance(paths, dict) else (paths or PathsConfig())

        # 内部状态（非 dataclass 字段，不会被序列化）
        self._config_path = _config_path
        self._lock = threading.RLock()  # 普通属性，非 dataclass 字段

        # 应用其他字段（用于从 JSON 加载时）
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

        # 路径解析为绝对路径
        if self._config_path:
            root = self._config_path.parent
            for field_name in ['temp', 'log', 'using']:
                rel_path = getattr(self.paths, field_name)
                if not Path(rel_path).is_absolute():
                    abs_path = (root / Path(rel_path)).resolve()
                    setattr(self.paths, field_name, str(abs_path) + '/')

    # 便捷属性

    @property
    def temp_dir(self) -> Path:
        return Path(self.paths.temp)

    @property
    def log_dir(self) -> Path:
        return Path(self.paths.log)

    @property
    def using_dir(self) -> Path:
        return Path(self.paths.using)

    # 核心方法

    def get(self, key: str, default: Any = None) -> Any:
        """
        点号路径访问：cfg.get("ai.timeout") / cfg.get("tts.enabled")
        """
        try:
            keys = key.split('.')
            value = self
            for k in keys:
                value = getattr(value, k) if not isinstance(value, dict) else value[k]
            return value
        except (AttributeError, KeyError):
            return default

    def set(self, key: str, value: Any, save: bool = True) -> 'AppConfig':
        """
        点号路径设置，支持链式调用
        cfg.set("ai.timeout", 60).set("debug", True)
        """
        with self._lock:
            keys = key.split('.')
            target = self
            for k in keys[:-1]:
                target = getattr(target, k)
            setattr(target, keys[-1], value)

        if save:
            self._save()
        return self

    def update(self, updates: Dict[str, Any], save: bool = True) -> 'AppConfig':
        """
        批量更新：cfg.update({"ai": {"timeout": 60}, "debug": True})
        """
        def deep_update(obj: Any, data: dict):
            for k, v in data.items():
                if hasattr(obj, k):
                    current = getattr(obj, k)
                    if isinstance(v, dict) and hasattr(current, '__dataclass_fields__'):
                        deep_update(current, v)
                    else:
                        setattr(obj, k, v)

        with self._lock:
            deep_update(self, updates)

        if save:
            self._save()
        return self

    def reload(self) -> 'AppConfig':
        """热重载配置"""
        if self._config_path and self._config_path.exists():
            with self._lock:
                data = json.loads(self._config_path.read_text(encoding='utf-8'))

                # 配置项名 -> dataclass 类的映射（和 _load 保持一致）
                config_classes = {
                    'ai': AIConfig,
                    'tts': TTSConfig,
                    'asr': ASRConfig,
                    'auto_agent': AutoAgentConfig,
                    'llm_core': LLMConfig,
                    'paths': PathsConfig,
                }

                for k, v in data.items():
                    if hasattr(self, k) and not k.startswith('_'):
                        # 如果是配置项且是 dict，转换为 dataclass
                        if k in config_classes and isinstance(v, dict):
                            setattr(self, k, config_classes[k](**v))
                        else:
                            setattr(self, k, v)
            print(f"配置重载: {self._config_path}")
        return self

    def to_dict(self) -> dict:
        """导出为字典（手动实现，排除内部属性）"""
        result = {
            'version': self.version,
            'debug': self.debug,
            'ai': asdict(self.ai) if hasattr(self.ai, '__dataclass_fields__') else self.ai,
            'tts': asdict(self.tts) if hasattr(self.tts, '__dataclass_fields__') else self.tts,
            'asr': asdict(self.asr) if hasattr(self.asr, '__dataclass_fields__') else self.asr,
            'auto_agent': asdict(self.auto_agent) if hasattr(self.auto_agent, '__dataclass_fields__') else self.auto_agent,
            'llm_core': asdict(self.llm_core) if hasattr(self.llm_core, '__dataclass_fields__') else self.llm_core,
            'paths': asdict(self.paths) if hasattr(self.paths, '__dataclass_fields__') else self.paths,
        }
        return result

    def _save(self) -> None:
        """保存到文件"""
        if self._config_path:
            with self._lock:
                json_str = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
                self._config_path.write_text(json_str, encoding='utf-8')

    @classmethod
    def _load(cls, path: Path) -> 'AppConfig':
        """从文件加载"""
        data = json.loads(path.read_text(encoding='utf-8'))

        # 配置项名 -> dataclass 类的映射
        config_classes = {
            'ai': AIConfig,
            'tts': TTSConfig,
            'asr': ASRConfig,
            'auto_agent': AutoAgentConfig,
            'llm_core': LLMConfig,
            'paths': PathsConfig,
        }

        # 自动转换 dict 为对应 dataclass
        for key, config_class in config_classes.items():
            if key in data and isinstance(data[key], dict):
                data[key] = config_class(**data[key])

        return cls(_config_path=path, **data)

    @classmethod
    def _create_default(cls, path: Path) -> 'AppConfig':
        """创建默认配置"""
        instance = cls(_config_path=path)
        instance._save()
        print(f"默认配置已创建: {path}")
        return instance

    def __repr__(self) -> str:
        """友好的打印格式"""
        lines = ["AppConfig("]
        for k, v in self.to_dict().items():
            lines.append(f"  {k}={v!r},")
        lines.append(")")
        return "\n".join(lines)


# 延迟初始化机制

_root: Path = _project_root()
_config_path: Path = _root / "settings.json"
_config_instance: Optional[AppConfig] = None
_init_lock: threading.Lock = threading.Lock()


def _ensure_initialized() -> AppConfig:
    """
    确保配置已初始化（线程安全的延迟初始化）
    """
    global _config_instance

    if _config_instance is not None:
        return _config_instance

    with _init_lock:
        if _config_instance is not None:
            return _config_instance

        # 自动加载或创建
        if _config_path.exists():
            _config_instance = AppConfig._load(_config_path)
            print(f"配置加载: {_config_path}")
        else:
            _config_instance = AppConfig._create_default(_config_path)

        # 确保目录存在
        for d in [_config_instance.temp_dir,
                  _config_instance.log_dir,
                  _config_instance.using_dir]:
            d.mkdir(parents=True, exist_ok=True)

        return _config_instance


class _LazyConfig:
    """
    配置代理类：拦截所有属性访问，第一次使用时自动初始化
    """

    def __getattr__(self, name: str) -> Any:
        """拦截属性访问，延迟初始化"""
        instance = _ensure_initialized()
        return getattr(instance, name)

    def __setattr__(self, name: str, value: Any) -> None:
        """拦截属性设置"""
        # 特殊属性直接设置到代理对象本身
        if name.startswith('_'):
            super().__setattr__(name, value)
        else:
            instance = _ensure_initialized()
            setattr(instance, name, value)

    def __repr__(self) -> str:
        instance = _ensure_initialized()
        return repr(instance)

    def __dir__(self) -> list:
        """支持 IDE 自动补全"""
        instance = _ensure_initialized()
        return dir(instance)

    # 显式代理必要方法
    def get(self, key: str, default: Any = None) -> Any:
        return _ensure_initialized().get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> AppConfig:
        return _ensure_initialized().set(key, value, save)

    def update(self, updates: Dict[str, Any], save: bool = True) -> AppConfig:
        return _ensure_initialized().update(updates, save)

    def reload(self) -> AppConfig:
        return _ensure_initialized().reload()

    def to_dict(self) -> dict:
        return _ensure_initialized().to_dict()

    def save(self) -> None:
        _ensure_initialized()._save()

    # 属性代理
    @property
    def ai(self) -> AIConfig:
        return _ensure_initialized().ai

    @property
    def tts(self) -> TTSConfig:
        return _ensure_initialized().tts

    @property
    def asr(self) -> ASRConfig:
        return _ensure_initialized().asr

    @property
    def auto_agent(self) -> AutoAgentConfig:
        return _ensure_initialized().auto_agent

    @property
    def llm_core(self) -> LLMConfig:
        return _ensure_initialized().llm_core

    @property
    def paths(self) -> PathsConfig:
        return _ensure_initialized().paths

    @property
    def temp_dir(self) -> Path:
        return _ensure_initialized().temp_dir

    @property
    def log_dir(self) -> Path:
        return _ensure_initialized().log_dir

    @property
    def using_dir(self) -> Path:
        return _ensure_initialized().using_dir

def ensure_config_initialized():
    """
    强制立即初始化配置（用于多线程环境）
    返回真正的 AppConfig 实例而非代理
    """
    return _ensure_initialized()

# 全局配置对象：导入即用，自动初始化
cfg: AppConfig = _LazyConfig()  # type: ignore


# 工具函数

def generate_example(path: Path = _root / "settings.example.json") -> None:
    """生成示例配置文件"""
    example = {
        "version": "1.0.0",
        "debug": False,
        "ai": {
            "api_key": "sk-your-api-key",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "timeout": 30
        },
        "tts": {
            "enabled": True,
            "model": "GPT_SoVITS",
            "url": "http://localhost:12458/",
            "reference_audio": "./using/reference.wav",
            "streaming": True,
            "speed": 1.0
        },
        "paths": {
            "temp": "./tmp/",
            "log": "./log/",
            "data": "./data/"
        }
    }
    path.write_text(json.dumps(example, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"示例配置已生成: {path}")


# 测试代码
if __name__ == "__main__":
    # 测试：直接访问，自动初始化
    print("第一次访问 cfg.ai.model:")
    print(f"  → {cfg.ai.model_name}")

    print(f"\n配置详情:")
    print(cfg)

    print(f"\n测试修改:")
    cfg.set("ai.timeout", 60)
    print(f"  ai.timeout = {cfg.ai.timeout}")

    print(f"\n测试批量更新:")
    cfg.update({"debug": True, "tts": {"speed": 1.5}})
    print(f"  debug = {cfg.debug}, tts.speed = {cfg.tts.speed}")

    print(f"\n测试热重载:")
    cfg.reload()