# -*- coding: utf-8 -*-
"""查询错误日志的临时脚本"""
import sqlite3
from datetime import datetime, timedelta

# 连接数据库
conn = sqlite3.connect('data/logs.db')
cursor = conn.cursor()

print("=" * 80)
print("最近30分钟的ERROR和CRITICAL日志")
print("=" * 80)

# 查询最近30分钟的错误
cursor.execute('''
    SELECT timestamp, level, logger, message 
    FROM logs 
    WHERE level IN ('ERROR', 'CRITICAL') 
    AND timestamp > datetime('now', '-30 minutes')
    ORDER BY timestamp DESC 
    LIMIT 100
''')

rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f"\n时间: {row[0]}")
        print(f"级别: {row[1]}")
        print(f"记录器: {row[2]}")
        print(f"消息: {row[3]}")
        print("-" * 80)
else:
    print("没有找到ERROR或CRITICAL级别的日志")

print("\n" + "=" * 80)
print("系统管理相关的WARNING日志")
print("=" * 80)

# 查询系统管理相关的警告
cursor.execute('''
    SELECT timestamp, level, logger, message 
    FROM logs 
    WHERE logger LIKE '%system%' 
    AND level = 'WARNING'
    AND timestamp > datetime('now', '-30 minutes')
    ORDER BY timestamp DESC 
    LIMIT 50
''')

rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f"\n时间: {row[0]}")
        print(f"级别: {row[1]}")
        print(f"记录器: {row[2]}")
        print(f"消息: {row[3]}")
        print("-" * 80)
else:
    print("没有找到系统管理相关的WARNING日志")

print("\n" + "=" * 80)
print("UI相关的错误日志")
print("=" * 80)

# 查询UI相关的错误
cursor.execute('''
    SELECT timestamp, level, logger, message 
    FROM logs 
    WHERE (logger LIKE '%ui%' OR logger LIKE '%SystemManager%')
    AND level IN ('ERROR', 'WARNING')
    AND timestamp > datetime('now', '-30 minutes')
    ORDER BY timestamp DESC 
    LIMIT 50
''')

rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f"\n时间: {row[0]}")
        print(f"级别: {row[1]}")
        print(f"记录器: {row[2]}")
        print(f"消息: {row[3]}")
        print("-" * 80)
else:
    print("没有找到UI相关的错误日志")

conn.close()

