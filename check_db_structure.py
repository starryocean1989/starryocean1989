# -*- coding: utf-8 -*-
"""检查数据库结构"""
import sqlite3

conn = sqlite3.connect('data/logs.db')
cursor = conn.cursor()

# 查看所有表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("数据库中的表:")
for table in tables:
    print(f"  - {table[0]}")

# 查看logs表结构
print("\nlogs表结构:")
cursor.execute("PRAGMA table_info(logs)")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]} ({col[2]})")

# 查看最近的几条日志
print("\n最近10条日志（任意级别）:")
cursor.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 10")
rows = cursor.fetchall()
for row in rows:
    print(row)

conn.close()

