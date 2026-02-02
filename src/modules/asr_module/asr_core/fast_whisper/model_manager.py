# fast_whisper/model_manager.py
import gc
from loguru import logger
from pathlib import Path
from typing import Optional
from faster_whisper import WhisperModel
import torch

from .config import ASRConfig


class ModelManager:
    """
    模型管理类
    - 负责模型生命周期管理
    - 支持自定义缓存目录
    - 自动硬件适配
    """
    
    def __init__(self, config: ASRConfig):
        self.config = config
        self._model: Optional[WhisperModel] = None
        self._device_info = None
        
        # 确保缓存目录存在
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        
    @property
    def model(self) -> Optional[WhisperModel]:
        """懒加载模型"""
        if self._model is None:
            self._load_model()
        return self._model
    
    def _load_model(self):
        """加载模型"""
        logger.info(f"🚀 初始化模型: {self.config.model_name}")
        logger.info(f"📦 设备: {self.config.device}, 计算类型: {self.config.compute_type}")
        
        try:
            self._model = WhisperModel(
                self.config.model_name,
                device=self.config.device,
                compute_type=self.config.compute_type,
                download_root=str(self.config.cache_dir),
                local_files_only=False,
            )
            
            self._device_info = {
                "device": self.config.device,
                "compute_type": self.config.compute_type,
                "model_size": self.config.model_name.split("-")[-2]
            }
            
            logger.info("✅ 模型加载成功")
            
        except Exception as e:
            logger.error(f"❌ 模型加载失败: {e}")
            raise RuntimeError(f"Failed to load ASR model: {e}")
    
    def reload(self, new_config: ASRConfig):
        """热重载模型"""
        logger.info("🔄 热重载模型...")
        self.unload()
        self.config = new_config
        self._load_model()
    
    def unload(self):
        """卸载模型释放资源"""
        if self._model is not None:
            logger.info("🗑️ 卸载模型...")
            del self._model
            self._model = None
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            gc.collect()
            
            logger.info("✅ 模型已卸载")
    
    def get_device_info(self) -> dict:
        """获取设备信息"""
        return self._device_info or {}
    
    def __enter__(self):
        """上下文管理器支持"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """自动清理资源"""
        self.unload()