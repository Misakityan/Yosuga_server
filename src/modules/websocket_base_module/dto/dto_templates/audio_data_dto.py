from pydantic import Field, BaseModel
import base64
from datetime import datetime, timezone
class AudioDataTransferObject(BaseModel):
    """
    音频数据传输对象
    该对象被用于服务端与客户端的音频数据交互
    同时支持流式与非流式的音频数据
    同时收发对等(通过Owner标识)
    """
    Owner: str = Field(default="server", description="音频数据的拥有者(server or client)")
    isStream: bool = Field(default=False, description="音频数据是否为流式数据")
    isStart: bool = Field(default=False, description="音频数据是否开始(流式时有效)")
    isEnd: bool = Field(default=False, description="音频数据是否结束(流式时有效)")
    sequence: int = Field(default=0, description="音频数据块序列号(流式时有效)")
    data: bytes = Field(default=b"", description="音频数据，流式时为分块数据，base64编码")
    sampleRate: int = Field(default=32000, description="音频采样率")
    channelCount: int = Field(default=1, description="音频通道数")
    bitDepth: int = Field(default=16, description="音频采样位数")
    duration: float = Field(default=0.0, description="音频时长")
    text: str = Field(default="", description="音频对应的文本")

    def set_dto_data(self, **kwargs) -> "AudioDataTransferObject":
        """链式更新数据（Pydantic 风格）"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self

    def to_json(self) -> dict:
        """
        将DTO对象转换为可序列化字典
        返回的json数据的格式:
        {
            "type": "audio_data",
            "timestamp": 1672531200.0,
            "data": {
                "Owner": "server",
                ......
            }
        }
        """
        # model_dump() 是 Pydantic v2 的序列化方法
        payload = self.model_dump()     # 获取所有模型字段
        payload["data"] = base64.b64encode(payload["data"]).decode()    # base64编码
        # 构造嵌套结构
        return {
            "type": "audio_data",
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "data": payload  # 音频字段嵌套
        }

    @classmethod
    def from_json(cls, json_data: dict) -> "AudioDataTransferObject":
        """
        从JSON数据创建DTO对象
        传入的json数据格式:
        {
            "Owner": "server",
            ......
        }
        """
        payload = json_data
        # 解码 base64 (内层 data 字段在传输时是 base64 字符串) ->  bytes
        if "data" in payload and isinstance(payload["data"], str):
            payload["data"] = base64.b64decode(payload["data"])
        # 构造对象 Pydantic 自动忽略 type/timestamp
        return cls.model_validate(payload)


# 测试代码
if __name__ == "__main__":
    # 模拟音频数据
    import os

    test_audio = os.urandom(1024)  # 随机生成1KB音频数据

    # 创建DTO
    audio = AudioDataTransferObject(
        data=test_audio,
        sequence=1,
        isStream=True,
        sampleRate=44100,
        duration=0.5
    )

    # 序列化 → JSON
    json_dict = audio.to_json()
    print(f"序列化后 data 长度: {len(json_dict['data'])}")  # ~1368 字符
    print(f"data 前30字符: {json_dict['data'][:30]}...")

    # 反序列化 → DTO
    restored = AudioDataTransferObject.from_json(json_dict)
    print(f"反序列化后 data 长度: {len(restored.data)}")  # 1024 bytes
    print(f"数据一致: {restored.data == test_audio}")  # True
