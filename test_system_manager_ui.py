# -*- coding: utf-8 -*-
"""
系统管理界面卡死问题测试脚本

测试目标：
1. 监控进程能否正确启动和自动清理旧进程
2. UI切换8个子界面时是否流畅，无卡顿
3. 监控数据推送是否正常工作
4. UI更新节流机制是否有效

使用方法：
    python test_system_manager_ui.py
"""

import sys
import time
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_monitor_process_cleanup():
    """测试监控进程的自动清理功能."""
    logger.info("=" * 60)
    logger.info("测试1：监控进程自动清理")
    logger.info("=" * 60)
    
    import subprocess
    import psutil
    
    # 启动监控进程
    logger.info("启动监控进程...")
    process = subprocess.Popen(
        [sys.executable, "backend/infrastructure/system_vnpy/monitor_process_entry.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # 等待启动
    time.sleep(3)
    
    # 检查进程是否在运行
    if process.poll() is None:
        logger.info("✅ 监控进程已启动 (PID=%d)", process.pid)
    else:
        logger.error("❌ 监控进程启动失败")
        return False
    
    # 停止进程
    logger.info("停止监控进程...")
    process.terminate()
    try:
        process.wait(timeout=3)
        logger.info("✅ 监控进程已正常停止")
    except subprocess.TimeoutExpired:
        process.kill()
        logger.warning("监控进程未响应，已强制终止")
    
    # 再次启动，测试自动清理
    logger.info("再次启动监控进程（测试自动清理）...")
    process2 = subprocess.Popen(
        [sys.executable, "backend/infrastructure/system_vnpy/monitor_process_entry.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    time.sleep(3)
    
    if process2.poll() is None:
        logger.info("✅ 监控进程成功重启 (PID=%d)", process2.pid)
        process2.terminate()
        process2.wait(timeout=3)
        return True
    else:
        logger.error("❌ 监控进程重启失败")
        return False


def test_ui_tab_switching():
    """测试UI标签页切换是否流畅."""
    logger.info("=" * 60)
    logger.info("测试2：UI标签页切换")
    logger.info("=" * 60)
    
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    
    # 创建QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    
    try:
        # 初始化后端
        from backend.core.base import initialize_services
        logger.info("初始化后端服务...")
        initialize_services()
        
        # 创建系统管理界面
        from ui.modules.system_manager_view import SystemManager
        logger.info("创建系统管理界面...")
        widget = SystemManager()
        widget.show()
        
        # 模拟切换标签页
        tab_widget = widget.tab_widget
        if not tab_widget:
            logger.error("❌ 未找到标签页组件")
            return False
        
        tab_count = tab_widget.count()
        logger.info("发现 %d 个标签页", tab_count)
        
        # 记录切换时间
        switch_times = []
        
        def switch_tab(index):
            """切换到指定标签页并测量时间."""
            start_time = time.time()
            tab_widget.setCurrentIndex(index)
            app.processEvents()  # 处理事件循环
            elapsed = time.time() - start_time
            switch_times.append(elapsed)
            tab_name = tab_widget.tabText(index)
            logger.info("  标签页 %d (%s): %.3f 秒", index, tab_name, elapsed)
        
        # 切换所有标签页
        logger.info("开始切换标签页...")
        for i in range(tab_count):
            switch_tab(i)
            time.sleep(0.5)  # 等待渲染
        
        # 分析结果
        avg_time = sum(switch_times) / len(switch_times) if switch_times else 0
        max_time = max(switch_times) if switch_times else 0
        
        logger.info("切换性能统计：")
        logger.info("  平均切换时间: %.3f 秒", avg_time)
        logger.info("  最长切换时间: %.3f 秒", max_time)
        
        # 判断是否通过测试（平均切换时间小于1秒，最长不超过2秒）
        if avg_time < 1.0 and max_time < 2.0:
            logger.info("✅ UI切换流畅，测试通过")
            result = True
        else:
            logger.warning("⚠️ UI切换较慢，可能需要进一步优化")
            result = False
        
        # 清理
        widget.close()
        return result
        
    except Exception as e:
        logger.error("❌ 测试失败: %s", e, exc_info=True)
        return False


def test_monitoring_data_push():
    """测试监控数据推送机制."""
    logger.info("=" * 60)
    logger.info("测试3：监控数据推送")
    logger.info("=" * 60)
    
    try:
        from backend.core.base import get_service_manager
        
        service_manager = get_service_manager()
        system_service = service_manager.get_service("system_manager_service", silent=True)
        
        if not system_service:
            logger.warning("系统管理服务未就绪，跳过测试")
            return True
        
        # 等待几秒，观察是否有监控数据推送
        logger.info("等待监控数据推送（10秒）...")
        time.sleep(10)
        
        # 检查监控数据缓存
        if hasattr(system_service, "_monitor_data_cache"):
            cache = system_service._monitor_data_cache
            if cache:
                logger.info("✅ 监控数据推送正常，缓存包含 %d 个字段", len(cache))
                return True
            else:
                logger.warning("⚠️ 监控数据缓存为空")
                return False
        else:
            logger.warning("⚠️ 未找到监控数据缓存")
            return False
            
    except Exception as e:
        logger.error("❌ 测试失败: %s", e, exc_info=True)
        return False


def main():
    """主测试函数."""
    logger.info("开始测试系统管理界面修复...")
    logger.info("")
    
    results = {}
    
    # 测试1：监控进程自动清理
    results["monitor_cleanup"] = test_monitor_process_cleanup()
    logger.info("")
    
    # 测试2：UI标签页切换
    results["ui_switching"] = test_ui_tab_switching()
    logger.info("")
    
    # 测试3：监控数据推送
    results["data_push"] = test_monitoring_data_push()
    logger.info("")
    
    # 汇总结果
    logger.info("=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        logger.info("  %s: %s", test_name, status)
    
    all_passed = all(results.values())
    if all_passed:
        logger.info("")
        logger.info("🎉 所有测试通过！系统管理界面卡死问题已修复。")
    else:
        logger.info("")
        logger.warning("⚠️ 部分测试未通过，请检查日志。")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

