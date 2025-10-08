# -*- coding: utf-8 -*-
"""
AI助手服务

集成DeepSeek AI，提供代码分析、代码生成、策略优化等功能。
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class AIService:
    """AI助手服务"""

    def __init__(self):
        """初始化AI服务"""
        from backend.config import get_settings

        self.settings = get_settings()
        self.ai_config = self.settings.ai
        self.conversation_history: Dict[str, List[Dict]] = {}

        # 检查API配置
        if self.ai_config.api_key:
            logger.info("AI助手服务初始化完成（DeepSeek API已配置）")
            self.enabled = True
        else:
            logger.warning("AI助手服务初始化完成（API Key未配置，AI功能将不可用）")
            self.enabled = False

    async def chat(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        AI对话

        Args:
            message: 用户消息
            context: 上下文信息（代码、策略信息等）
            session_id: 会话ID（用于保持对话历史）

        Returns:
            AI响应
        """
        try:
            # 如果未启用，直接报错
            if not self.enabled:
                raise RuntimeError(
                    "AI助手未启用。请配置DeepSeek API Key：\n"
                    "1. 访问 https://platform.deepseek.com/ 注册账号\n"
                    "2. 获取API Key\n"
                    "3. 设置环境变量：AI_API_KEY=your_api_key\n"
                    "4. 重启应用"
                )

            # 获取或创建会话历史
            session_id = session_id or "default"
            if session_id not in self.conversation_history:
                self.conversation_history[session_id] = []

            history = self.conversation_history[session_id]

            # 构建消息列表
            messages = self._build_messages(message, context, history)

            # 调用DeepSeek API
            response = await self._call_deepseek_api(messages)

            # 保存历史
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": response["content"]})

            # 限制历史长度
            max_history = self.ai_config.max_history or 10
            if len(history) > max_history * 2:
                history = history[-(max_history * 2) :]
                self.conversation_history[session_id] = history

            # 分析响应内容，分离代码和文本
            parsed_response = self._parse_response(response["content"])

            logger.info("AI助手响应成功，会话ID: %s", session_id)
            return {
                "success": True,
                "message": parsed_response["text"],
                "code": parsed_response["code"],
                "type": "ai_response",
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
            }

        except Exception as e:
            logger.error("AI助手处理失败: %s", e)
            return {
                "success": False,
                "error": str(e),
                "message": f"AI助手处理失败: {e}",
                "timestamp": datetime.now().isoformat(),
            }

    def _build_messages(
        self, message: str, context: Optional[Dict[str, Any]], history: List[Dict]
    ) -> List[Dict]:
        """构建发送给AI的消息列表"""
        messages = [{"role": "system", "content": self.ai_config.system_prompt}]

        # 添加历史对话
        max_history = self.ai_config.max_history or 10
        messages.extend(history[-(max_history * 2) :])

        # 构建当前消息
        current_message = message
        if context:
            if "code" in context:
                code_text = context["code"]
                current_message = f"当前代码：\n```python\n{code_text}\n```\n\n{message}"
            if "strategy_info" in context:
                strategy_json = json.dumps(context["strategy_info"], ensure_ascii=False)
                current_message += f"\n\n策略信息：{strategy_json}"

        messages.append({"role": "user", "content": current_message})
        return messages

    async def _call_deepseek_api(self, messages: List[Dict]) -> Dict[str, Any]:
        """调用DeepSeek API"""
        headers = {
            "Authorization": f"Bearer {self.ai_config.api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": self.ai_config.model,
            "messages": messages,
            "max_tokens": self.ai_config.max_tokens,
            "temperature": self.ai_config.temperature,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.ai_config.api_url,
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=self.ai_config.timeout),
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return {
                        "content": result["choices"][0]["message"]["content"],
                        "usage": result.get("usage", {}),
                    }
                else:
                    error_text = await resp.text()
                    error_msg = f"DeepSeek API错误 ({resp.status}): {error_text}"
                    raise RuntimeError(error_msg)

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """解析AI响应，分离代码和文本"""
        # 提取代码块
        code_blocks = re.findall(r"```(?:python)?\n(.*?)```", content, re.DOTALL)

        # 移除代码块，保留文本
        text = re.sub(r"```(?:python)?\n.*?```", "", content, flags=re.DOTALL).strip()

        return {"text": text, "code": "\n\n".join(code_blocks) if code_blocks else None}

    async def analyze_code(self, code: str, analysis_type: str = "review") -> Dict[str, Any]:
        """
        代码分析

        Args:
            code: 要分析的代码
            analysis_type: 分析类型（review/optimize/debug）

        Returns:
            分析结果
        """
        prompts = {
            "review": "请审查这段Python策略代码，指出潜在的问题和改进建议。",
            "optimize": "请分析这段策略代码的性能，提供优化建议。",
            "debug": "请帮我找出这段代码中的Bug和逻辑错误。",
        }

        prompt = prompts.get(analysis_type, prompts["review"])
        context = {"code": code}

        return await self.chat(prompt, context)

    async def generate_code(
        self, requirement: str, strategy_type: str = "ctastrategy"
    ) -> Dict[str, Any]:
        """
        代码生成

        Args:
            requirement: 需求描述
            strategy_type: 策略类型

        Returns:
            生成的代码
        """
        prompt = f"""
请根据以下需求生成一个{strategy_type}类型的VnPy策略代码：

需求：{requirement}

要求：
1. 使用VnPy框架的标准模板
2. 包含完整的参数定义
3. 实现on_bar/on_tick等核心方法
4. 添加必要的注释
5. 遵循PEP8代码规范
"""

        return await self.chat(prompt)

    def clear_history(self, session_id: Optional[str] = None) -> bool:
        """清除对话历史"""
        if session_id:
            if session_id in self.conversation_history:
                del self.conversation_history[session_id]
                logger.info("清除会话历史: %s", session_id)
                return True
            return False
        else:
            self.conversation_history.clear()
            logger.info("清除所有会话历史")
            return True


__all__ = ["AIService"]
