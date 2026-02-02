import asyncio
import base64
from pathlib import Path
from src.modules.device_control_module.device_control_core.ui_tars_.ui_tars_client import UITarsClient, UITarsClientConfig


async def test_ui_tars_stream():
    """测试 UI-TARS 流式调用"""
    # 创建客户端
    config = UITarsClientConfig(
        deployment_type="lmstudio",
        base_url="http://192.168.1.8:1234/v1",
        model_name="ui-tars-1.5-7b@q4_k_m",
        temperature=0.1
    )
    client = UITarsClient(config)

    # 使用工具方法编码
    image_base64 = base64.b64encode(Path("test_files/Screenshot_test.png").read_bytes()).decode()
    print(f"✅ 图片编码完成，长度: {len(image_base64)} 字符\n")

    # 流式调用并实时打印
    print("🤖 开始流式调用 UI-TARS...\n")
    print("思考过程:\n")

    import time
    # 计算耗时
    start_time = time.time()
    full_response = ""
    chunk_count = 0

    full_response = await client.call_async("打开AK加速器", image_base64)
    # 传入 base64 字符串
    # for chunk in client.stream_async("我的桌面系统是KDE, 帮我打开设置", image_base64):
    #     chunk_count += 1
    #     content = chunk.content
    #
    #     # 实时打印每个 chunk
    #     print(content, end="", flush=True)
    #
    #     # 累积完整内容
    #     full_response += content

    end_time = time.time()
    print(f"\n\n耗时: {end_time - start_time:.2f} 秒")
    print(f"\n\n{'=' * 50}")
    print(f"✅ 流式调用完成！共接收 {chunk_count} 个 chunk")
    print(f"完整响应长度: {len(full_response)} 字符")

    print("响应内容:\n")
    print(full_response)

import pyautogui
def auto_click(x : int, y : int):
    pyautogui.moveTo(x, y, duration=1.5)
    pyautogui.click()

def auto_drag(x1 : int, y1 : int, x2 : int, y2 : int):
    pyautogui.moveTo(x1, y1, duration=1.5)
    pyautogui.dragTo(x2, y2, duration=1.5)

# 运行异步函数
if __name__ == "__main__":
    asyncio.run(test_ui_tars_stream())
    auto_click(173,48)
    # auto_drag(56,39, 170,39)