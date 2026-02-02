import asyncio
from src.modules.tts_module.tts_core.gpt_sovits.gpt_sovits_client import GPTSoVITSClient, StreamingMode
from src.modules.tts_module.tts_core.async_audio_player import AsyncAudioPlayer
import sounddevice as sd

test_text = "春の午後、公園のベンチに座って本を読んでいると、小さな子供が凧あげをしているのが目に入った。風に乗って凧が高く上がるたびに、彼の顔には真っすぐな笑顔が広がる。母親がそばで見守りながら、時折声をかけている。\
空は雲一つない青さで、桜の花びらが風に舞っている。遠くで犬の鳴き声が聞こえ、芝生の上では老夫婦がお茶を楽しんでいた。すべてがゆっくりと流れる時間の中で、自分の心も不思議と落ち着いてくる。\
ふと、子供の凧が木の枝に引っかかってしまった。少し焦る様子だったが、母親が助けてくれて、すぐにまた空に舞い上がった。失敗しても、誰かが助けてくれる。そんな当たり前のことに、今日は特別な温かさを感じた。\
日が傾き始める頃、私は本を閉じて家路についた。明日もきっと、誰かの笑顔があるだろう。"

async def test_tts():
    # 创建客户端（推荐上下文管理器）
    async with GPTSoVITSClient(debug=True, port= 20261, host="192.168.1.8") as client:
        # 基础TTS调用
        try:
            audio = await client.tts(
                text="あのさ、いやまあ、なんていうか...要するに、そういうことじゃなくて、ほら、前に言ってたやつ、あれなんだけど、とにかく、後ででもいいから、ちょっと相談に乗ってくれない？",
                ref_audio_path="uploaded_audio/test_voice.wav",  # 服务器上的路径
                text_lang="ja",
                prompt_lang="ja",
                media_type="wav",
                prompt_text="もう!こんなところで何やってるんだよ!"
            )

            # 保存音频
            audio.save("outputs/output.wav")
            print(f"✅ TTS成功！音频大小: {len(audio.audio_data)} bytes")

        except Exception as e:
            print(f"❌ 错误: {e}")
async def test_model_change():
    async with GPTSoVITSClient(debug=True, port= 20261, host="192.168.1.8") as client:
        # 切换模型
        print("🔄 切换GPT模型...")
        await client.set_gpt_weights(
            "GPT_weights_v2Pro/Yosuga_Airi-e32.ckpt"
        )

        print("🔄 切换SoVITS模型...")
        await client.set_sovits_weights(
            "SoVITS_weights_v2Pro/Yosuga_Airi_e16_s864.pth"
        )


async def stream_tts():
    async with GPTSoVITSClient(debug=True, port= 20261, host="192.168.1.8") as client:
        try:
            # 使用最快模式流式输出
            chunk_count = 0
            async for chunk in await client.tts(
                    text="要するに、そういうことじゃなくて、ほら、前に言ってたやつ、あれなんだけど、とにかく、後ででもいいから、ちょっと相談に乗ってくれない？",
                    ref_audio_path="uploaded_audio/test_voice.wav",
                    text_lang="ja",
                    prompt_lang="ja",
                    prompt_text="もう!こんなところで何やってるんだよ!",
                    streaming_mode=StreamingMode.FASTEST,  # 模式3：快速流式
                    media_type="wav"
            ):
                chunk_count += 1
                print(f"🎵 收到音频块 #{chunk_count}: {len(chunk.audio_data)} bytes")

                # 实时播放处理
                # await play_audio_chunk(chunk.audio_data)

            print(f"✅ 流式TTS完成！共{chunk_count}个音频块")

        except Exception as e:
            print(f"❌ 流式错误: {e}")


async def stream_tts_and_play(
        text: str,
        ref_audio_path: str,
        text_lang: str = "zh",
        prompt_lang: str = "zh",
        streaming_mode: StreamingMode = StreamingMode.FASTEST
):
    """
    实时流式TTS + 播放一体化

    Args:
        text: 要合成的文本
        ref_audio_path: 参考音频路径
        text_lang: 文本语言
        prompt_lang: 提示语言
    """
    # 创建音频播放器（缓冲区大小=5，平衡延迟和稳定性）
    async with AsyncAudioPlayer(buffer_size=5) as player:
        # 创建TTS客户端
        async with GPTSoVITSClient(debug=True, port= 20261, host="192.168.1.8") as client:
            try:
                print(f"🎤 开始流式合成: {text[:30]}...")
                print(f"🎯 流式模式: {streaming_mode.name}")

                # 获取音频流（异步生成器）
                audio_stream = await client.tts(
                    text=text,
                    ref_audio_path=ref_audio_path,
                    text_lang=text_lang,
                    prompt_lang=prompt_lang,
                    prompt_text="もう!こんなところで何やってるんだよ!",
                    streaming_mode=streaming_mode,
                    media_type="wav",
                    sample_steps=32,
                    top_k=5,
                    temperature=1.0
                )

                # 动态读取并播放
                chunk_idx = 0
                async for audio_chunk in audio_stream:
                    chunk_idx += 1
                    print(f"📥 收到音频块 #{chunk_idx}: {len(audio_chunk.audio_data):6d} bytes")

                    # 立即加入播放队列（非阻塞）
                    await player.add_chunk(audio_chunk.audio_data)

                print(f"✅ 合成完成! 共接收 {chunk_idx} 个音频块")

                # 等待播放完成（所有块播完）
                await player.audio_queue.join()
                print("🎵 播放完成!")

            except Exception as e:
                print(f"❌ 错误: {e}")
                raise


async def test_japanese():
    """测试日语长文本流式播放"""
    print("=" * 50)
    print("🗾 日语流式TTS测试")
    print("=" * 50)

    await stream_tts_and_play(
        text=test_text,
        ref_audio_path="uploaded_audio/test_voice.wav",
        text_lang="ja",
        prompt_lang="ja",

        streaming_mode=StreamingMode.FASTEST  # 模式3：最快
    )

async def batch_test():
    """批量处理示例"""
    async with GPTSoVITSClient() as client:
        texts = [
            "你好，世界！",
            "这是一个批量测试。",
            "异步批量处理非常高效。"
        ]

        results = await client.batch_tts(
            texts=texts,
            ref_audio_path="archive_jingyuan_1.wav",
            text_lang="zh"
        )

        for i, audio in enumerate(results):
            audio.save(f"output/batch_{i}.wav")
            print(f"✅ 批量任务 {i + 1}/{len(results)} 完成")





if __name__ == "__main__":
    # 检查音频设备
    print("🔍 检查音频设备...")
    print(sd.query_devices())
    sd.default.device = (None, "pulse")  # 使用PulseAudio

    asyncio.run(test_japanese())