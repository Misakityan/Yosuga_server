# requestTest.py
import requests
from pathlib import Path

# 指定正确的 MIME 类型
url = "http://192.168.1.8:20260/transcribe"
audio_path = Path("test_files/z105300938.wav")

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

# 打印响应详情
print(f"状态码: {response.status_code}")
print(f"响应头: {response.headers.get('content-type')}")

# 检查响应是否成功
if response.status_code == 200:
    result = response.json()
    print(f"识别结果: {result['data']['text']}")
    print(f"语言: {result['data']['language']}")
    print(f"置信度: {result['data']['confidence']}")
    print(f"处理时间: {result['data']['processing_time']}s")
else:
    print(f"错误响应: {response.text}")