# -*- coding: utf-8 -*-
"""
两阶段重试连接池

提供带智能重试机制的连接池包装器，支持：
- 阶段1：IPv4+IPv6混合池，最多10次尝试
- 阶段2：IPv4最快30%服务器，最多5次尝试
- 自动排除已尝试的服务器
- 详细日志记录

作者：[项目名称]
版本：1.0
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from .async_hq import AsyncTdxHq_API
from .logger import logger


class RetryConnectionPool:
    """
    带两阶段重试的连接池包装器
    
    阶段1: IPv4+IPv6混合池，最多10次尝试
    阶段2: IPv4最快30%服务器，最多5次尝试
    """
    
    def __init__(
        self,
        server_pool_manager,
        phase1_max_attempts: int = 10,
        phase2_max_attempts: int = 5,
        connection_timeout: float = 5.0,
    ):
        """
        初始化重试连接池
        
        Args:
            server_pool_manager: ServerPoolManager 实例
            phase1_max_attempts: 阶段1最大尝试次数
            phase2_max_attempts: 阶段2最大尝试次数
            connection_timeout: 连接超时时间（秒）
        """
        self.server_pool_manager = server_pool_manager
        self.phase1_max_attempts = phase1_max_attempts
        self.phase2_max_attempts = phase2_max_attempts
        self.connection_timeout = connection_timeout
        
    async def execute_with_retry(
        self,
        task_func: Callable[[AsyncTdxHq_API], Any],
        attempted_servers: List[str],
        scenario: str = "download",
    ) -> Tuple[Optional[Any], bool]:
        """
        执行带重试的任务
        
        Args:
            task_func: 任务函数，接受 AsyncTdxHq_API 作为参数，返回结果
            attempted_servers: 已尝试服务器列表（格式：["ip:port", ...]），会被更新
            scenario: 场景标识（用于日志）
        
        Returns:
            (result, success): 结果和是否成功
        """
        # 阶段1: 混合池重试
        logger.debug(
            f"[RETRY-POOL] 开始阶段1重试（混合池）: 已尝试={len(attempted_servers)}个服务器",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )
        
        result = await self._phase1_retry(task_func, attempted_servers, scenario)
        if result is not None:
            logger.info(
                f"[RETRY-POOL] ✅ 阶段1成功: 已尝试={len(attempted_servers)}个服务器",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return result, True
            
        # 阶段2: 最快30%服务器重试
        logger.info(
            f"[RETRY-POOL] ⚠️ 阶段1失败，进入阶段2（最快30%池）: 已尝试={len(attempted_servers)}个服务器",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )
        
        result = await self._phase2_retry(task_func, attempted_servers, scenario)
        if result is not None:
            logger.info(
                f"[RETRY-POOL] ✅ 阶段2成功: 已尝试={len(attempted_servers)}个服务器",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return result, True
        
        # 两个阶段都失败
        logger.warning(
            f"[RETRY-POOL] ❌ 两阶段重试均失败: 总计尝试={len(attempted_servers)}个服务器",
            extra={"log_type": "ALERT", "scenario": scenario}
        )
        return None, False
    
    async def _phase1_retry(
        self,
        task_func: Callable[[AsyncTdxHq_API], Any],
        attempted_servers: List[str],
        scenario: str,
    ) -> Optional[Any]:
        """阶段1重试：混合池"""
        remaining_attempts = self.phase1_max_attempts
        
        while remaining_attempts > 0:
            # 获取混合服务器池（排除已尝试的）
            servers = self.server_pool_manager.get_mixed_servers(
                shuffle=True,
                exclude=attempted_servers if attempted_servers else None
            )
            
            if not servers:
                logger.debug(
                    f"[RETRY-POOL] 阶段1: 无可用服务器（已排除{len(attempted_servers)}个）",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                break
            
            # 尝试每个服务器直到成功或全部失败
            for server_info in servers:
                if remaining_attempts <= 0:
                    break
                    
                server_key = f"{server_info['ip']}:{server_info['port']}"
                result = await self._try_single_server(
                    task_func,
                    server_info,
                    attempted_servers,
                    scenario,
                    phase=1,
                )
                
                remaining_attempts -= 1
                
                if result is not None:
                    return result
                
                # 服务器已添加到 attempted_servers，继续下一个
                logger.debug(
                    f"[RETRY-POOL] 阶段1: 服务器 {server_key} 失败，剩余尝试={remaining_attempts}",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
            
            # 如果所有可用服务器都尝试过了，退出
            if not servers:
                break
        
        return None
    
    async def _phase2_retry(
        self,
        task_func: Callable[[AsyncTdxHq_API], Any],
        attempted_servers: List[str],
        scenario: str,
    ) -> Optional[Any]:
        """阶段2重试：最快30%服务器"""
        remaining_attempts = self.phase2_max_attempts
        
        while remaining_attempts > 0:
            # 获取最快30%服务器（排除已尝试的）
            servers = self.server_pool_manager.get_top_30_percent_ipv4_servers(
                shuffle=True,
                exclude=attempted_servers if attempted_servers else None
            )
            
            if not servers:
                logger.debug(
                    f"[RETRY-POOL] 阶段2: 无可用服务器（已排除{len(attempted_servers)}个）",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                break
            
            # 尝试每个服务器直到成功或全部失败
            for server_info in servers:
                if remaining_attempts <= 0:
                    break
                    
                server_key = f"{server_info['ip']}:{server_info['port']}"
                result = await self._try_single_server(
                    task_func,
                    server_info,
                    attempted_servers,
                    scenario,
                    phase=2,
                )
                
                remaining_attempts -= 1
                
                if result is not None:
                    return result
                
                # 服务器已添加到 attempted_servers，继续下一个
                logger.debug(
                    f"[RETRY-POOL] 阶段2: 服务器 {server_key} 失败，剩余尝试={remaining_attempts}",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
            
            # 如果所有可用服务器都尝试过了，退出
            if not servers:
                break
        
        return None
    
    async def _try_single_server(
        self,
        task_func: Callable[[AsyncTdxHq_API], Any],
        server_info: Dict[str, Any],
        attempted_servers: List[str],
        scenario: str,
        phase: int,
    ) -> Optional[Any]:
        """
        尝试单个服务器
        
        Args:
            task_func: 任务函数
            server_info: 服务器信息 {"ip": ..., "port": ..., "name": ..., "ping_time": ...}
            attempted_servers: 已尝试服务器列表（会被更新）
            scenario: 场景标识
            phase: 当前阶段（1或2）
        
        Returns:
            任务结果，失败返回 None
        """
        server_key = f"{server_info['ip']}:{server_info['port']}"
        server_name = server_info.get('name', server_key)
        
        # 记录尝试
        attempted_servers.append(server_key)
        
        api = None
        try:
            logger.debug(
                f"[RETRY-POOL] 阶段{phase}: 尝试服务器 {server_name} ({server_key}), "
                f"延迟={server_info.get('ping_time', 0):.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            
            # 创建连接
            api = AsyncTdxHq_API()
            connected = await asyncio.wait_for(
                api.connect(server_info['ip'], server_info['port']),
                timeout=self.connection_timeout
            )
            
            if not connected:
                logger.debug(
                    f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 连接失败",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                return None
            
            # 执行任务
            result = await task_func(api)
            
            # 检查结果有效性
            if result is None:
                logger.debug(
                    f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 任务返回 None",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                return None
            
            # 成功
            logger.debug(
                f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 任务成功",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return result
            
        except asyncio.TimeoutError:
            logger.debug(
                f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 连接超时",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return None
        except Exception as e:
            logger.debug(
                f"[RETRY-POOL] 阶段{phase}: 服务器 {server_key} 异常: {type(e).__name__}: {e}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            return None
        finally:
            # 确保连接关闭
            if api:
                try:
                    await api.disconnect()
                except Exception:
                    pass
