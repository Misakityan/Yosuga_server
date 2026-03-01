# llm_core/llm_core_prompt_manager.py

"""
llm prompt 结构化信息管理
用于将各种输入到llm_core的数据流结构化，并附加注释，以方便llm可以准确的理解并可以结构化返回相关内容
"""
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field, field_validator
from typing import Callable, List, Optional, Coroutine, Any, ClassVar, Dict
from src.server_core.llm_core.llm_core_prompts import YOSUGA_SYSTEM_PROMPT_SCH

class LLMCorePromptBase(BaseModel, ABC):
    """LLM 提示词基类：定义输入输出结构"""
    @abstractmethod
    def type(self) -> str:
        """返回该提示词类型的唯一标识"""
        pass

    @abstractmethod
    def describe_input(self) -> str:
        """生成输入格式的自然语言描述（填充到 {InputInfo}）"""
        pass

    @abstractmethod
    def describe_output(self) -> str:
        """生成输出格式的自然语言描述（填充到 {OutputInfo}）"""
        pass

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_data: str):
        return cls.model_validate_json(json_data)


class LLMCorePromptManager(LLMCorePromptBase):
    """聚合所有子类，生成完整的 prompt 信息"""
    # 类变量：存储所有注册的子类
    _registry: ClassVar[Dict[str, LLMCorePromptBase]] = {}

    def get_registry_size(self) -> int:
        return len(self._registry)

    def register(self, son: LLMCorePromptBase) -> None:
        self._registry[son.type()] = son

    def type(self) -> str:
        return "manager"

    def describe_input(self) -> str:
        """聚合所有子类的输入描述"""
        return "\n".join(
            f"[{type_id}]{son.describe_input()}\n"
            for type_id, son in self._registry.items()
        )

    def describe_output(self) -> str:
        """聚合所有子类的输出描述"""
        return "\n".join(
            f"[{type_id}]{son.describe_output()}\n"
            for type_id, son in self._registry.items()
        )

class YosugaAudioASRText(LLMCorePromptBase):
    """音频ASR文本输入场景"""
    def type(self) -> str:
        return "用户语音asr信息"

    def describe_input(self) -> str:
        return '''
                当用户通过语音与Yosuga交互时，你会收到如下JSON结构：
                {
                  "text": "用户说的话（字符串）",
                  "confidence": 0.95
                }
                - `text`: 语音转写的原始文本，可能包含口语化表达或识别错误
                - `confidence`: ASR引擎的识别置信度，低于0.8需警惕识别错误
                '''

    def describe_output(self) -> str:
        return '''
                针对用户音频识别出的文本内容输入，你应该按以下JSON格式回复：
                {
                  "type": "固定为audio_text",
                  "response_text": "你的回复文本（字符串）",
                  "emotion": "neutral",
                  "action": "none"
                }
                - `response_text`: 给用户的自然语言回复
                - `emotion`: 回复的情感基调，可选值：neutral/cheerful/sad/angry
                - `action`: 触发的动作指令，如"wave_hand"、"nod"等，"none"表示无动作
                '''

class YosugaEmbedded(LLMCorePromptBase):
    """嵌入式设备输入场景"""
    def type(self) -> str:
        pass

    def describe_input(self) -> str:
        pass

    def describe_output(self) -> str:
        pass

class YosugaUITARS(LLMCorePromptBase):
    """自动化操作构建场景"""
    def type(self) -> str:
        return "自动化操作信息"

    def describe_input(self) -> str:
        return '''
            当你尝试调用自动化agent的时候，自动化agent将会返回下面的内容作为输入给你，自动化agent的返回信息很重要，有的任务不是一次就可以完成的，此时你可能需要多次调用自动化agent,直到agent返回finished(任务完成)：
            {
                "auto_agent":"
                Thought: 自动化agent的推理过程，可以考虑二次加工后作为回复用户的内容
                Action: 对应的自动化动作[包括click(单击坐标), left_double(双击坐标), right_single(右键单击), drag(拖拽), hotkey(快捷键), type(输入文本), scroll(滚动), wait(等待), finished(任务完成)]
                "
            }
        '''

    def describe_output(self) -> str:
        return '''
            1. 当用户试图进行一些自动化操作时，你可以通过返回以下json来调用自动化agent，调用的时候也可以一并回复用户一些文本内容：
                {
                    "type": "固定为call_auto_agent",
                    "llm_translation": "针对用户的意图的转译，如果用户的意图足够明确，直接照抄即可，注意转译的语言必须是英语(English)，可以混合部分中文(例如应用名称)，这个和聊天交流使用的语言不统一。"
                }
            2. 针对自动化agent操作输入，你应该按以下JSON格式回复。如果你发起了自动化agent请求之后，却没有返回下面的JSON内容，那么你的请求并不会作用到用户的设备，所以你调用完自动化agent一定要及时返回下面的JSON内容：
                {
                  "type": "固定为auto_agent",
                  "Action": "自动化agent返回的相应的自动化动作名称",
                  "x1": "某个操作的x1，不是所有的操作都有，如果相关的操作没有，写成-1即可，y1,x2,y2也同理",
                  "y1": "某个操作的y1",
                  "x2": "某个操作的x2",
                  "y2": "某个操作的y2",
                  "key": "快捷键，若当前操作没有该字段信息，此处内容为空即可",
                  "content": "输入文本的内容，若当前操作没有该字段信息，此处内容为空即可",
                  "direction": "滚动方向(down or up)，若当前操作没有该字段信息，此处内容为空即可，同时需要关心自动化agent回复的x1,和y1坐标"
                }
            自动化agent返回的操作信息不一定包括JSON的全部字段，例如某次返回只有key的内容，或者只有content的内容。
            针对自动化agent操作输入的返回，若没有相关内容可以留空相关字段，请不要省略掉任何字段名称。
            
            注意：自动化agent的状态可见YosugaSystemState表。
        '''

class YosugaLive2DControl(LLMCorePromptBase):
    """对Yosuga Live2D控制场景"""
    def type(self) -> str:
        return "Yosuga Live2D控制信息"

    def describe_input(self) -> str:
        pass

    def describe_output(self) -> str:
        pass


if __name__ == "__main__":
    # 注册所有prompt处理器
    manager = LLMCorePromptManager()
    manager.register(YosugaAudioASRText())
    manager.register(YosugaUITARS())

    # 生成最终 system prompt
    system_prompt = YOSUGA_SYSTEM_PROMPT_SCH.format(
        InputInfo=manager.describe_input(),
        OutputInfo=manager.describe_output(),
        RoleSetting="...",
        Language="ja",
        Memory = "",
        SystemStateTable=""
    )
    print(system_prompt)