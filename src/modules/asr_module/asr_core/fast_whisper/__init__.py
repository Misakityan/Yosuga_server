# fast_whisper/__init__.py
from typing import Optional
from src.modules.asr_module.asr_core.fast_whisper.config import ASRConfig
from src.modules.asr_module.asr_core.fast_whisper.model_manager import ModelManager
from src.modules.asr_module.asr_core.fast_whisper.asr_interface import ASRInterface

__version__ = "1.0.0"
__all__ = ["ASRConfig", "ModelManager", "ASRInterface"]

def create_asr(config: Optional[ASRConfig] = None) -> ASRInterface:
    """
    快速创建ASR实例
    Args:
        config: ASR配置，若为None则使用默认配置
    """
    return ASRInterface.get_instance(config)