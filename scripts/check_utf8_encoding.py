# -*- coding: utf-8 -*-
"""检查并修复Python文件的UTF-8编码声明."""
import os
from pathlib import Path

def check_utf8_declaration(file_path):
    """检查文件首行是否有UTF-8声明."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            return 'coding' in first_line and 'utf-8' in first_line
    except Exception as e:
        print(f'  ❌ 读取文件失败: {file_path} - {e}')
        return True  # 跳过有问题的文件

def add_utf8_declaration(file_path):
    """给文件添加UTF-8声明."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('# -*- coding: utf-8 -*-\n')
            f.write(content)
        return True
    except Exception as e:
        print(f'  ❌ 修复失败: {file_path} - {e}')
        return False

# 统计信息
total_files = 0
missing_declaration = 0
fixed_files = 0
failed_files = 0

print('=' * 70)
print('🔍 检查Python文件UTF-8编码声明')
print('=' * 70)

# 检查backend和ui目录
for directory in ['backend', 'ui']:
    print(f'\n📁 正在检查目录: {directory}/')
    
    for py_file in Path(directory).rglob('*.py'):
        total_files += 1
        
        if not check_utf8_declaration(py_file):
            missing_declaration += 1
            print(f'  ⚠️  缺少UTF-8声明: {py_file}')
            
            if add_utf8_declaration(py_file):
                fixed_files += 1
                print(f'  ✅ 已添加UTF-8声明')
            else:
                failed_files += 1

print('\n' + '=' * 70)
print('📊 检查结果统计')
print('=' * 70)
print(f'总文件数: {total_files}')
print(f'缺少声明: {missing_declaration}')
print(f'成功修复: {fixed_files}')
print(f'修复失败: {failed_files}')

if missing_declaration == 0:
    print('\n✅ 所有Python文件都有UTF-8编码声明！')
elif fixed_files == missing_declaration:
    print('\n✅ 所有缺失的UTF-8声明已成功添加！')
else:
    print(f'\n⚠️  还有 {missing_declaration - fixed_files} 个文件需要手动处理')

print('=' * 70)

