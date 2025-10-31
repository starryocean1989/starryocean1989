# -*- coding: utf-8 -*-
"""检查实际数据文件"""
from pathlib import Path

data_path = Path('data/kline')
print(f'数据目录: {data_path.absolute()}')
print(f'存在: {data_path.exists()}')

if data_path.exists():
    files = list(data_path.glob('*.parquet'))
    print(f'parquet文件数: {len(files)}')
    
    if files:
        print(f'\n前10个文件:')
        for f in sorted(files)[:10]:
            print(f'  {f.name}')
    else:
        print('\n❌ 没有找到任何parquet文件')
else:
    print('\n❌ 数据目录不存在')
