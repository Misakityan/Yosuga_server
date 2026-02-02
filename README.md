### Yosuga_server

## 📊 Project Stats

![GitHub last commit](https://img.shields.io/github/last-commit/Misakityan/Yosuga_server)
![GitHub issues](https://img.shields.io/github/issues/Misakityan/Yosuga_server)
![GitHub stars](https://img.shields.io/github/stars/Misakityan/Yosuga_server?style=social)

欢迎访问本项目。

首先向你介绍一下Yosuga这个项目：

本项目的作者是Misakiotoha(みさきおとは[見崎音羽])。[call me "Misaki" でいいよ]

之所以叫Yosuga，这个词来源日语当中的单词"縁"的发音，其意思是"缘分，关系"。

本项目分为三个部分：
1. Yosuga：这是项目的前端部分，是Yosuga与用户交互的一层，采用C++20 + Qt6.6.3编写，使用到的核心外部库为Live2D For C++ SDK。
2. Yosuga_server：这是项目的后端部分，是Yosuga的核心，采用python3.11编写，使用到的外部库较多，负责联系项目的各个部分。
3. Yosuga_embedded：这是项目的拓展部分，使得Yosuga对嵌入式设备拥有几乎完全的自定义控制能力，采用C语言编写，只使用到了cJSON库，平台无关，增强了Yosuga与外界的交互能力。

**_本项目为Yosuga_server._**

本项目使用uv构建，基于python3.11. 
本项目由YosugaServer发展而来，项目架构与代码有了相当大的改变。(YosugaServer并未开源，它仅仅是一次小小的尝试)


### 如何快速启动本项目？
1. 确保uv已安装，并添加到环境变量中
2. 执行`cd Yosuga_server` & `uv sync`
3. 接着，如果你的电脑带有cuda，那么执行 `uv pip install -r requirements-cuda.txt`
4. 如果没有cuda，那么执行 `uv pip install -r requirements-cpu.txt`
5. 最后执行 `uv run python main.py` 即可启动项目

首次启动项目后，会在项目根目录下生成settings.json配置文件，你需要配置一些必要的字段信息：
```json
{
  "ai": {
    "api_key": "sk-xxxxx",
    "base_url": "http://localhost:1234/v1",
    "model_name": "qwen/qwen3-4b-2507"
  },
  "tts": {
    "gpt_model_name": "GPT_weights_v2Pro/Yosuga_Airi-e32.ckpt",
    "sovits_model_name": "SoVITS_weights_v2Pro/Yosuga_Airi_e16_s864.pth",
    "host": "localhost",
    "port": 20261,
    "reference_audio": "./using/reference.wav"
  },
  "asr": {
    "url": "http://localhost:20260/"
  },
  "auto_agent": {
    "deployment_type": "lmstudio",
    "model_name": "ui-tars-1.5-7b@q4_k_m",
    "base_url": "http://localhost:1234/v1"
  },
  "llm_core": {
    "role_character": "你是由Misakiotoha开发的助手稲葉愛理ちゃん，可以和用户一起玩游戏，聊天，做各种事情，性格抽象，没事爱整整活。",
    "max_context_tokens": 2048,
    "language": "日本语"
  }
}
```
上面这些字段的信息，你需要根据你的实际情况进行配置。实际的配置文件的字段名称会比上面的多出不少。


配置完成后，再次重启服务端就可以使用啦~

接着是每个模型的配置相关：
1. asr模型，本项目使用fast-whisper作为asr模型，并且附带了一键启动的部分
，你需要找到 `Yosuga_server/src/modules/asr_module/start_api.py` 这个文件，然后启动它
，一般来说，即使是cpu也可以进行asr模型的推理，但是速度相比cuda要逊色很多。
同时，如果你遇到了启动时长时间加载，那么此时你需要试着挂一下梯子，因为初次启动
会在Hugging Face上下载模型。
2. tts模型，本项目使用GPT-SoVITS作为tts模型，建议使用其V2Pro版本。
3. auto_agent模型，本项目使用的自动化操作识别的模型为字节跳动开源的
`ui-tars-1.5-7b@q4_k_m` 关于此模型的更多信息可以参考字节跳动的[开源链接](https://github.com/bytedance/UI-TARS)
，建议在LM Studio上进行部署，该模型十分轻量。
4. ai模型，该模型限制为大语言模型，没有限制，本项目支持市面上的所有大语言模型。


本项目当前并不完善，还有很多需要优化的地方，并且尚未接入Yosuga_embedded。

欢迎大家为本项目贡献代码。