from pydantic import Field, BaseModel
from datetime import datetime, timezone
class ScreenShotDataTransferObject(BaseModel):
    """
    服务端向客户端请求实时截图的数据传输对象
    服务端与客户端收发对等(通过Owner标识)
    客户端收到这个type的包，就会自动对当前设备的画面进行截图
    """
    Owner: str = Field(default="server", description="数据的拥有者(server or client)")
    isSuccess: bool = Field(default=False, description="是否截图成功")
    RealTimeScreenShot: str = Field(default="", description="客户端设备的实时截图数据(base64)")
    Width: int = Field(default=1920, description="截图的宽度")
    Height: int = Field(default=1080, description="截图的高度")
    DescribeInfo: str = Field(default="", description="设备的描述信息(告知模型以做出更加准确的判断)")
    LLMResponse: str = Field(default="", description="LLM的响应结果(由服务端发送时携带)")


    def set_dto_data(self, **kwargs) -> "ScreenShotDataTransferObject":
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
            "type": "screenshot_data",
            "timestamp": 1672531200.0,
            "data": {
                  "Owner": "数据的拥有者(server or client)",
                  "isSuccess": "是否截图成功(true or false)"
                  "RealTimeScreenShot": "客户端设备的实时截图数据(base64)",
                  "Width": "截图的宽度",
                  "Height": "截图的高度",
                  "DescribeInfo": "设备的描述信息(告知模型以做出更加准确的判断)",
                  "LLMResponse": "LLM的响应结果(由服务端发送时携带)"
            }
        }
        """
        # model_dump() 是 Pydantic v2 的序列化方法
        payload = self.model_dump()     # 获取所有模型字段
        # 构造嵌套结构
        return {
            "type": "screenshot_data",
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "data": payload  # 字段嵌套
        }

    @classmethod
    def from_json(cls, json_data: dict) -> "ScreenShotDataTransferObject":
        """
        从JSON数据创建DTO对象
        传入的json数据格式:
        {
          "Owner": "数据的拥有者(server or client)",
          "isSuccess": "是否截图成功(true or false)",
          "RealTimeScreenShot": "客户端设备的实时截图数据(base64)",
          "Width": "截图的宽度 非必要字段",
          "Height": "截图的高度 非必要字段",
          "DescribeInfo": "设备的描述信息(告知模型以做出更加准确的判断) 非必要字段",
          "LLMResponse": "LLM的响应结果(由服务端发送时携带) 必要字段"
        }
        """
        payload = json_data
        payload.pop("type", None)           # 移除多余字段
        payload.pop("timestamp", None)      # 移除多余字段
        # 构造对象 Pydantic 自动忽略 type/timestamp
        return cls.model_validate(payload)

