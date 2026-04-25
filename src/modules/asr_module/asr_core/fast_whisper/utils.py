# fast_whisper/utils.py
from loguru import logger
from datetime import datetime
from typing import Dict, Any

def check_hardware() -> Dict[str, Any]:
    """硬件检测"""
    import torch
    info = {
        "cuda_available": torch.cuda.is_available(),
        "device_name": "CPU",
        "device_count": 0,
        "compute_type": "int8"
    }
    
    if info["cuda_available"]:
        info.update({
            "device_name": torch.cuda.get_device_name(0),
            "device_count": torch.cuda.device_count(),
            "compute_type": "int8_float16"
        })
    
    return info

class PerformanceProfiler:
    """性能分析器"""
    def __init__(self, enable: bool = True):
        self.enable = enable
        self.stats = []
    
    def record(self, audio_duration: float, inference_time: float):
        if not self.enable:
            return
        
        rtf = inference_time / audio_duration if audio_duration > 0 else 0
        self.stats.append({
            "timestamp": datetime.now().isoformat(),
            "rtf": rtf,
            "audio_duration": audio_duration,
            "inference_time": inference_time
        })
        
        if len(self.stats) % 10 == 0:
            avg_rtf = sum(s["rtf"] for s in self.stats[-10:]) / 10
            logger.info(f"最近10次平均RTF: {avg_rtf:.3f}")