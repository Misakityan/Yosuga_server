# asr_module/client/models.py
from pydantic import BaseModel
from typing import Optional

class ASRHealthStatus(BaseModel):
    """ASR服务健康状态"""
    status: str             # 状态
    timestamp: str          # 时间戳
    device: str             # 设备
    model_loaded: bool      # 模型是否加载

class ASRResult(BaseModel):
    """语音识别结果"""
    text: str               # 识别结果
    language: str           # 语言
    confidence: float       # 置信度
    processing_time: float  # 处理时间

class ASRResponse(BaseModel):
    """统一API响应"""
    success: bool
    data: Optional[ASRResult] = None
    error: Optional[str] = None

class ServiceInfo(BaseModel):
    """服务信息"""
    message: str            # 消息
    docs: str               # 文档
    health: str             # 健康
    transcribe: str         # 识别