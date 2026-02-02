from pydantic import Field, BaseModel
from datetime import datetime, timezone
class AutoAgentDataTransferObject(BaseModel):
    """
    自动化agent数据传输对象
    该对象被用于服务端向客户端发送控制信息
    """
    Action: str = Field(default="", description="自动化动作名称")
    x1: int = Field(default=-1, description="鼠标起始位置x1")
    y1: int = Field(default=-1, description="鼠标起始位置y1")
    x2: int = Field(default=-1, description="鼠标结束位置x2")
    y2: int = Field(default=-1, description="鼠标结束位置y2")
    key: str = Field(default="", description="快捷键")
    content: str = Field(default="", description="输入文本内容")
    direction: str = Field(default="", description="滚动方向")

    def set_dto_data(self, **kwargs) -> "AutoAgentDataTransferObject":
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
            "type": "auto_agent",
            "timestamp": 1672531200.0,
            "data": {
                  "Action": "自动化agent返回的相应的自动化动作名称",
                  "x1": "某个操作的x1，不是所有的操作都有，如果相关的操作没有，写成-1即可，y1,x2,y2也同理",
                  "y1": "某个操作的y1",
                  "x2": "某个操作的x2",
                  "y2": "某个操作的y2",
                  "key": "快捷键，若当前操作没有该字段信息，此处内容为空即可",
                  "content": "输入文本的内容，若当前操作没有该字段信息，此处内容为空即可",
                  "direction": "滚动方向，若当前操作没有该字段信息，此处内容为空即可"
            }
        }
        """
        # model_dump() 是 Pydantic v2 的序列化方法
        payload = self.model_dump()     # 获取所有模型字段
        # 构造嵌套结构
        return {
            "type": "auto_agent",
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "data": payload  # 字段嵌套
        }

    @classmethod
    def from_json(cls, json_data: dict) -> "AutoAgentDataTransferObject":
        """
        从JSON数据创建DTO对象
        传入的json数据格式:
        {
          "type": "auto_agent",
          "Action": "自动化agent返回的相应的自动化动作名称",
          "x1": "某个操作的x1，不是所有的操作都有，如果相关的操作没有，写成-1即可，y1,x2,y2也同理",
          "y1": "某个操作的y1",
          "x2": "某个操作的x2",
          "y2": "某个操作的y2",
          "key": "快捷键，若当前操作没有该字段信息，此处内容为空即可",
          "content": "输入文本的内容，若当前操作没有该字段信息，此处内容为空即可",
          "direction": "滚动方向，若当前操作没有该字段信息，此处内容为空即可"
        }
        """
        payload = json_data
        payload.pop("type", None)   # 移除多余字段
        # 构造对象 Pydantic 自动忽略 type/timestamp
        return cls.model_validate(payload)

