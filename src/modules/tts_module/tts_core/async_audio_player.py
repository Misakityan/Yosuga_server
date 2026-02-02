# tts_core/async_audio_player.py
import asyncio
import io
from loguru import logger
from typing import Optional
import numpy as np
import sounddevice as sd
import wave

class AsyncAudioPlayer:
    """
    异步流式音频播放器
    - 自动检测WAV头并解析采样率
    - 使用环形缓冲区确保播放流畅
    - 支持动态音频格式切换
    """

    def __init__(self, buffer_size: int = 10):
        """
        Args:
            buffer_size: 音频块缓冲数量（越大越稳定，但延迟越高）
        """
        self.audio_queue = asyncio.Queue(maxsize=buffer_size)
        self.sample_rate = 32000  # 默认采样率
        self.channels = 1
        self.dtype = np.float32
        self.stream: Optional[sd.OutputStream] = None
        self.is_playing = False
        self._first_chunk_processed = False
        logger.info(f"🎵 音频播放器初始化，缓冲区大小: {buffer_size}")

    async def add_chunk(self, audio_data: bytes):
        """
        添加音频块到播放队列
        自动处理第一个chunk（包含WAV头）
        """
        try:
            # 第一个chunk需要解析WAV头
            if not self._first_chunk_processed:
                # 写入BytesIO以便wave模块读取
                wav_buffer = io.BytesIO(audio_data)
                try:
                    with wave.open(wav_buffer, 'rb') as wav_file:
                        # 解析WAV头信息
                        self.sample_rate = wav_file.getframerate()
                        self.channels = wav_file.getnchannels()
                        self.sampwidth = wav_file.getsampwidth()

                        # 读取PCM数据（去掉头部）
                        pcm_data = wav_file.readframes(wav_file.getnframes())

                        logger.info(f"📊 解析WAV头: {self.sample_rate}Hz, {self.channels}ch, {self.sampwidth * 8}bit")

                        # 转换为numpy数组
                        if self.sampwidth == 2:
                            audio_array = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
                        elif self.sampwidth == 4:
                            audio_array = np.frombuffer(pcm_data, dtype=np.int32).astype(np.float32) / 2147483648.0
                        else:
                            raise ValueError(f"不支持的采样宽度: {self.sampwidth}")

                        # 转单声道（如果多声道）
                        if self.channels > 1:
                            audio_array = audio_array.reshape(-1, self.channels).mean(axis=1)

                        await self.audio_queue.put(audio_array)
                        self._first_chunk_processed = True

                except wave.Error:
                    # 可能是不完整的WAV头，尝试直接播放
                    logger.warning("⚠️ WAV头解析失败，尝试直接播放")
                    await self._play_raw(audio_data)
                    return
            else:
                # 后续chunk直接播放（RAW PCM）
                await self._play_raw(audio_data)

        except Exception as e:
            logger.error(f"❌ 音频块处理失败: {e}")

    async def _play_raw(self, audio_data: bytes):
        """播放RAW PCM数据"""
        try:
            # 假设是16位PCM（最常见）
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            # 如果是多声道数据（罕见）
            if len(audio_array) % self.channels == 0 and self.channels > 1:
                audio_array = audio_array.reshape(-1, self.channels).mean(axis=1)

            await self.audio_queue.put(audio_array)
        except Exception as e:
            logger.error(f"❌ RAW音频处理失败: {e}")

    async def play_worker(self):
        """后台播放任务"""
        logger.info("🎧 音频播放任务启动")

        while self.is_playing or not self.audio_queue.empty():
            try:
                # 从队列获取音频块（最多等待0.5秒）
                audio_chunk = await asyncio.wait_for(self.audio_queue.get(), timeout=0.5)

                # 延迟初始化音频流（直到获得第一个数据块）
                if self.stream is None:
                    logger.info(f"🔊 打开音频输出流: {self.sample_rate}Hz")
                    self.stream = sd.OutputStream(
                        samplerate=self.sample_rate,
                        channels=1,
                        dtype=self.dtype,
                        blocksize=1024,  # 低延迟模式
                        latency='low'
                    )
                    self.stream.start()

                # 写入音频流播放
                self.stream.write(audio_chunk)

                # 标记任务完成
                self.audio_queue.task_done()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"❌ 播放任务异常: {e}")
                break

        logger.info("🛑 音频播放任务结束")

    async def start(self):
        """启动播放系统"""
        self.is_playing = True
        self._first_chunk_processed = False
        self.play_task = asyncio.create_task(self.play_worker())

    async def stop(self):
        """停止播放并清理资源"""
        self.is_playing = False

        # 等待播放任务结束
        if hasattr(self, 'play_task'):
            await self.play_task

        # 关闭音频流
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        # 清空队列
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except:
                break

        logger.info("✅ 音频播放已停止")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()