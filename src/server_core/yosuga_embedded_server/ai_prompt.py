"""
AI提示词构建器 - 构造用于AI函数调用的结构化提示词。

提示词引导AI输出有效的JSON-RPC调用，
服务端可将这些调用转发到相应的嵌入式设备。
"""

import json
from typing import Optional


# -- 约束AI输出的系统提示词模板 --
SYSTEM_PROMPT_TEMPLATE = """你是一个通过函数调用来控制嵌入式设备的AI助手。

你可以访问所有已连接设备上的以下函数：

{functions_table}

指令:
1. 你可以同时调用一个或多个函数。
2. 要调用函数，请以JSON数组格式返回RPC调用：
   {calls_syntax_example}
3. 始终为所有必填参数提供有效值。
4. 对于可选参数，仅在需要时包含它们。
5. 如果函数返回数据，结果将回传给你。

规则:
- 只能调用上面列出的函数。
- 不要虚构函数名或参数。
- 如果需要的功能没有对应的函数支持，请说明你需要的功能。
- 如果进行函数调用，只返回JSON数组（不要额外文字）。
- 如果需要提问或提供信息，添加"_explanation"字段。

函数调用的响应格式:
```json
[
  {{
    "jsonrpc": "2.0",
    "method": "function_name",
    "params": {{ "param1": value1, "param2": value2 }},
    "id": 1
  }}
]
```

设备路由: 每个函数属于特定设备（显示为@device_name）。
系统会自动将调用路由到正确的设备。
"""


FUNCTION_ENTRY_TEMPLATE = """### {name} (类型: {type}) @ {device_name}
描述: {description}
参数:
{params}
"""

PARAM_ENTRY_TEMPLATE = "  - {name} ({type}{optional}): {description}"


CALLS_SYNTAX_EXAMPLE = """[
  {
    "jsonrpc": "2.0",
    "method": "function_name",
    "params": {
      "param1": "value1",
      "param2": 42
    },
    "id": 1
  }
]"""


class AIPromptBuilder:
    """从函数注册表内容构建AI提示词。

    提示词设计目标:
    - 清晰列出所有可用函数及其描述
    - 显示每个函数由哪个设备提供
    - 约束AI输出有效的JSON-RPC
    - 支持多调用响应
    """

    def __init__(self):
        self._system_prompt = SYSTEM_PROMPT_TEMPLATE

    def set_system_prompt(self, prompt: str):
        self._system_prompt = prompt

    def build_system_prompt(self, functions: list[dict]) -> str:
        """用当前函数表构建完整的系统提示词。

        Args:
            functions: 来自FunctionRegistry的函数信息字典列表

        Returns:
            准备发送给AI的完整系统提示词字符串。
        """
        if not functions:
            return "当前没有已连接的嵌入式设备，无可用函数。"

        table = self._format_functions_table(functions)
        return self._system_prompt.format(
            functions_table=table,
            calls_syntax_example=CALLS_SYNTAX_EXAMPLE,
        )

    def _format_functions_table(self, functions: list[dict]) -> str:
        """将函数列表格式化为可读的函数表。"""
        entries = []
        for func in functions:
            params_str = self._format_params(func.get("params", []))
            entry = FUNCTION_ENTRY_TEMPLATE.format(
                name=func["name"],
                type=func.get("type", "ctrl_noret"),
                device_name=func.get("device_name", "unknown"),
                description=func.get("description", "No description"),
                params=params_str if params_str else "  (none)",
            )
            entries.append(entry)
        return "\n".join(entries)

    def _format_params(self, params: list[dict]) -> str:
        lines = []
        for p in params:
            optional_str = ", optional" if p.get("optional") else ""
            lines.append(PARAM_ENTRY_TEMPLATE.format(
                name=p.get("name", "?"),
                type=p.get("type", "unknown"),
                optional=optional_str,
                description=p.get("description", ""),
            ))
        return "\n".join(lines)

    def parse_ai_response(self, response_text: str) -> Optional[list[dict]]:
        """从AI响应文本中提取JSON-RPC调用数组。

        AI可能将JSON包裹在markdown代码块中，或直接输出原始JSON。
        此方法处理两种情况。

        Args:
            response_text: AI返回的原始文本

        Returns:
            RPC请求字典列表，解析失败时返回None
        """
        text = response_text.strip()

        # 尝试从markdown代码块中提取
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return data
        return None
