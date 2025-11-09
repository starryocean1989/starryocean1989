#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复native_ipc/ipc_async.c中的NATIVE_LOG调用参数问题
"""

import re

def fix_native_log_calls(content):
    # 模式1: , NULL); 替换为 );
    content = re.sub(r', NULL\);', ');', content)

    # 模式2: NATIVE_LOG_INFO(..., details) 替换为 NATIVE_LOG_INFO_DETAILS(..., details)
    content = re.sub(
        r'NATIVE_LOG_INFO\(([^,]+),\s*([^,]+),\s*([^,]+),\s*"([^"]+)",\s*([^)]+)\)',
        r'NATIVE_LOG_INFO_DETAILS(\1, \2, \3, "\4", \5)',
        content
    )

    # 模式3: NATIVE_LOG_DEBUG(..., details) 替换为 NATIVE_LOG_DEBUG_DETAILS(..., details)
    content = re.sub(
        r'NATIVE_LOG_DEBUG\(([^,]+),\s*([^,]+),\s*([^,]+),\s*"([^"]+)",\s*([^)]+)\)',
        r'NATIVE_LOG_DEBUG_DETAILS(\1, \2, \3, "\4", \5)',
        content
    )

    # 模式4: NATIVE_LOG_WARNING(..., details) 替换为 NATIVE_LOG_WARNING_DETAILS(..., details)
    content = re.sub(
        r'NATIVE_LOG_WARNING\(([^,]+),\s*([^,]+),\s*([^,]+),\s*"([^"]+)",\s*([^)]+)\)',
        r'NATIVE_LOG_WARNING_DETAILS(\1, \2, \3, "\4", \5)',
        content
    )

    # 模式5: NATIVE_LOG_ERROR(..., details) 替换为 NATIVE_LOG_ERROR_DETAILS(..., details)
    content = re.sub(
        r'NATIVE_LOG_ERROR\(([^,]+),\s*([^,]+),\s*([^,]+),\s*"([^"]+)",\s*([^)]+)\)',
        r'NATIVE_LOG_ERROR_DETAILS(\1, \2, \3, "\4", \5)',
        content
    )

    # 模式6: NATIVE_LOG_CRITICAL(..., details) 替换为 NATIVE_LOG_CRITICAL_DETAILS(..., details)
    content = re.sub(
        r'NATIVE_LOG_CRITICAL\(([^,]+),\s*([^,]+),\s*([^,]+),\s*"([^"]+)",\s*([^)]+)\)',
        r'NATIVE_LOG_CRITICAL_DETAILS(\1, \2, \3, "\4", \5)',
        content
    )

    return content

def main():
    input_file = 'native_ipc/ipc_async.c'
    output_file = 'native_ipc/ipc_async_fixed.c'

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()

        fixed_content = fix_native_log_calls(content)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(fixed_content)

        print(f"成功修复文件: {output_file}")

        # 检查剩余的NULL参数
        null_count = fixed_content.count(', NULL);')
        if null_count > 0:
            print(f"警告: 还有 {null_count} 个NULL参数未修复")
        else:
            print("所有NULL参数已修复")

    except Exception as e:
        print(f"错误: {e}")

if __name__ == '__main__':
    main()
