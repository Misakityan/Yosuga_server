# llm_core/llm_core_analysis.py

"""
LLM输出解析与序列化模块
将LLM返回的JSON字符串智能解析为强类型Python对象，供其他模块直接调用
支持多类型混合响应，自动路由到对应数据模型
"""

import json
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Optional, Type, List
from pydantic import BaseModel, Field, ValidationError, field_validator
from loguru import logger
import re

# 抽象基类
class LLMCoreAnalysisBase(BaseModel, ABC):
    """
    LLM输出数据模型抽象基类
    各场景通过继承定义具体的数据结构
    """

    # 解析器type标识
    type: str = Field(..., description="场景类型标识")

    @classmethod
    @abstractmethod
    def type_(cls) -> str:
        """返回该模型对应的场景类型标识"""
        pass

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        返回该场景的数据结构schema
        用于生成system prompt中的{OutputInfo}
        """
        return cls.model_json_schema()

# 管理器
class LLMCoreAnalysisManager:
    """
    LLM输出解析管理器
    智能路由：根据JSON中的type_字段，自动选择对应模型进行解析
    """

    # 类变量：存储所有注册的数据模型类
    _model_registry: ClassVar[Dict[str, Type[LLMCoreAnalysisBase]]] = {}

    @classmethod
    def register(cls, model_class: Type[LLMCoreAnalysisBase]) -> None:
        """
        注册场景数据模型类

        Args:
            model_class: 继承自LLMCoreAnalysisBase的数据模型类

        Example:
            LLMCoreAnalysisManager.register(YosugaAudioResponseData)
        """
        type_id = model_class.type_()
        cls._model_registry[type_id] = model_class
        logger.info(f"已注册LLM数据输出解析模型: {type_id} -> {model_class.__name__}")

    @classmethod
    def parse(cls, json_str: str) -> List[LLMCoreAnalysisBase]:
        """
        统一解析入口：无论单对象还是数组，总是返回对象列表

        Args:
            json_str: LLM原始JSON字符串（支持markdown代码块）

        Returns:
            解析后的模型实例列表，顺序与JSON数组一致

        Raises:
            ValidationError: 格式校验失败
            ValueError: JSON解析失败
        """
        print(f"待解析的内容为(llm本次输出原生内容)：{json_str}")   # TODO:delete

        cleaned = cls._clean_markdown(json_str)     # 清理markdown标记
        try:
            data = json.loads(cleaned)
            # 统一包装成列表
            if not isinstance(data, list):
                data = [data]
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}\n原始输出: {cleaned[:200]}...")
            raise ValueError(f"无效的JSON格式: {e}")

        results: List[LLMCoreAnalysisBase] = []
        for idx, item in enumerate(data):
            type_id = item.get("type")
            if not type_id:
                logger.warning(f"跳过第{idx}个元素（无type字段）: {item}")
                continue

            if type_id not in cls._model_registry:
                logger.warning(f"未注册的类型 '{type_id}'，可用类型: {list(cls._model_registry.keys())}")
                continue

            model_class = cls._model_registry[type_id]
            try:
                # 重新序列化为字符串再解析（保持接口兼容）
                item_json = json.dumps(item, ensure_ascii=False)
                result = model_class.model_validate_json(item_json)
                results.append(result)
            except ValidationError as e:
                logger.error(f"第{idx}个对象校验失败 (type={type_id}): {e}")
                continue
            except Exception as e:
                logger.error(f"第{idx}个对象解析失败 (type={type_id}): {e}")
                continue

        logger.success(f"解析完成 | 成功: {len(results)}/{len(data)}")
        return results

    @staticmethod
    def _clean_markdown(json_str: str) -> str:
        # 尝试找到第一个 '[' 和最后一个 ']'
        start = json_str.find('[')
        end = json_str.rfind(']')
        if start != -1 and end != -1:
            return json_str[start:end + 1]
        return json_str  # Fallback

# 具体场景数据模型
class YosugaAudioResponseData(LLMCoreAnalysisBase):
    """
    音频ASR场景的LLM输出数据模型

    使用示例:
        LLMCoreAnalysisManager.register(YosugaAudioResponseData)
        data = YosugaAudioResponseData.parse_raw('{"type_": "audio_text", "response_text": "你好"}')
        data.response_text  # 直接属性访问
        '你好'
        data.emotion  # 默认值
        'neutral'
    """

    type: str = Field(default="audio_text", description="固定为audio_text")
    response_text: str = Field(..., description="回复文本")
    emotion: str = Field(default="neutral", description="情感基调")
    action: str = Field(default="none", description="动作指令")

    @classmethod
    def type_(cls) -> str:
        return "audio_text"

class YosugaUITARSResponseData(LLMCoreAnalysisBase):
    """
    自动化操作场景的LLM输出数据模型
    """

    type: str = Field(default="auto_agent", description="固定为auto_agent")
    Action: str = Field(..., description="动作名称")
    x1: Optional[int] = Field(default=None, description="起点x")
    y1: Optional[int] = Field(default=None, description="起点y")
    x2: Optional[int] = Field(default=None, description="终点x")
    y2: Optional[int] = Field(default=None, description="终点y")
    key: Optional[str] = Field(default="", description="快捷键")
    content: Optional[str] = Field(default="", description="输入文本")
    direction: Optional[str] = Field(default="", description="滚动方向")

    @classmethod
    def type_(cls) -> str:
        return "auto_agent"

    @field_validator('x1', 'y1', 'x2', 'y2', mode='before')
    @classmethod
    def convert_optional_int(cls, v: Any) -> Optional[int]:
        """
        将字符串类型的坐标值转换为 int，空字符串转为 None

        Args:
            v: 原始值（可能是 str, int, None）

        Returns:
            Optional[int]: 转换后的值
        """
        if v is None:
            return None
        if isinstance(v, str):
            # 处理空字符串
            if v.strip() == "":
                return None
            # 尝试转换为 int
            try:
                return int(v)
            except ValueError:
                logger.warning(f"无法将字符串 '{v}' 转换为 int，返回 None")
                return None
        if isinstance(v, int):  # 如果原始值本身就是int类型，直接return
            return v
        if isinstance(v, float):    # 如果解析出了float,强转成int再return
            return int(v)

        logger.warning(f"意外的类型 {type(v)}，返回 None")
        return None

    def to_dict(self) -> dict:
        """
        将模型转换为字典，用于生成JSON字符串

        Returns:
            dict: 模型数据字典
        """
        return {
            "type": self.type,
            "Action": self.Action,
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "key": self.key,
            "content": self.content,
            "direction": self.direction
        }

class YosugaUITARSRequestData(LLMCoreAnalysisBase):
    """
    自动化操作场景的LLM对自动化agent的调用的输出解析模型
    """

    type: str = Field(default="call_auto_agent", description="固定为call_auto_agent")
    llm_translation: str = Field(default="", description="针对用户的意图的转译，如果用户的意图足够明确，直接照抄即可")

    @classmethod
    def type_(cls) -> str:
        return "call_auto_agent"




class YosugaLive2DResponseData(LLMCoreAnalysisBase):
    """
    Live2D控制场景的LLM输出数据模型    TODO
    """

    type: str = Field(default="live2d_control", description="固定为live2d_control")
    parameter: str = Field(..., description="参数名")
    value: float = Field(..., description="目标值")
    duration: int = Field(default=500, description="过渡时间(ms)")

    @classmethod
    def type_(cls) -> str:
        return "live2d_control"

class YosugaEmbeddedResponseData(LLMCoreAnalysisBase):
    """
    嵌入式设备场景的LLM输出数据模型
    LLM输出 JSON-RPC 风格的函数调用，由服务端解析并路由到对应设备
    """

    type: str = Field(default="embedded_control", description="固定为embedded_control")
    calls: list[dict] = Field(default_factory=list, description="JSON-RPC 调用列表，每项含 method/params/id")
    response_text: str = Field(default="", description="同时回复给用户的文本（可选）")

    @classmethod
    def type_(cls) -> str:
        return "embedded_control"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "calls": self.calls,
            "response_text": self.response_text
        }

# 使用示例
if __name__ == "__main__":
    from loguru import logger

    # 注册所有数据模型
    LLMCoreAnalysisManager.register(YosugaAudioResponseData)
    LLMCoreAnalysisManager.register(YosugaUITARSResponseData)
    LLMCoreAnalysisManager.register(YosugaLive2DResponseData)
    LLMCoreAnalysisManager.register(YosugaEmbeddedResponseData)

    logger.info("=== LLM输出解析模块测试 ===")

    # 测试单对象解析
    print("\n【测试1：单对象自动识别】")
    llm_output = '''
    ```json
    [{
      "type": "audio_text",
      "response_text": "收到！我会微笑回应",
      "emotion": "cheerful"
    }]
    ```
    '''

    response = LLMCoreAnalysisManager.parse(llm_output)
    print(f"类型: {response}")

    # 3. 测试多对象解析
    print("\n【测试2：多对象混合响应】")
    multi_output = '''
    ```json
    [
      {
        "type": "auto_agent",
        "Action": "click",
        "x1": "100",
        "y1": "200"
      },
      {
        "type": "live2d_control",
        "parameter": "ParamEyeLOpen",
        "value": 0.8,
        "duration": 300
      }
    ]
    ```
    '''

    results = LLMCoreAnalysisManager.parse(multi_output)
    print(f"类型: {results}")