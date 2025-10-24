# -*- coding: utf-8 -*-
"""直接输出错误日志到文件"""
import sqlite3
import sys

try:
    conn = sqlite3.connect('data/terminal.db')
    cursor = conn.cursor()
    
    # 查看表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    output = []
    output.append("=" * 80)
    output.append(f"数据库中的表: {tables}")
    output.append("=" * 80)
    
    if 'system_logs' in tables:
        # 查询所有ERROR和WARNING
        cursor.execute('''
            SELECT timestamp, level, module, logger, message 
            FROM system_logs 
            WHERE level IN ('ERROR', 'WARNING', 'CRITICAL')
            ORDER BY timestamp DESC 
            LIMIT 50
        ''')
        
        rows = cursor.fetchall()
        output.append(f"\n找到 {len(rows)} 条ERROR/WARNING/CRITICAL日志:\n")
        
        for row in rows:
            output.append(f"\n{'='*80}")
            output.append(f"时间: {row[0]}")
            output.append(f"级别: {row[1]}")
            output.append(f"模块: {row[2]}")
            output.append(f"Logger: {row[3]}")
            output.append(f"消息: {row[4]}")
    else:
        output.append("\n警告: system_logs表不存在！")
    
    # 写入文件
    with open('error_logs_output.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(output))
    
    # 也打印到stdout
    print('\n'.join(output))
    
    conn.close()
    print("\n结果已保存到 error_logs_output.txt")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()

