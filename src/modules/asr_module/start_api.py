# start_api.py
import uvicorn
from loguru import logger
import threading
import time

def start_server():
    """启动 ASR API 服务"""
    uvicorn.run(
        "api:app",  # 模块名:app实例
        host="0.0.0.0",
        port=20260,
        workers=1,  # 单用户场景，1个worker足够
        log_level="info",
        reload=False,  # 生产环境关闭热重载
        access_log=True,
    )

def first_test() -> None:
    """首次启动测试"""
    time.sleep(5)   # 给服务器一些启动时间
    # 构造一个测试请求以验证初始化模型加载成功
    logger.info("测试模型是否加载成功...")
    import requests
    from pathlib import Path
    url = "http://localhost:20260/transcribe"
    audio_path = Path("../../../Test/test_files/test.wav")
    try:
        with open(audio_path, "rb") as f:
            # 明确指定文件名和 MIME 类型
            files = {
                "file": (
                    audio_path.name,  # 文件名
                    f,  # 文件对象
                    "audio/wav"  # MIME 类型
                )
            }

            response = requests.post(url, files=files)
        logger.info(f"状态码: {response.status_code}")
        logger.info(f"响应头: {response.headers.get('content-type')}")
        if response.status_code == 200:
            result = response.json()
            logger.info(f"识别结果: {result['data']['text']}")
            logger.info(f"识别语言: {result['data']['language']}")
            logger.info(f"置信度: {result['data']['confidence']:.2f}")
            logger.info(f"处理时间: {result['data']['processing_time']}s")
        else:
            logger.error(f"请求失败，错误响应信息: {response.text}")
            logger.error("请检查模型是否正确加载或其他问题")
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")

if __name__ == "__main__":
    logger.info("启动 ASR API 服务...")

    # 在后台线程启动服务器
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # 执行测试
    first_test()

    # 保持主线程运行
    server_thread.join()
