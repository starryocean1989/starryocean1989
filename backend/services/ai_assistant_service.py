# -*- coding: utf-8 -*-
"""
AI助手服务.

提供DeepSeek AI助手功能，包括：
- 策略代码生成和优化
- 策略逻辑解释和建议
- 错误诊断和修复建议
- 对话历史管理
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from backend.services.base_and_utils import BaseService
from backend.config import get_settings

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class AIAssistantService(BaseService):
    """AI助手服务.

    封装DeepSeek API调用，提供智能策略编写辅助功能。
    """

    def __init__(self):
        """初始化AI助手服务."""
        super().__init__()

        # AI配置
        self.settings = get_settings()
        self.ai_config = self.settings.ai

        # 对话历史
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history = self.ai_config.max_history

        # API配置
        self.api_url = self.ai_config.api_url
        self.api_key = self.ai_config.api_key
        self.model = self.ai_config.model
        self.max_tokens = self.ai_config.max_tokens
        self.temperature = self.ai_config.temperature
        self.timeout = self.ai_config.timeout

        self.logger.info("AI助手服务已创建")

    def _do_initialize(self) -> bool:
        """初始化AI助手服务."""
        try:
            self.logger.info("初始化AI助手服务...")

            # 检查requests库
            if not HAS_REQUESTS:
                self.logger.warning("requests库未安装，AI功能不可用")
                return False

            # 检查API密钥
            if not self.api_key:
                self.logger.warning("未配置DeepSeek API密钥，AI功能不可用")
                return False

            # 初始化系统提示词
            self._init_system_prompt()

            self.logger.info("✅ AI助手服务初始化成功")
            return True

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _do_shutdown(self) -> bool:
        """关闭AI助手服务."""
        try:
            # 清空对话历史
            self.conversation_history.clear()
            return True
        except Exception as e:
            self._log_error("关闭", e)
            return False

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "api_configured": bool(self.api_key),
            "has_requests": HAS_REQUESTS,
            "conversation_length": len(self.conversation_history),
        }

    def _init_system_prompt(self):
        """初始化系统提示词."""
        system_prompt = self.ai_config.system_prompt
        if not system_prompt:
            system_prompt = """你是一个专业的量化交易策略编写助手，精通Python和VnPy框架。
你的任务是帮助用户编写、优化和调试量化交易策略。

你应该：
1. 提供清晰、可执行的Python代码
2. 遵循VnPy框架的最佳实践
3. 考虑策略的风险管理和资金管理
4. 提供代码注释和解释
5. 指出潜在的问题和改进建议

