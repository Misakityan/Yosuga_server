# llm_core/llm_core_dispatcher.py

"""
动作分发器模块
负责将解析后的LLM输出对象路由到对应的业务处理器
支持同步/异步处理，提供回退机制与执行结果追踪
"""

import asyncio
from typing import Any, Callable, ClassVar, Dict, List, Optional, Union
from functools import wraps
from loguru import logger

from src.server_core.llm_core.llm_core_analysis import LLMCoreAnalysisBase

# 处理器类型定义
# 同步处理器：接收解析对象，返回执行结果
SyncActionHandler = Callable[[LLMCoreAnalysisBase], Any]
# 异步处理器：接收解析对象，返回协程
AsyncActionHandler = Callable[[LLMCoreAnalysisBase], Any]


def handler_error_wrapper(func: Callable) -> Callable:
    """
    处理器错误包装装饰器
    统一捕获异常并记录日志，避免单个处理失败导致整体崩溃
    """

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"处理器 {func.__name__} 执行失败: {e}")
            raise

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"异步处理器 {func.__name__} 执行失败: {e}")
            raise

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


class LLMCoreActionDispatcher:
    """
    LLM动作分发中心

    职责：
    1. 管理类型到处理器的映射关系
    2. 支持同步与异步处理器注册
    3. 执行分发并收集处理结果
    4. 提供未注册类型的回退机制
    5. 支持批量处理与结果聚合

    使用示例：
        # 注册同步处理器
        def handle_audio(data: YosugaAudioResponseData) -> dict:
            return {"status": "spoken", "text": data.response_text}

        LLMCoreActionDispatcher.register("audio_text", handle_audio)

        # 注册异步处理器
        async def handle_ui(data: YosugaUITARSResponseData):
            await perform_click(data.x1, data.y1)
            return {"status": "clicked"}

        LLMCoreActionDispatcher.register_async("auto_agent", handle_ui)

        # 执行分发
        results = LLMCoreActionDispatcher.execute(parsed_objects)
    """

    # 类变量存储所有注册的处理器
    _sync_handlers: ClassVar[Dict[str, SyncActionHandler]] = {}
    _async_handlers: ClassVar[Dict[str, AsyncActionHandler]] = {}
    _fallback_handler: ClassVar[Optional[Union[SyncActionHandler, AsyncActionHandler]]] = None

    @classmethod
    def register(cls, type_id: str, handler: SyncActionHandler) -> None:
        """
        注册同步处理器

        Args:
            type_id: 与 LLMCoreAnalysisBase.type_() 返回值匹配的标识符
            handler: 同步函数，接收解析对象并返回执行结果

        Raises:
            ValueError: 处理器不是可调用的函数
        """
        if not callable(handler):
            raise ValueError(f"处理器必须是可调用函数，收到: {type(handler)}")

        # 检查是否已注册，防止覆盖
        if type_id in cls._sync_handlers or type_id in cls._async_handlers:
            logger.warning(f"类型 '{type_id}' 已被注册，将被覆盖")

        cls._sync_handlers[type_id] = handler_error_wrapper(handler)
        logger.success(f"注册同步处理器: {type_id} → {handler.__name__}")

    @classmethod
    def register_async(cls, type_id: str, handler: AsyncActionHandler) -> None:
        """
        注册异步处理器

        Args:
            type_id: 类型标识符
            handler: 异步函数，接收解析对象并返回协程

        Raises:
            ValueError: 处理器不是有效的异步函数
        """
        if not asyncio.iscoroutinefunction(handler):
            raise ValueError(f"异步处理器必须是协程函数，收到: {type(handler)}")

        if type_id in cls._sync_handlers or type_id in cls._async_handlers:
            logger.warning(f"类型 '{type_id}' 已被注册，将被覆盖")

        cls._async_handlers[type_id] = handler_error_wrapper(handler)
        logger.success(f"注册异步处理器: {type_id} → {handler.__name__}")

    @classmethod
    def set_fallback(cls, handler: Union[SyncActionHandler, AsyncActionHandler]) -> None:
        """
        设置回退处理器（未注册类型的默认处理）

        Args:
            handler: 同步或异步函数，处理所有未匹配的类型
        """
        wrapped = handler_error_wrapper(handler)
        cls._fallback_handler = wrapped
        handler_type = "异步" if asyncio.iscoroutinefunction(handler) else "同步"
        logger.info(f"设置{handler_type}回退处理器: {handler.__name__}")

    @classmethod
    def get_handler(cls, type_id: str) -> Optional[Union[SyncActionHandler, AsyncActionHandler]]:
        """获取指定类型的处理器"""
        # 优先返回同步处理器
        if type_id in cls._sync_handlers:
            return cls._sync_handlers[type_id]
        # 其次返回异步处理器
        if type_id in cls._async_handlers:
            return cls._async_handlers[type_id]
        # 返回回退处理器
        return cls._fallback_handler

    @classmethod
    def execute(
            cls,
            analysis_results: List[LLMCoreAnalysisBase],
            run_async: bool = False
    ) -> Dict[str, List[Any]]:
        """
        执行分发处理

        Args:
            analysis_results: 解析器返回的对象列表
            run_async: 是否启用异步执行模式（需要业务代码支持asyncio）

        Returns:
            执行结果字典:
            {
                "success": [处理成功的结果列表],
                "failed": [{"type": "...", "error": "..."}],
                "skipped": [跳过的类型列表]
            }
        """
        if not analysis_results:
            logger.warning("无对象需要分发")
            return {"success": [], "failed": [], "skipped": []}

        if run_async and (cls._async_handlers or asyncio.iscoroutinefunction(cls._fallback_handler)):
            # 异步执行模式（需要事件循环）
            return asyncio.run(cls._execute_async(analysis_results))

        # 默认同步执行
        return cls._execute_sync(analysis_results)

    @classmethod
    def _execute_sync(cls, results: List[LLMCoreAnalysisBase]) -> Dict[str, List[Any]]:
        """同步批量执行"""
        outputs = {"success": [], "failed": [], "skipped": []}

        for idx, result in enumerate(results):
            type_id = result.type
            logger.debug(f"[{idx}] 分发类型: {type_id}")

            handler = cls.get_handler(type_id)
            if not handler:
                outputs["skipped"].append(type_id)
                logger.warning(f"无处理器，跳过: {type_id}")
                continue

            # 执行同步处理器
            if asyncio.iscoroutinefunction(handler):
                logger.error(f"异步处理器 '{type_id}' 不能在同步模式下执行")
                outputs["failed"].append({"type": type_id, "error": "异步处理器需要run_async=True"})
                continue

            try:
                output = handler(result)
                outputs["success"].append({
                    "type": type_id,
                    "output": output,
                    "index": idx
                })
                logger.success(f"[{idx}] 处理成功: {type_id}")
            except Exception as e:
                outputs["failed"].append({
                    "type": type_id,
                    "error": str(e),
                    "index": idx
                })
                logger.error(f"[{idx}] 处理失败 {type_id}: {e}")

        cls._log_summary(outputs, len(results))
        return outputs

    @classmethod
    async def _execute_async(cls, results: List[LLMCoreAnalysisBase]) -> Dict[str, List[Any]]:
        """异步批量执行"""
        outputs = {"success": [], "failed": [], "skipped": []}
        tasks = []

        for idx, result in enumerate(results):
            type_id = result.type
            logger.debug(f"[{idx}] 异步分发类型: {type_id}")

            handler = cls.get_handler(type_id)
            if not handler:
                outputs["skipped"].append(type_id)
                logger.warning(f"无处理器，跳过: {type_id}")
                continue

            # 创建协程任务
            if asyncio.iscoroutinefunction(handler):
                task = cls._run_async_handler(handler, result, idx, outputs)
            else:
                # 同步处理器在异步线程池中执行
                task = cls._run_sync_in_executor(handler, result, idx, outputs)

            tasks.append(task)

        # 并发执行所有任务
        await asyncio.gather(*tasks, return_exceptions=True)

        cls._log_summary(outputs, len(results))
        return outputs

    @classmethod
    async def _run_async_handler(cls, handler, result, idx, outputs):
        """运行异步处理器"""
        try:
            output = await handler(result)
            outputs["success"].append({
                "type": result.type,
                "output": output,
                "index": idx
            })
            logger.success(f"[{idx}] 异步处理成功: {result.type}")
        except Exception as e:
            outputs["failed"].append({
                "type": result.type,
                "error": str(e),
                "index": idx
            })
            logger.error(f"[{idx}] 异步处理失败 {result.type}: {e}")

    @classmethod
    async def _run_sync_in_executor(cls, handler, result, idx, outputs):
        """在线程池中运行同步处理器"""
        loop = asyncio.get_event_loop()
        try:
            output = await loop.run_in_executor(None, handler, result)
            outputs["success"].append({
                "type": result.type,
                "output": output,
                "index": idx
            })
            logger.success(f"[{idx}] 同步处理器(线程池)成功: {result.type}")
        except Exception as e:
            outputs["failed"].append({
                "type": result.type,
                "error": str(e),
                "index": idx
            })
            logger.error(f"[{idx}] 同步处理器(线程池)失败 {result.type}: {e}")

    @classmethod
    def _log_summary(cls, outputs: Dict, total: int):
        """输出处理摘要"""
        success_count = len(outputs["success"])
        failed_count = len(outputs["failed"])
        skipped_count = len(outputs["skipped"])

        logger.info(
            f"分发完成 | 总计: {total} | 成功: {success_count} "
            f"失败: {failed_count} 跳过: {skipped_count}"
        )

    @classmethod
    def clear(cls) -> None:
        """清空所有处理器（测试/热重载用）"""
        cls._sync_handlers.clear()
        cls._async_handlers.clear()
        cls._fallback_handler = None
        logger.info("已清空所有动作处理器")

    @classmethod
    def list_handlers(cls) -> Dict[str, str]:
        """列出当前注册的所有处理器"""
        handlers = {}
        for type_id, handler in cls._sync_handlers.items():
            handlers[type_id] = f"同步: {handler.__name__}"
        for type_id, handler in cls._async_handlers.items():
            handlers[type_id] = f"异步: {handler.__name__}"
        return handlers