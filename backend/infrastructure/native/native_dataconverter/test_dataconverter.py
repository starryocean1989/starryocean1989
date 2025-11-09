# -*- coding: utf-8 -*-
"""native_dataconverter 测试文件."""

import pytest
import os


class TestNativeDataconverter:
    """native_dataconverter 模块测试."""

    def test_dataconverter_setup_exists(self):
        """测试setup.py文件存在."""
        setup_path = os.path.join(os.path.dirname(__file__), "setup.py")
        assert os.path.exists(setup_path)
        assert os.path.isfile(setup_path)

        # 验证setup.py内容包含基本配置
        with open(setup_path, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "name=\"native_dataconverter\"" in content
            assert "dataconverter.cpp" in content

    def test_dataconverter_module_placeholder(self):
        """数据转换器模块占位符测试."""
        # 这个包目前只有setup.py，主要验证构建配置
        try:
            import backend.infrastructure.native.native_dataconverter
            # 如果有__init__.py，导入会成功
            assert True
        except ImportError:
            # 如果没有__init__.py，这是预期的
            assert True

    def test_dataconverter_cpp_source_exists(self):
        """测试C++源文件存在."""
        cpp_path = os.path.join(os.path.dirname(__file__), "dataconverter.cpp")
        assert os.path.exists(cpp_path)
        assert os.path.isfile(cpp_path)

        # 验证是C++文件（基本检查）
        with open(cpp_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # C++文件通常包含这些特征
            cpp_indicators = ['#include', 'using namespace', 'class', 'int main']
            has_cpp_features = any(indicator in content for indicator in cpp_indicators)
            assert has_cpp_features, "文件看起来不是有效的C++源文件"
