# -*- coding: utf-8 -*-
"""监控进程入口 - 简单入口文件

这个文件是为了兼容启动脚本而创建的。
实际的监控进程代码已经合并到 monitor_system.py 中。
"""

if __name__ == "__main__":
    import sys
    from pathlib import Path

    # 确保项目根目录在sys.path中（监控进程独立运行时需要）
    project_root = Path(__file__).parent.parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # 导入并运行合并后的主函数
    from backend.infrastructure.system_vnpy.monitor_system import main

    main()
