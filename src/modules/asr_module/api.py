# asr_module/api.py
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
import tempfile
import time
from datetime import datetime
from loguru import logger
from src.modules.asr_module.asr_core.fast_whisper import create_asr, ASRConfig

# 初始化FastAPI应用
app = FastAPI(
    title="Yosuga ASR API",
    description="基于faster-whisper Turbo的高性能多语种语音转文本服务",
    version="1.0.0"
)

# 全局单例ASR实例（延迟加载）
_asr_instance = None

def get_asr():
    """获取或创建ASR实例（单例）"""
    global _asr_instance
    if _asr_instance is None:
        logger.info("初始化ASR服务...")
        _asr_instance = create_asr(
            ASRConfig(
                model_name="deepdml/faster-whisper-large-v3-turbo-ct2",
                device="auto",
                compute_type="int8_float16",    # 如果你是gtx老卡，换成float32
                cache_dir=Path("asr_models/faster_whisper_large_v3_ct2"),
                beam_size=1,        # 贪婪搜索，速度最快
                vad_filter=True,    # 过滤静音，节省30%时间
            )
        )
        logger.info("ASR服务初始化完成")
    return _asr_instance

@app.on_event("startup")
async def startup_event():
    """应用启动时预加载模型"""
    get_asr()

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    global _asr_instance
    if _asr_instance:
        _asr_instance.shutdown()
        logger.info("ASR服务已关闭")

@app.post("/transcribe", response_class=JSONResponse)
async def transcribe_audio(
    file: UploadFile = File(..., description="音频文件 (WAV, FLAC, MP3等格式)")
):
    """
    语音转文本API
    
    - **file**: 音频文件，支持WAV/FLAC/MP3等格式
    - **返回**: JSON格式结果，包含text/language/confidence
    """
    start_time = time.time()
    
    # 验证文件类型
    if file.content_type and not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="请上传音频文件 (MIME类型: audio/*)")
    
    try:
        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = Path(tmp_file.name)
        
        logger.info(f"接收文件: {file.filename} ({len(content)} bytes)")
        
        # 调用ASR识别
        asr = get_asr()
        text, language, confidence = asr.transcribe_wav(tmp_path)
        
        # 清理临时文件
        tmp_path.unlink(missing_ok=True)
        
        processing_time = time.time() - start_time
        
        logger.info(f"识别完成: {language} | {len(text)}字符 | 置信度:{confidence:.2f} | 耗时:{processing_time:.3f}s")
        
        return {
            "success": True,
            "data": {
                "text": text,
                "language": language,
                "confidence": confidence,
                "processing_time": round(processing_time, 3)
            }
        }
        
    except Exception as e:
        logger.error(f"识别失败: {e}")
        raise HTTPException(status_code=500, detail=f"识别失败: {str(e)}")

@app.get("/health")
async def health_check():
    """健康检查接口"""
    asr = get_asr()
    health = asr.health_check()
    
    return {
        "status": "healthy" if health["status"] == "healthy" else "unhealthy",
        "timestamp": datetime.now().isoformat(),
        "device": health["device"],
        "model_loaded": health["model_loaded"]
    }

@app.get("/")
async def root():
    """API根路径"""
    return {
        "message": "Yosuga ASR API 正在运行",
        "docs": "/docs",
        "health": "/health",
        "transcribe": "/transcribe (POST)"
    }