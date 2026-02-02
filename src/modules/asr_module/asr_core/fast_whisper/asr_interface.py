# fast_whisper/asr_interface.py
from loguru import logger
from pathlib import Path
from typing import Tuple, Optional
import torchaudio
import torch
import numpy

from .model_manager import ModelManager
from .config import ASRConfig
from .utils import PerformanceProfiler

class ASRInterface:
    """
    ASR接口类 - 全局单例
    - 提供wav转文本功能
    - 注入ModelManager
    - 性能统计
    """
    
    _instance: Optional['ASRInterface'] = None
    
    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[ASRConfig] = None):
        # 防止重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self.config = config or ASRConfig()
        self.model_manager = ModelManager(self.config)
        self.profiler = PerformanceProfiler(self.config.enable_profiling)
        
        # 音频参数
        self.sample_rate = 16000
        
        self._initialized = True
        logger.info("🎤 ASR接口初始化完成")
    
    @classmethod
    def get_instance(cls, config: Optional[ASRConfig] = None) -> 'ASRInterface':
        """全局访问点"""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance
    
    def transcribe_wav(
        self, 
        wav_path: Path, 
        language: Optional[str] = None
    ) -> Tuple[str, str, float]:
        """
        WAV音频转文本（核心接口）
        
        Args:
            wav_path: WAV文件路径
            language: 指定语言代码（如'zh'/'en'），None则自动检测
        
        Returns:
            (text, language, confidence)
        """
        try:
            # 记录开始时间
            import time
            start_time = time.time()
            
            logger.info(f"🎵 开始识别: {wav_path.name}")
            
            # 执行识别...
            audio = self._load_audio(wav_path)
            result = self._transcribe(audio, language)
            text, lang, confidence = self._parse_result(result)
            
            # 计算耗时
            processing_time = time.time() - start_time
            logger.info(
                f"✅ 识别完成: {lang} | {len(text)}字符 | 置信度:{confidence:.2f} | "
                f"耗时:{processing_time:.3f}s | RTF:{processing_time/(len(audio)/self.sample_rate):.3f}"
            )
            
            return text, lang, confidence
            
        except Exception as e:
            logger.error(f"❌ 识别失败 {wav_path}: {e}")
            raise RuntimeError(f"Transcription failed: {e}")
    
    def _load_audio(self, wav_path: Path) -> numpy.ndarray:
        """加载和预处理音频"""
        if not wav_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {wav_path}")
        
        # 加载音频
        waveform, sample_rate = torchaudio.load(wav_path)
        
        # 重采样到16kHz
        if sample_rate != self.sample_rate:
            resampler = torchaudio.transforms.Resample(sample_rate, self.sample_rate)
            waveform = resampler(waveform)
        
        # 转换为单声道
        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)
        
        # 转换为numpy数组
        audio = waveform.squeeze().numpy()
        
        return audio
    
    def _transcribe(self, audio: numpy.ndarray, language: Optional[str]) -> Tuple:
        """执行推理"""
        model = self.model_manager.model
        
        # 添加模型存在性检查
        if model is None:
            logger.error("ASR模型未加载，请检查模型配置和路径")
            raise RuntimeError("ASR模型未加载，请检查模型配置和路径")
        
        # 记录时间
        import time
        start_time = time.time()
        
        # 调用模型
        segments, info = model.transcribe(
            audio,
            language=language,
            beam_size=self.config.beam_size,
            best_of=self.config.best_of,
            vad_filter=self.config.vad_filter,
        )
        
        # 立即执行生成器
        segments_list = list(segments)
        
        # 性能统计
        inference_time = time.time() - start_time
        audio_duration = len(audio) / self.sample_rate
        self.profiler.record(audio_duration, inference_time)
        
        return segments_list, info
    
    def _parse_result(self, result: Tuple) -> Tuple[str, str, float]:
        """解析识别结果"""
        segments, info = result
        
        # 合并所有片段
        text = " ".join([seg.text.strip() for seg in segments])
        
        # 获取语言信息
        language = info.language if info else "unknown"
        confidence = info.language_probability if info else 0.0
        
        return text, language, confidence
    
    def transcribe_batch(self, wav_paths: list) -> list:
        """批量识别接口"""
        return [
            {
                "file": str(path),
                "text": result[0],
                "language": result[1],
                "confidence": result[2]
            }
            for path, result in zip(wav_paths, [
                self.transcribe_wav(Path(p)) for p in wav_paths
            ])
        ]
    
    def health_check(self) -> dict:
        """健康检查接口"""
        return {
            "status": "healthy" if self.model_manager.model else "unhealthy",
            "device": self.config.device,
            "model_loaded": self.model_manager.model is not None,
            "device_info": self.model_manager.get_device_info(),
        }
    
    def shutdown(self):
        """优雅关闭"""
        logger.info("🛑 关闭ASR接口...")
        self.model_manager.unload()