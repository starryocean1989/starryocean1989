# -*- coding: utf-8 -*-
"""
启动日志检查脚本
在启动后运行此脚本,检查terminal输出和log文件的完整性
"""

import re
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

def check_log_file(log_file: Path) -> Dict:
    """检查日志文件内容"""
    print(f"\n{'='*80}")
    print(f"检查日志文件: {log_file.name}")
    print(f"{'='*80}")
    
    if not log_file.exists():
        print(f"❌ 文件不存在: {log_file}")
        return {"success": False, "reason": "文件不存在"}
    
    # 读取文件内容
    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    file_size = log_file.stat().st_size
    print(f"文件大小: {file_size} bytes")
    print(f"总行数: {len(lines)}")
    
    # 统计各级别日志
    debug_count = len([line for line in lines if '[DEBUG' in line])
    info_count = len([line for line in lines if '[INFO' in line])
    warning_count = len([line for line in lines if '[WARNING' in line])
    error_count = len([line for line in lines if '[ERROR' in line])
    critical_count = len([line for line in lines if '[CRITICAL' in line])
    
    print(f"\n级别统计:")
    print(f"  DEBUG: {debug_count}")
    print(f"  INFO: {info_count}")
    print(f"  WARNING: {warning_count}")
    print(f"  ERROR: {error_count}")
    print(f"  CRITICAL: {critical_count}")
    
    # 检查是否包含必要的阶段日志
    stages = [
        ("环境准备阶段", r"env_setup"),
        ("日志系统初始化", r"logging_init"),
        ("Qt框架初始化", r"qt_framework"),
        ("后端服务初始化", r"backend_init"),
        ("UI激活", r"ui_activation"),
    ]
    
    print(f"\n阶段检查:")
    stage_results = {}
    for stage_name, pattern in stages:
        matches = [line for line in lines if re.search(pattern, line, re.IGNORECASE)]
        has_stage = len(matches) > 0
        status = "✅" if has_stage else "⚠️"
        print(f"  {status} {stage_name}: {len(matches)} 条日志")
        stage_results[stage_name] = has_stage
    
    # 检查是否有统计信息
    has_statistics = any("日志统计" in line for line in lines)
    print(f"\n{'✅' if has_statistics else '❌'} 包含日志统计信息")
    
    # 检查是否有开始/结束标记
    has_start = any("事件日志文件" in line for line in lines)
    has_end = any("事件结束" in line for line in lines)
    print(f"{'✅' if has_start else '❌'} 包含开始标记")
    print(f"{'✅' if has_end else '❌'} 包含结束标记")
    
    # 检查错误日志内容
    if error_count > 0 or critical_count > 0:
        print(f"\n⚠️ 发现错误日志:")
        error_lines = [line for line in lines if '[ERROR' in line or '[CRITICAL' in line]
        for line in error_lines[:10]:  # 只显示前10条
            print(f"  {line.strip()}")
        if len(error_lines) > 10:
            print(f"  ... 还有 {len(error_lines) - 10} 条")
    
    # 验证通过条件
    success = (
        file_size > 0 and
        len(lines) > 0 and
        (debug_count + info_count) > 0 and
        has_start and
        has_end and
        has_statistics
    )
    
    result = {
        "success": success,
        "file_size": file_size,
        "total_lines": len(lines),
        "debug_count": debug_count,
        "info_count": info_count,
        "warning_count": warning_count,
        "error_count": error_count,
        "critical_count": critical_count,
        "has_statistics": has_statistics,
        "has_start": has_start,
        "has_end": has_end,
        "stages": stage_results,
    }
    
    print(f"\n{'✅ 检查通过' if success else '❌ 检查失败'}")
    
    return result

def find_latest_startup_log() -> Path:
    """查找最新的启动日志文件"""
    logs_dir = Path("logs")
    
    if not logs_dir.exists():
        print(f"❌ 日志目录不存在: {logs_dir.absolute()}")
        return None
    
    # 查找所有application_startup日志文件
    startup_logs = list(logs_dir.glob("application_startup_*.log"))
    
    if not startup_logs:
        print(f"❌ 未找到启动日志文件")
        return None
    
    # 按修改时间排序,返回最新的
    latest_log = max(startup_logs, key=lambda p: p.stat().st_mtime)
    
    return latest_log

def check_all_logs():
    """检查所有日志文件"""
    print("="*80)
    print("启动日志完整性检查")
    print("="*80)
    print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 查找最新的启动日志
    latest_log = find_latest_startup_log()
    
    if not latest_log:
        print("\n❌ 未找到启动日志文件")
        return False
    
    print(f"\n找到最新启动日志: {latest_log.name}")
    modified_time = datetime.fromtimestamp(latest_log.stat().st_mtime)
    print(f"修改时间: {modified_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 检查日志文件
    result = check_log_file(latest_log)
    
    # 打印详细结果
    print("\n" + "="*80)
    print("检查结果总结")
    print("="*80)
    
    if result["success"]:
        print("✅ 日志文件检查通过")
        print(f"\n关键指标:")
        print(f"  - 文件大小: {result['file_size']} bytes")
        print(f"  - 总行数: {result['total_lines']}")
        print(f"  - DEBUG日志: {result['debug_count']}")
        print(f"  - INFO日志: {result['info_count']}")
        print(f"  - WARNING日志: {result['warning_count']}")
        print(f"  - ERROR日志: {result['error_count']}")
        print(f"  - CRITICAL日志: {result['critical_count']}")
        
        print(f"\n结构完整性:")
        print(f"  - 开始标记: {'✅' if result['has_start'] else '❌'}")
        print(f"  - 结束标记: {'✅' if result['has_end'] else '❌'}")
        print(f"  - 统计信息: {'✅' if result['has_statistics'] else '❌'}")
        
        print(f"\n阶段覆盖:")
        for stage_name, has_stage in result['stages'].items():
            print(f"  - {stage_name}: {'✅' if has_stage else '⚠️'}")
        
        return True
    else:
        print("❌ 日志文件检查失败")
        return False

def main():
    """主函数"""
    try:
        success = check_all_logs()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ 检查被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 检查过程异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
