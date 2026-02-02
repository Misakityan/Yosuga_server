from src.modules.text_ai_module.text_ai_core.general_text_ai_req import UnifiedLLM, ModelConfig, ModelProvider, create_llm_client
from src.config.config import get_settings
from src.config.convert_env import EnvConverter
from src.config.file_config import DirectoryInitializer

EnvConverter().convert(backup_existing=True)    # 若是首次启动则从env模板中生成env文件
DirectoryInitializer(get_settings())            # 初始化必要的目录(若不存在则创建)

def test1():
    """
    测试常规调用
    """
    # 配置模型
    config = ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name=get_settings().ai_model_name,
        base_url=get_settings().ai_api_base_url,
        api_key=get_settings().ai_api_key,  # 从环境中取出相关的api_key
        temperature=0.7,
        max_tokens=2048
    )

    # 创建客户端
    llm = UnifiedLLM(config)

    # 发送消息
    response = llm.chat([
        {"role": "system", "content": "你是一个DeepSeek助手"},
        {"role": "user", "content": "请介绍一下DeepSeek模型的特点"}
    ])

    print(response.content)

def base_test2():
    """
    测试流式响应
    """
    # 使用快捷函数
    deepseek_llm = create_llm_client(
        provider="openai",  # DeepSeek使用OpenAI兼容接口
        model_name=get_settings().ai_model_name,
        api_key=get_settings().ai_api_key,
        base_url=get_settings().ai_api_base_url
    )

    # 流式聊天
    messages = [
        {"role": "user", "content": "用Python写一个快速排序算法"}
    ]

    print("正在生成响应...")
    for chunk in deepseek_llm.stream_chat(messages):
        print(chunk.content, end="", flush=True)


def test_lm_studio():
    """测试本地 LM Studio 模型"""
    print("=== 测试本地 LM Studio ===")

    # 使用UnifiedLLM类
    config = ModelConfig(
        provider=ModelProvider.LM_STUDIO,
        model_name="qwen/qwen3-4b-2507",
        base_url="http://192.168.1.8:1234/v1",
        api_key="",  # LM Studio不需要API密钥，留空
        temperature=0.7,
        max_tokens=1024,
        streaming=False  # 启用流式响应
    )

    llm = UnifiedLLM(config)

    # 发送消息
    messages = [
        {"role": "system", "content": "你是一个有用的助手"},
        {"role": "user", "content": "用中文介绍一下自己"}
    ]

    print("非流式响应:")
    response = llm.chat(messages, streaming=False)
    print(response.content)

    print("\n流式响应:")
    for chunk in llm.stream_chat(messages):
        print(chunk.content, end="", flush=True)

if __name__ == "__main__":
    test_lm_studio()