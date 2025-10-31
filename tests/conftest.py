# -*- coding: utf-8 -*-
"""顶层测试配置文件

配置pytest插件和全局fixture
"""

# 从e2e fixtures模块导入
pytest_plugins = ["tests.e2e.fixtures.network_request_fixtures"]
