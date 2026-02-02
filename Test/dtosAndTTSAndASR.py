# 一个小Test, 展示设计的dtos模块与tts和asr的集成
from src.modules.websocket_base_module.dto.third_dtos import AudioDataDTO
from src.modules.tts_module.tts_core.async_audio_player import AsyncAudioPlayer
from src.modules.tts_module.tts_core.gpt_sovits.gpt_sovits_client import GPTSoVITSClient, StreamingMode
from src.modules.asr_module.client.asr_client import create_asr_client


# with create_asr_client(base_url="http://192.168.1.5:20260") as client:
#     # 转录文件
#     result = client.transcribe_file("test_files/test.wav")
#     print(f"识别结果: {result.data.text}")
#     print(f"置信度: {result.data.confidence:.2f}")
#     print(f"耗时: {result.data.processing_time:.3f}s")

