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

from backend.core.service_base import BaseService
from backend.core.config import get_settings

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

        # 🔧 MCP 功能：定义文件操作工具
        self.tools = self._define_tools()

        # 策略文件目录（用于安全检查）
        from pathlib import Path

        self.strategy_dir = Path("strategies/user_strategies").resolve()

        self.logger.info("AI助手服务已创建（支持文件操作工具）")

    def _do_initialize(self) -> bool:
        """初始化AI助手服务."""
        try:
            self.logger.info("初始化AI助手服务...")

            # 检查requests库
            if not HAS_REQUESTS:
                # AI是可选功能，降低日志级别
                self.logger.debug("requests库未安装，AI功能不可用")
                return False

            # 检查API密钥（使用最新配置）
            from backend.core.config import get_settings

            current_settings = get_settings()
            current_api_key = current_settings.ai.api_key

            if not current_api_key:
                # AI是可选功能，降低日志级别
                self.logger.debug("未配置DeepSeek API密钥，AI功能不可用")
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

文件操作指南：
- 当用户说"新建xxx文件"、"创建xxx策略"时，使用write_file工具将代码保存到新文件
- 当用户说"修改xxx文件"、"更新xxx文件"或提到具体文件名时，先用read_file读取该文件，然后用write_file保存修改
- 当用户说"查看xxx文件"、"读取xxx文件"时，使用read_file工具读取文件内容
- 文件路径格式：strategies/user_strategies/文件名.py
- 总是使用完整的文件路径，不要省略目录

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

            # 检查API密钥（使用最新配置）
            from backend.core.config import get_settings

            current_settings = get_settings()
            current_api_key = current_settings.ai.api_key

            if not current_api_key:
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

                # 检查是否有文件操作（从最近的对话历史中查找）
                files_modified = self._extract_modified_files()

                return {
                    "success": True,
                    "message": ai_message,
                    "message_type": classified_response["type"],
                    "code": classified_response.get("code"),
                    "text": classified_response.get("text"),
                    "files_modified": files_modified,  # 新增：修改的文件列表
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
            # 每次调用时重新获取最新配置（支持热更新）
            from backend.core.config import get_settings

            current_settings = get_settings()
            current_api_key = current_settings.ai.api_key
            current_api_url = current_settings.ai.api_url
            current_model = current_settings.ai.model
            current_max_tokens = current_settings.ai.max_tokens
            current_temperature = current_settings.ai.temperature
            current_timeout = current_settings.ai.timeout

            # 记录使用的API Key（用于调试）
            if current_api_key:
                masked_key = (
                    f"{current_api_key[:4]}...{current_api_key[-4:]}"
                    if len(current_api_key) > 8
                    else "***"
                )
                # 改为 info 级别，确保能看到
                self.logger.info("🔑 正在使用API Key: %s", masked_key)

            # 构建请求头（使用最新的API Key）
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {current_api_key}",
            }

            # 构建请求体（使用最新的配置）
            payload = {
                "model": current_model,
                "messages": self.conversation_history,
                "max_tokens": current_max_tokens,
                "temperature": current_temperature,
            }

            # 🔧 仅在启用工具调用时添加 tools 参数
            enable_tools = (
                current_settings.ai.enable_tools
                if hasattr(current_settings.ai, "enable_tools")
                else False
            )
            if enable_tools:
                payload["tools"] = self.tools
                self.logger.info("工具调用已启用，包含 %d 个工具", len(self.tools))
            else:
                self.logger.debug("工具调用未启用")

            # 工具调用循环（最多10轮，避免无限循环）
            max_tool_rounds = 10
            for _round_num in range(max_tool_rounds):
                # 发送请求（使用最新的URL和超时配置）
                response = requests.post(
                    current_api_url, headers=headers, json=payload, timeout=current_timeout
                )

                # 检查响应状态
                if response.status_code != 200:
                    error_msg = f"API调用失败: {response.status_code} - {response.text}"
                    self.logger.error(error_msg)
                    return {
                        "success": False,
                        "message": error_msg,
                    }

                result = response.json()

                # 提取AI回复
                if "choices" not in result or len(result["choices"]) == 0:
                    return {
                        "success": False,
                        "message": "API返回格式错误",
                    }

                choice = result["choices"][0]
                finish_reason = choice.get("finish_reason")
                message = choice.get("message", {})

                # 检查是否需要调用工具
                if finish_reason == "tool_calls" and "tool_calls" in message:
                    # AI 请求调用工具
                    tool_calls = message["tool_calls"]
                    self.logger.info("AI 请求调用 %d 个工具", len(tool_calls))

                    # 将 AI 的消息添加到历史
                    self.conversation_history.append(message)

                    # 执行所有工具调用
                    for tool_call in tool_calls:
                        tool_id = tool_call.get("id")
                        function = tool_call.get("function", {})
                        function_name = function.get("name")

                        # 解析参数
                        import json

                        try:
                            arguments = json.loads(function.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            arguments = {}

                        # 执行工具
                        tool_result = self._execute_tool(function_name, arguments)

                        # 将工具结果添加到历史
                        self.conversation_history.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_id,
                                "content": tool_result,
                            }
                        )

                    # 更新 payload 继续对话
                    payload["messages"] = self.conversation_history

                    # 继续下一轮（让 AI 处理工具结果）
                    continue

                elif finish_reason == "stop":
                    # AI 完成回复，返回内容
                    content = message.get("content", "")
                    if content:
                        return {
                            "success": True,
                            "content": content,
                        }
                    else:
                        return {
                            "success": False,
                            "message": "AI回复为空",
                        }

                else:
                    # 其他情况（如达到token限制）
                    content = message.get("content", "")
                    if content:
                        return {
                            "success": True,
                            "content": content,
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"未知的完成原因: {finish_reason}",
                        }

            # 达到最大轮数限制
            return {
                "success": False,
                "message": f"工具调用超过最大轮数限制（{max_tool_rounds}轮）",
            }

        except requests.exceptions.Timeout:
            self.logger.warning("API请求超时，可能是因为工具调用处理时间较长")
            return {
                "success": False,
                "message": "API请求超时。如果AI正在调用文件操作工具，请增加超时时间（在系统管理→系统配置中设置）。建议超时时间：60-90秒。",
            }
        except requests.exceptions.ConnectionError as e:
            self.logger.error("连接错误: %s", e, exc_info=True)
            return {
                "success": False,
                "message": "连接错误: 服务器关闭了连接。可能原因：1) 请求过大 2) 服务器繁忙 3) 网络不稳定。建议：分步骤操作，避免一次性复杂请求。",
            }
        except requests.exceptions.RequestException as e:
            self.logger.error("网络请求失败: %s", e, exc_info=True)
            return {
                "success": False,
                "message": f"网络请求失败: {str(e)}",
            }
        except Exception as e:
            self.logger.error("API调用异常: %s", e, exc_info=True)
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

    def _extract_modified_files(self) -> list:
        """从对话历史中提取最近修改的文件列表.

        Returns:
            list: 修改的文件路径列表
        """
        modified_files = []

        # 从后往前查找最近的tool消息（限制在最近20条消息内）
        recent_messages = self.conversation_history[-20:]

        for msg in reversed(recent_messages):
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                # 检查是否是成功写入文件的消息
                if "✅ 成功写入文件" in content:
                    # 提取文件路径（格式：✅ 成功写入文件：路径 (字节数)）
                    import re

                    match = re.search(r"✅ 成功写入文件：(.+?)\s+\(", content)
                    if match:
                        file_path = match.group(1).strip()
                        if file_path not in modified_files:
                            modified_files.append(file_path)

        return modified_files

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

    # ==================== MCP 功能：文件操作工具 ====================

    def _define_tools(self) -> List[Dict[str, Any]]:
        """定义AI可以使用的文件操作工具（符合DeepSeek API格式）.

        参考：https://api-docs.deepseek.com/zh-cn/guides/function_calling

        Returns:
            List: 工具定义列表
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "读取文件内容。可以读取任何文本文件，包括策略文件、配置文件、日志文件等。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "文件路径，可以是相对路径（相对于项目根目录）或绝对路径。例如：strategies/user_strategies/my_strategy.py",
                            }
                        },
                        "required": ["file_path"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "写入或创建策略文件。仅限于 strategies/user_strategies 目录内。如果文件已存在会覆盖。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "文件路径，必须在 strategies/user_strategies 目录内。例如：strategies/user_strategies/new_strategy.py",
                            },
                            "content": {
                                "type": "string",
                                "description": "文件内容（完整的代码或文本）",
                            },
                        },
                        "required": ["file_path", "content"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_file",
                    "description": "删除策略文件。仅限于 strategies/user_strategies 目录内。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "要删除的文件路径，必须在 strategies/user_strategies 目录内。",
                            }
                        },
                        "required": ["file_path"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_strategy_files",
                    "description": "列出所有用户策略文件。",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def _is_safe_strategy_path(self, file_path: str) -> bool:
        """检查路径是否在策略目录内（安全检查）.

        Args:
            file_path: 文件路径

        Returns:
            bool: 是否安全
        """
        try:
            from pathlib import Path

            # 解析目标路径
            if Path(file_path).is_absolute():
                target = Path(file_path).resolve()
            else:
                # 相对路径，相对于项目根目录
                project_root = Path(__file__).parent.parent.parent
                target = (project_root / file_path).resolve()

            # 检查是否在策略目录内
            is_safe = target.is_relative_to(self.strategy_dir)

            if not is_safe:
                self.logger.warning("路径安全检查失败: %s 不在策略目录内", file_path)

            return is_safe

        except Exception as e:
            self.logger.error("路径安全检查异常: %s", e)
            return False

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """执行工具调用.

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            str: 工具执行结果
        """
        try:
            self.logger.info("执行工具: %s, 参数: %s", tool_name, arguments)

            if tool_name == "read_file":
                return self._tool_read_file(arguments.get("file_path", ""))
            elif tool_name == "write_file":
                return self._tool_write_file(
                    arguments.get("file_path", ""), arguments.get("content", "")
                )
            elif tool_name == "delete_file":
                return self._tool_delete_file(arguments.get("file_path", ""))
            elif tool_name == "list_strategy_files":
                return self._tool_list_strategy_files()
            else:
                return f"错误：未知工具 '{tool_name}'"

        except Exception as e:
            self.logger.error("工具执行失败: %s", e, exc_info=True)
            return f"错误：工具执行失败 - {str(e)}"

    def _tool_read_file(self, file_path: str) -> str:
        """工具：读取文件内容.

        Args:
            file_path: 文件路径

        Returns:
            str: 文件内容或错误消息
        """
        try:
            from pathlib import Path

            if not file_path:
                return "错误：未提供文件路径"

            # 解析路径
            if Path(file_path).is_absolute():
                target = Path(file_path)
            else:
                # 相对路径，相对于项目根目录
                project_root = Path(__file__).parent.parent.parent
                target = project_root / file_path

            # 检查文件是否存在
            if not target.exists():
                return f"错误：文件不存在 - {file_path}"

            if not target.is_file():
                return f"错误：路径不是文件 - {file_path}"

            # 检查文件大小（限制 1MB）
            file_size = target.stat().st_size
            if file_size > 1024 * 1024:
                return f"错误：文件过大（{file_size / 1024:.1f}KB），最大支持 1MB"

            # 读取文件
            with open(target, "r", encoding="utf-8") as f:
                content = f.read()

            self.logger.info("成功读取文件: %s (%d 字节)", file_path, len(content))
            return f"文件内容（{file_path}）：\n\n{content}"

        except UnicodeDecodeError:
            return f"错误：文件编码错误，无法读取（可能是二进制文件） - {file_path}"
        except PermissionError:
            return f"错误：没有读取权限 - {file_path}"
        except Exception as e:
            self.logger.error("读取文件失败: %s", e, exc_info=True)
            return f"错误：读取文件失败 - {str(e)}"

    def _tool_write_file(self, file_path: str, content: str) -> str:
        """工具：写入文件内容（仅限策略目录）.

        Args:
            file_path: 文件路径
            content: 文件内容

        Returns:
            str: 操作结果消息
        """
        try:
            from pathlib import Path

            if not file_path:
                return "错误：未提供文件路径"

            if not content:
                return "错误：未提供文件内容"

            # 安全检查：仅允许写入策略目录
            if not self._is_safe_strategy_path(file_path):
                return f"错误：安全限制 - 只能写入 strategies/user_strategies 目录内的文件。尝试写入的路径：{file_path}"

            # 解析路径
            if Path(file_path).is_absolute():
                target = Path(file_path)
            else:
                project_root = Path(__file__).parent.parent.parent
                target = project_root / file_path

            # 确保是 .py 文件
            if target.suffix != ".py":
                return f"错误：只允许写入 .py 文件。当前文件：{target.suffix}"

            # 创建目录（如果不存在）
            target.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)

            self.logger.info("成功写入文件: %s (%d 字节)", file_path, len(content))
            return f"✅ 成功写入文件：{file_path} ({len(content)} 字节)"

        except PermissionError:
            return f"错误：没有写入权限 - {file_path}"
        except Exception as e:
            self.logger.error("写入文件失败: %s", e, exc_info=True)
            return f"错误：写入文件失败 - {str(e)}"

    def _tool_delete_file(self, file_path: str) -> str:
        """工具：删除文件（仅限策略目录）.

        Args:
            file_path: 文件路径

        Returns:
            str: 操作结果消息
        """
        try:
            from pathlib import Path

            if not file_path:
                return "错误：未提供文件路径"

            # 安全检查：仅允许删除策略目录内的文件
            if not self._is_safe_strategy_path(file_path):
                return f"错误：安全限制 - 只能删除 strategies/user_strategies 目录内的文件。尝试删除的路径：{file_path}"

            # 解析路径
            if Path(file_path).is_absolute():
                target = Path(file_path)
            else:
                project_root = Path(__file__).parent.parent.parent
                target = project_root / file_path

            # 检查文件是否存在
            if not target.exists():
                return f"错误：文件不存在 - {file_path}"

            if not target.is_file():
                return f"错误：路径不是文件 - {file_path}"

            # 删除文件
            target.unlink()

            self.logger.info("成功删除文件: %s", file_path)
            return f"✅ 成功删除文件：{file_path}"

        except PermissionError:
            return f"错误：没有删除权限 - {file_path}"
        except Exception as e:
            self.logger.error("删除文件失败: %s", e, exc_info=True)
            return f"错误：删除文件失败 - {str(e)}"

    def _tool_list_strategy_files(self) -> str:
        """工具：列出所有策略文件.

        Returns:
            str: 策略文件列表
        """
        try:
            if not self.strategy_dir.exists():
                return "策略目录不存在"

            # 列出所有 .py 文件
            strategy_files = list(self.strategy_dir.glob("*.py"))

            if not strategy_files:
                return "策略目录为空，没有找到任何 .py 文件"

            # 构建文件列表
            file_list = []
            for file in sorted(strategy_files):
                file_size = file.stat().st_size
                file_list.append(f"- {file.name} ({file_size} 字节)")

            result = f"找到 {len(strategy_files)} 个策略文件：\n\n" + "\n".join(file_list)

            self.logger.info("列出策略文件: %d 个", len(strategy_files))
            return result

        except Exception as e:
            self.logger.error("列出策略文件失败: %s", e, exc_info=True)
            return f"错误：列出文件失败 - {str(e)}"
