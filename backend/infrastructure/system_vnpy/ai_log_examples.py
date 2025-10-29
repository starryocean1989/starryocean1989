# -*- coding: utf-8 -*-
"""
AI日志系统使用示例.

演示如何在核心流程中使用AI日志系统。
"""

import logging
from backend.infrastructure.system_vnpy.unified_log_system import (
    ai_log_process,
    ProcessNames,
    start_ai_process,
    end_ai_process,
)


# =============================================================================
# 示例1：使用上下文管理器（推荐）
# =============================================================================

def example_download_with_context():
    """使用上下文管理器的数据下载示例."""
    logger = logging.getLogger("data_center.download")
    
    # 使用with语句自动管理AI日志文件
    with ai_log_process(
        ProcessNames.DOWNLOAD_KLINE,
        metadata={"symbol_count": 5000, "frequency": "1d"}
    ):
        logger.info("开始下载K线数据...")
        logger.info("连接服务器...")
        
        # 业务逻辑
        for i in range(10):
            logger.debug(f"下载进度: {i*10}%")
        
        logger.info("下载完成")
    # with块结束时自动结束AI日志流程


# =============================================================================
# 示例2：手动控制AI日志流程
# =============================================================================

def example_symbol_refresh_manual():
    """手动控制的品种列表刷新示例."""
    logger = logging.getLogger("data_center.symbol")
    
    # 手动开始AI日志流程
    ai_log_file = start_ai_process(
        ProcessNames.SYMBOL_REFRESH,
        metadata={"source": "tdx", "markets": ["SH", "SZ"]}
    )
    logger.info(f"AI日志文件: {ai_log_file}")
    
    try:
        logger.info("开始刷新品种列表...")
        logger.info("连接通达信服务器...")
        
        # 业务逻辑
        logger.info("获取上证A股列表...")
        logger.info("获取深证A股列表...")
        logger.info("合并品种列表...")
        
        logger.info("品种列表刷新完成")
        
        # 成功结束
        end_ai_process(success=True, summary="成功刷新5000个品种")
        
    except Exception as e:
        logger.exception("品种列表刷新失败")
        # 失败结束
        end_ai_process(success=False, summary=f"刷新失败: {e}")
        raise


# =============================================================================
# 示例3：数据质量扫描
# =============================================================================

def example_quality_scan():
    """数据质量扫描示例."""
    logger = logging.getLogger("data_center.quality")
    
    with ai_log_process(
        ProcessNames.QUALITY_SCAN,
        metadata={
            "base_date": "2024-01-01",
            "symbol_count": 5000,
            "scan_type": "completeness"
        }
    ):
        logger.info("开始数据质量扫描...")
        
        # 扫描过程
        logger.info("检查数据完整性...")
        logger.info("检查数据连续性...")
        logger.info("检查数据准确性...")
        
        # 发现问题
        logger.warning("发现数据缺失: 600000 (2024-12-25 至 2024-12-31)")
        logger.warning("发现数据缺失: 000001 (2024-12-30 至 2024-12-31)")
        
        logger.info("质量扫描完成")


# =============================================================================
# 示例4：服务初始化流程
# =============================================================================

def example_service_init():
    """服务初始化示例（在服务类的_do_initialize中使用）."""
    logger = logging.getLogger("services.data_center")
    stage_logger = logging.getLogger("services.data_center.stage")
    
    # 注意：服务初始化通常不需要独立的AI日志流程
    # 因为它是启动流程的一部分，会被启动流程的AI日志捕获
    
    stage_logger.info("数据中心服务初始化开始")
    
    logger.debug("初始化任务调度器...")
    logger.debug("初始化ChinaStockEngine...")
    logger.debug("加载品种列表缓存...")
    
    stage_logger.info("数据中心服务初始化完成")


# =============================================================================
# 使用建议
# =============================================================================

"""
AI日志系统使用建议：

1. **何时使用AI日志流程**：
   - 用户主动触发的操作（手动下载、手动扫描等）
   - 长时间运行的任务（批量下载、质量扫描）
   - 可能失败的关键流程（策略回测、交易执行）
   
2. **何时不使用AI日志流程**：
   - 简单的查询操作
   - 高频调用的函数
   - 已经在其他AI日志流程内部的子流程
   
3. **日志级别选择**：
   - DEBUG: 详细的调试信息（步骤、变量值）
   - INFO: 流程关键节点（开始、完成）
   - WARNING: 非致命问题（数据缺失、超时重试）
   - ERROR: 严重错误（失败、异常）
   
4. **元数据设计**：
   - 包含关键参数（品种数量、时间范围）
   - 便于AI理解上下文
   - 不要包含敏感信息
   
5. **异常处理**：
   - 使用logger.exception()记录完整堆栈
   - 在end_ai_process()中标记失败
   - 包含失败原因摘要
"""
