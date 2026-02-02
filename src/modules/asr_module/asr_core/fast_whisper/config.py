# fast_whisper/config.py
from dataclasses import dataclass
from pathlib import Path
import torch

@dataclass
class ASRConfig:
    """ASR配置类"""
    model_name: str = "deepdml/faster-whisper-large-v3-turbo-ct2"
    device: str = "auto"
    compute_type: str = "int8_float16"
    cache_dir: Path = Path.home() / ".cache" / "faster_whisper"
    
    # 速度优化参数
    beam_size: int = 1
    best_of: int = 1
    vad_filter: bool = True
    batch_size: int = 16
    
    # 性能统计
    enable_profiling: bool = True
    
    def __post_init__(self):
        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            
        if self.device == "cpu":
            self.compute_type = "int8"
            self.batch_size = 4