当用户请求代码时，请使用```python代码块包裹代码。
当提供建议或解释时，使用自然语言描述。"""

        # 添加系统消息到历史
        self.conversation_history.append({"role": "system", "content": system_prompt})

    def chat(self, user_message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """与AI助手对话.

        Args:
            user_message: 用户消息
            context: 上下文信息（可选，如当前策略代码、错误信息等）

        Returns:
            Dict: 包含AI回复、消息类型等信息
        """
        try:
            if not HAS_REQUESTS:
                return {
                    "success": False,
                    "message": "requests库未安装",
                }

            if not self.api_key:
                return {
                    "success": False,
                    "message": "未配置DeepSeek API密钥",
                }

            # 构建完整的用户消息（包含上下文）
            full_message = user_message
            if context:
                context_str = self._format_context(context)
                full_message = f"{context_str}\n\n{user_message}"

            # 添加用户消息到历史
            self.conversation_history.append({"role": "user", "content": full_message})

            # 保持历史长度限制
            self._trim_history()

            # 调用DeepSeek API
            response = self._call_deepseek_api()

            if response["success"]:
                ai_message = response["content"]

                # 添加AI回复到历史
                self.conversation_history.append({"role": "assistant", "content": ai_message})

                # 分类回复内容（代码/文本）
                classified_response = self._classify_response(ai_message)

                return {
                    "success": True,
                    "message": ai_message,
                    "message_type": classified_response["type"],
                    "code": classified_response.get("code"),
                    "text": classified_response.get("text"),
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                return response

        except Exception as e:
            self._log_error("AI对话", e)
            return {
                "success": False,
                "message": f"对话失败: {str(e)}",
            }

    def _call_deepseek_api(self) -> Dict[str, Any]:
        """调用DeepSeek API.

        Returns:
            Dict: API响应结果
        """
        try:
            # 构建请求头
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            # 构建请求体
            payload = {
                "model": self.model,
                "messages": self.conversation_history,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
            }

            # 发送请求
            response = requests.post(
                self.api_url, headers=headers, json=payload, timeout=self.timeout
            )

            # 检查响应状态
            if response.status_code == 200:
                result = response.json()

                # 提取AI回复内容
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    return {
                        "success": True,
                        "content": content,
                    }
                else:
                    return {
                        "success": False,
                        "message": "API返回格式错误",
                    }
            else:
                error_msg = f"API调用失败: {response.status_code} - {response.text}"
                self.logger.error(error_msg)
                return {
                    "success": False,
                    "message": error_msg,
                }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "API请求超时",
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "message": f"网络请求失败: {str(e)}",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"API调用异常: {str(e)}",
            }

    def _format_context(self, context: Dict[str, Any]) -> str:
        """格式化上下文信息.

        Args:
            context: 上下文字典

        Returns:
            str: 格式化后的上下文字符串
        """
        context_parts = []

        if "strategy_code" in context:
            context_parts.append(f"当前策略代码:\n```python\n{context['strategy_code']}\n```")

        if "error_message" in context:
            context_parts.append(f"错误信息:\n{context['error_message']}")

        if "strategy_type" in context:
            context_parts.append(f"策略类型: {context['strategy_type']}")

        if "requirements" in context:
            context_parts.append(f"需求描述:\n{context['requirements']}")

        return "\n\n".join(context_parts)

    def _classify_response(self, ai_message: str) -> Dict[str, Any]:
        """分类AI回复内容.

        将回复分为代码和文本两部分。

        Args:
            ai_message: AI回复消息

        Returns:
            Dict: 包含type, code, text的字典
        """
        # 查找代码块
        code_blocks = []
        text_parts = []

        # 简单的代码块提取（```python...```）
        import re

        # 查找所有代码块
        pattern = r"```(?:python)?\n(.*?)```"
        matches = list(re.finditer(pattern, ai_message, re.DOTALL))

        if matches:
            # 有代码块
            last_end = 0
            for match in matches:
                # 提取代码块之前的文本
                if match.start() > last_end:
                    text = ai_message[last_end : match.start()].strip()
                    if text:
                        text_parts.append(text)

                # 提取代码
                code = match.group(1).strip()
                code_blocks.append(code)

                last_end = match.end()

            # 提取最后一个代码块之后的文本
            if last_end < len(ai_message):
                text = ai_message[last_end:].strip()
                if text:
                    text_parts.append(text)

            # 如果有代码，类型为mixed或code
            if code_blocks:
                return {
                    "type": "mixed" if text_parts else "code",
                    "code": "\n\n".join(code_blocks),
                    "text": "\n\n".join(text_parts) if text_parts else "",
                }

        # 没有代码块，纯文本
        return {
            "type": "text",
            "text": ai_message.strip(),
        }

    def _trim_history(self):
        """修剪对话历史，保持在最大长度限制内."""
        # 始终保留系统消息
        system_messages = [msg for msg in self.conversation_history if msg["role"] == "system"]
        user_assistant_messages = [
            msg for msg in self.conversation_history if msg["role"] != "system"
        ]

        # 如果超出限制，删除最旧的对话
        if len(user_assistant_messages) > self.max_history * 2:
            # 保留最近的max_history对对话
            user_assistant_messages = user_assistant_messages[-(self.max_history * 2) :]

        # 重建历史
        self.conversation_history = system_messages + user_assistant_messages

    def clear_history(self) -> Dict[str, Any]:
        """清空对话历史.

        Returns:
            Dict: 操作结果
        """
        try:
            # 保留系统消息
            system_messages = [msg for msg in self.conversation_history if msg["role"] == "system"]
            self.conversation_history = system_messages

            self.logger.info("对话历史已清空")

            return {
                "success": True,
                "message": "对话历史已清空",
            }

        except Exception as e:
            self._log_error("清空历史", e)
            return {
                "success": False,
                "message": f"清空失败: {str(e)}",
            }

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """获取对话历史.

        Returns:
            List: 对话历史列表
        """
        # 排除系统消息
        return [msg for msg in self.conversation_history if msg["role"] != "system"]

    def generate_strategy_code(
        self, strategy_description: str, strategy_type: str = "ctastrategy"
    ) -> Dict[str, Any]:
        """生成策略代码.

        Args:
            strategy_description: 策略描述
            strategy_type: 策略类型

        Returns:
            Dict: 包含生成的策略代码
        """
        try:
            # 构建提示词
            prompt = f"""请根据以下描述生成一个{strategy_type}类型的VnPy策略代码：

{strategy_description}

要求：
1. 代码结构完整，包含所有必要的方法
2. 包含详细的中文注释
3. 实现完整的策略逻辑
4. 包含适当的风险控制
5. 遵循VnPy框架的最佳实践

请直接输出可执行的Python代码。"""

            # 调用chat方法
            response = self.chat(prompt)

            if response["success"] and response["message_type"] in ["code", "mixed"]:
                return {
                    "success": True,
                    "code": response.get("code", ""),
                    "explanation": response.get("text", ""),
                }
            else:
                return response

        except Exception as e:
            self._log_error("生成策略代码", e)
            return {
                "success": False,
                "message": f"生成失败: {str(e)}",
            }

    def optimize_strategy_code(self, strategy_code: str) -> Dict[str, Any]:
        """优化策略代码.

        Args:
            strategy_code: 现有策略代码

        Returns:
            Dict: 包含优化建议和优化后的代码
        """
        try:
            prompt = """请分析以下策略代码，并提供优化建议和优化后的代码：

1. 性能优化
2. 逻辑改进
3. 风险控制加强
4. 代码规范性

请提供优化建议和完整的优化后代码。"""

            context = {"strategy_code": strategy_code}

            response = self.chat(prompt, context)

            return response

        except Exception as e:
            self._log_error("优化策略代码", e)
            return {
                "success": False,
                "message": f"优化失败: {str(e)}",
            }

    def explain_strategy_code(self, strategy_code: str) -> Dict[str, Any]:
        """解释策略代码.

        Args:
            strategy_code: 策略代码

        Returns:
            Dict: 包含策略解释
        """
        try:
            prompt = """请详细解释以下策略代码的逻辑：

1. 策略的核心思想
2. 入场和出场条件
3. 风险控制方法
4. 参数设置说明
5. 适用市场和注意事项"""

            context = {"strategy_code": strategy_code}

            response = self.chat(prompt, context)

            return response

        except Exception as e:
            self._log_error("解释策略代码", e)
            return {
                "success": False,
                "message": f"解释失败: {str(e)}",
            }

    def debug_strategy_error(self, strategy_code: str, error_message: str) -> Dict[str, Any]:
        """调试策略错误.

        Args:
            strategy_code: 策略代码
            error_message: 错误消息

        Returns:
            Dict: 包含错误分析和修复建议
        """
        try:
            prompt = """策略运行时出现了错误，请帮助分析错误原因并提供修复方案。

请提供：
1. 错误原因分析
2. 具体的修复步骤
3. 修复后的完整代码
4. 如何避免类似错误"""

            context = {
                "strategy_code": strategy_code,
                "error_message": error_message,
            }

            response = self.chat(prompt, context)

            return response

        except Exception as e:
            self._log_error("调试策略错误", e)
            return {
                "success": False,
                "message": f"调试失败: {str(e)}",
            }
