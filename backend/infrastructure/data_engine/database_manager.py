# -*- coding: utf-8 -*-
"""
数据库管理器模块.

提供数据库连接,表创建,数据插入等功能的数据库管理类.
支持SQLite数据库操作,包括行情数据,数据源配置和查询历史的存储.
"""

import logging
import sqlite3
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class DatabaseManager:
    """数据库管理器."""

    def __init__(self, db_path: "Path"):
        """初始化数据库管理器."""
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None
        self.logger = logging.getLogger(__name__)

    def initialize(self) -> None:
        """初始化数据库表结构."""
        try:
            self.connection = sqlite3.connect(str(self.db_path))
            self.connection.row_factory = sqlite3.Row

            # 创建表
            self.create_tables()

            self.logger.info("数据库初始化成功")

        except Exception as e:
            self.logger.error("数据库初始化失败: %s", e)
            raise

    def create_tables(self) -> None:
        """创建数据库表."""
        if not self.connection:
            return

        cursor = self.connection.cursor()

        # 行情数据表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            name TEXT,
            price REAL,
            volume INTEGER,
            timestamp TEXT,
            category TEXT,
            source TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 数据源配置表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS data_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT UNIQUE NOT NULL,
            source_name TEXT,
            source_type TEXT,
            host TEXT,
            port INTEGER,
            database TEXT,
            username TEXT,
            password TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 查询历史表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS query_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id TEXT UNIQUE NOT NULL,
            source_id TEXT,
            data_type TEXT,
            symbol TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT,
            result_count INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        self.connection.commit()
        cursor.close()

    def insert_quotes(self, quotes: List[Dict[str, Any]]) -> int:
        """插入行情数据."""
        if not self.connection:
            raise RuntimeError("数据库未初始化")

        cursor = self.connection.cursor()
        inserted_count = 0

        try:
            for quote in quotes:
                cursor.execute(
                    """
                    INSERT INTO quotes (
                        symbol, name, price, volume, timestamp, category,
                        source
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        quote.get("symbol"),
                        quote.get("name"),
                        quote.get("price"),
                        quote.get("volume"),
                        quote.get("timestamp"),
                        quote.get("category"),
                        quote.get("source"),
                    ),
                )
                inserted_count += 1

            self.connection.commit()
            self.logger.info("成功插入 %d 条行情数据", inserted_count)

        except Exception as e:
            self.connection.rollback()
            self.logger.error("插入行情数据失败: %s", e)
            raise

        finally:
            cursor.close()

        return inserted_count

    def close(self) -> None:
        """关闭数据库连接."""
        if self.connection:
            self.connection.close()
            self.connection = None
            self.logger.info("数据库连接已关闭")
