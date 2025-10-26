# -*- coding: utf-8 -*-
"""Ã¥Â·Â¥Ã¥ÂÂ·Ã¥ÂÂÃ§Â®Â¡Ã§ÂÂÃ¦Â¨Â¡Ã¥ÂÂ - Ã¥Â®ÂÃ¦ÂÂ´Ã¥ÂÂÃ¥Â¹Â¶Ã§ÂÂÃ¯Â¼Âmanagers.py + tools.pyÃ¯Â¼Â.

Ã¦ÂÂ¬Ã¦ÂÂÃ¤Â»Â¶Ã¥ÂÂÃ¥ÂÂ«Ã¦ÂÂÃ¦ÂÂÃ§Â®Â¡Ã§ÂÂÃ¥ÂÂÃ¥Â·Â¥Ã¥ÂÂ·Ã¥ÂÂÃ¨ÂÂ½Ã¯Â¼Â
- Part 1: Ã¦ÂÂÃ¥ÂÂ¡/Ã¨Â¿ÂÃ§Â¨Â/Ã¥Â®ÂÃ¥ÂÂ¨Ã§Â®Â¡Ã§ÂÂÃ¯Â¼ÂÃ¦ÂÂ¥Ã¨ÂÂª managers.pyÃ¯Â¼Â
- Part 2: Ã¨Â¯ÂÃ¦ÂÂ­/Ã¦ÂÂÃ¤Â»Â¶/Ã§Â½ÂÃ§Â»Â/Ã¦ÂÂ§Ã¨ÂÂ½Ã¥Â·Â¥Ã¥ÂÂ·Ã¯Â¼ÂÃ¦ÂÂ¥Ã¨ÂÂª tools.pyÃ¯Â¼Â
"""

import base64
import datetime
import fnmatch
import glob
import logging
import os
import re
import secrets
import shutil
import socket
import ssl
import stat
import threading
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import psutil
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


# =============================================================================
# Part 1: Ã¦ÂÂÃ¥ÂÂ¡/Ã¨Â¿ÂÃ§Â¨Â/Ã¥Â®ÂÃ¥ÂÂ¨Ã§Â®Â¡Ã§ÂÂÃ¯Â¼ÂÃ¦ÂÂ¥Ã¨ÂÂª managers.pyÃ¯Â¼Â
# =============================================================================


# =============================================================================
# Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂ¥Ã¥ÂºÂ·Ã¦Â£ÂÃ¦ÂÂ¥Ã¥ÂÂÃ©ÂÂÃ¥ÂÂ¯
# =============================================================================


class ServiceHealthChecker:
    """Ã¥Â¢ÂÃ¥Â¼ÂºÃ§ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂ¥Ã¥ÂºÂ·Ã¦Â£ÂÃ¦ÂÂ¥Ã¥ÂÂ¨ - Ã¦ÂÂ¯Ã¦ÂÂÃ¤Â¸ÂÃ¥ÂÂ¡Ã¦ÂÂÃ¦Â ÂÃ£ÂÂÃ¨ÂµÂÃ¦ÂºÂÃ¥ÂÂ Ã§ÂÂ¨Ã£ÂÂÃ¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂÃ¦Â£ÂÃ¦ÂÂ¥."""

    def __init__(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂ¥Ã¥ÂºÂ·Ã¦Â£ÂÃ¦ÂÂ¥Ã¥ÂÂ¨."""
        self.logger = logging.getLogger(__name__)
        self._monitoring_interval = 2  # Ã©Â»ÂÃ¨Â®Â¤2Ã§Â§ÂÃ¦ÂÂ¨Ã©ÂÂÃ©Â¢ÂÃ§ÂÂ
        self._main_process = psutil.Process()

    def set_monitoring_interval(self, interval: int):
        """Ã¨Â®Â¾Ã§Â½Â®Ã§ÂÂÃ¦ÂÂ§Ã¦ÂÂ¨Ã©ÂÂÃ©Â¢ÂÃ§ÂÂ.

        Args:
            interval: Ã¦ÂÂ¨Ã©ÂÂÃ©ÂÂ´Ã©ÂÂÃ¯Â¼ÂÃ§Â§ÂÃ¯Â¼ÂÃ¯Â¼ÂÃ¨ÂÂÃ¥ÂÂ´1-10
        """
        self._monitoring_interval = max(1, min(10, interval))
        self.logger.info("Ã§ÂÂÃ¦ÂÂ§Ã¦ÂÂ¨Ã©ÂÂÃ©Â¢ÂÃ§ÂÂÃ¥Â·Â²Ã¨Â®Â¾Ã§Â½Â®Ã¤Â¸Âº %d Ã§Â§Â", self._monitoring_interval)

    def get_monitoring_interval(self) -> int:
        """Ã¨ÂÂ·Ã¥ÂÂÃ¥Â½ÂÃ¥ÂÂÃ§ÂÂÃ¦ÂÂ§Ã¦ÂÂ¨Ã©ÂÂÃ©Â¢ÂÃ§ÂÂ."""
        return self._monitoring_interval

    def quick_check(self, service_name: str, service_manager) -> Dict[str, Any]:
        """Ã¥Â¿Â«Ã©ÂÂÃ¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂ¥Ã¥ÂºÂ·Ã§ÂÂ¶Ã¦ÂÂÃ¯Â¼ÂÃ¥Â¢ÂÃ¥Â¼ÂºÃ§ÂÂÃ¯Â¼Â.

        Args:
            service_name: Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂÃ§Â§Â°
            service_manager: Ã¦ÂÂÃ¥ÂÂ¡Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨Ã¥Â®ÂÃ¤Â¾Â

        Returns:
            Dict: Ã¦Â£ÂÃ¦ÂÂ¥Ã§Â»ÂÃ¦ÂÂÃ¯Â¼ÂÃ¥ÂÂÃ¥ÂÂ«Ã¥ÂÂºÃ§Â¡ÂÃ¦ÂÂÃ¦Â ÂÃ£ÂÂÃ¤Â¸ÂÃ¥ÂÂ¡Ã¦ÂÂÃ¦Â ÂÃ£ÂÂÃ¨ÂµÂÃ¦ÂºÂÃ¥ÂÂ Ã§ÂÂ¨
        """
        try:
            # Ã¨ÂÂ·Ã¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥Â®ÂÃ¤Â¾Â
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "service_name": service_name,
                    "status": "not_found",
                    "online": False,
                    "response_time_ms": 0,
                    "message": "Ã¦ÂÂÃ¥ÂÂ¡Ã¦ÂÂªÃ¦Â³Â¨Ã¥ÂÂ",
                    "call_count": 0,
                    "success_rate": 0.0,
                    "error_rate": 0.0,
                    "memory_mb": 0.0,
                    "thread_count": 0,
                }

            # Ã¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂÃ¥ÂÂ¡Ã¦ÂÂ¯Ã¥ÂÂ¦Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂ
            is_initialized = getattr(service, "is_initialized", False)

            # Ã¦ÂµÂÃ©ÂÂÃ¥ÂÂÃ¥ÂºÂÃ¦ÂÂ¶Ã©ÂÂ´Ã¯Â¼ÂÃ©ÂÂÃ¨Â¿ÂÃ¨Â°ÂÃ§ÂÂ¨health_checkÃ¯Â¼Â
            start_time = time.time()
            try:
                health_result = service.health_check() if hasattr(service, "health_check") else {}
                response_time_ms = (time.time() - start_time) * 1000

                # Ã¦ÂÂ¶Ã©ÂÂÃ¤Â¸ÂÃ¥ÂÂ¡Ã¦ÂÂÃ¦Â ÂÃ¯Â¼ÂÃ¤Â»ÂÃ¦ÂÂ§Ã¨ÂÂ½Ã¨Â·ÂÃ¨Â¸ÂªÃ¥ÂÂ¨Ã¨ÂÂ·Ã¥ÂÂÃ¯Â¼Â
                call_count = 0
                success_rate = 100.0
                error_rate = 0.0

                try:
                    from backend.services.system_manager_service import performance_tracker

                    # Ã¥Â°ÂÃ¨Â¯ÂÃ¤Â»ÂÃ¦ÂÂ§Ã¨ÂÂ½Ã¨Â·ÂÃ¨Â¸ÂªÃ¥ÂÂ¨Ã¨ÂÂ·Ã¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã§ÂÂ¸Ã¥ÂÂ³Ã¦ÂÂÃ¦Â Â
                    all_metrics = performance_tracker.get_all_metrics()
                    # Ã¦ÂÂ¥Ã¦ÂÂ¾Ã¤Â¸ÂÃ¦ÂÂÃ¥ÂÂ¡Ã§ÂÂ¸Ã¥ÂÂ³Ã§ÂÂÃ¦ÂÂÃ¦Â Â
                    service_metrics = {}
                    for _category, metrics_list in all_metrics.items():
                        # metrics_list Ã¦ÂÂ¯Ã¤Â¸ÂÃ¤Â¸ÂªÃ¥ÂÂÃ¨Â¡Â¨Ã¯Â¼ÂÃ¥ÂÂÃ¥ÂÂ«Ã¥Â¤ÂÃ¤Â¸ÂªÃ¦ÂÂÃ¦Â ÂÃ¥Â­ÂÃ¥ÂÂ¸
                        for metric_dict in metrics_list:
                            # Ã©ÂÂÃ¥ÂÂÃ¥Â­ÂÃ¥ÂÂ¸Ã¤Â¸Â­Ã§ÂÂÃ¦Â¯ÂÃ¤Â¸ÂªÃ¦ÂÂÃ¦Â Â
                            for metric_name, metric_value in metric_dict.items():
                                if service_name.replace("_service", "") in metric_name.lower():
                                    # Ã¥Â­ÂÃ¥ÂÂ¨Ã¦ÂÂÃ¦Â ÂÃ¥ÂÂ¼Ã¯Â¼ÂÃ¦Â³Â¨Ã¦ÂÂÃ¯Â¼ÂÃ¨Â¿ÂÃ©ÂÂÃ§ÂÂ metric_value Ã¥ÂÂ¯Ã¨ÂÂ½Ã¦ÂÂ¯Ã¦ÂÂ°Ã¥ÂÂ¼Ã¯Â¼ÂÃ¤Â¸ÂÃ¦ÂÂ¯Ã¥Â­ÂÃ¥ÂÂ¸Ã¯Â¼Â
                                    if isinstance(metric_value, dict):
                                        service_metrics[metric_name] = metric_value

                    # Ã¨ÂÂÃ¥ÂÂÃ¤Â¸ÂÃ¥ÂÂ¡Ã¦ÂÂÃ¦Â Â
                    if service_metrics:
                        total_calls = sum(m.get("total_calls", 0) for m in service_metrics.values())
                        if total_calls > 0:
                            call_count = total_calls
                            # Ã¨Â®Â¡Ã§Â®ÂÃ¥Â¹Â³Ã¥ÂÂÃ¦ÂÂÃ¥ÂÂÃ§ÂÂ
                            success_rates = [
                                m.get("success_rate", 100) for m in service_metrics.values()
                            ]
                            success_rate = sum(success_rates) / len(success_rates)
                            error_rate = 100.0 - success_rate
                except Exception as e:
                    self.logger.debug("Ã¨ÂÂ·Ã¥ÂÂÃ¤Â¸ÂÃ¥ÂÂ¡Ã¦ÂÂÃ¦Â ÂÃ¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)

                # Ã¦ÂÂ¶Ã©ÂÂÃ¨ÂµÂÃ¦ÂºÂÃ¥ÂÂ Ã§ÂÂ¨Ã¦ÂÂÃ¦Â Â
                memory_mb = 0.0
                thread_count = 0

                try:
                    # Ã¨ÂÂ·Ã¥ÂÂÃ¥Â½ÂÃ¥ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ§ÂÂÃ¥ÂÂÃ¥Â­ÂÃ¥ÂÂ Ã§ÂÂ¨
                    memory_info = self._main_process.memory_info()
                    memory_mb = memory_info.rss / (1024 * 1024)

                    # Ã¨ÂÂ·Ã¥ÂÂÃ§ÂºÂ¿Ã§Â¨ÂÃ¦ÂÂ°
                    thread_count = threading.active_count()
                except Exception as e:
                    self.logger.debug("Ã¨ÂÂ·Ã¥ÂÂÃ¨ÂµÂÃ¦ÂºÂÃ¥ÂÂ Ã§ÂÂ¨Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)

                return {
                    "service_name": service_name,
                    "status": "online",
                    "online": True,
                    "initialized": is_initialized,
                    "response_time_ms": round(response_time_ms, 2),
                    "health_details": health_result,
                    "message": "Ã¦ÂÂÃ¥ÂÂ¡Ã¦Â­Â£Ã¥Â¸Â¸",
                    # Ã¤Â¸ÂÃ¥ÂÂ¡Ã¦ÂÂÃ¦Â Â
                    "call_count": call_count,
                    "success_rate": round(success_rate, 2),
                    "error_rate": round(error_rate, 2),
                    # Ã¨ÂµÂÃ¦ÂºÂÃ¥ÂÂ Ã§ÂÂ¨
                    "memory_mb": round(memory_mb, 2),
                    "thread_count": thread_count,
                }
            except Exception as e:
                response_time_ms = (time.time() - start_time) * 1000
                return {
                    "service_name": service_name,
                    "status": "error",
                    "online": False,
                    "response_time_ms": round(response_time_ms, 2),
                    "message": f"Ã¥ÂÂ¥Ã¥ÂºÂ·Ã¦Â£ÂÃ¦ÂÂ¥Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
                    "call_count": 0,
                    "success_rate": 0.0,
                    "error_rate": 100.0,
                    "memory_mb": 0.0,
                    "thread_count": 0,
                }

        except Exception as e:
            self.logger.error("Ã¥Â¿Â«Ã©ÂÂÃ¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
            return {
                "service_name": service_name,
                "status": "error",
                "online": False,
                "response_time_ms": 0,
                "message": f"Ã¦Â£ÂÃ¦ÂÂ¥Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
                "call_count": 0,
                "success_rate": 0.0,
                "error_rate": 100.0,
                "memory_mb": 0.0,
                "thread_count": 0,
            }

    def check_response_time(self, service_name: str, service_manager) -> float:
        """Ã¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂÃ¥ÂºÂÃ¦ÂÂ¶Ã©ÂÂ´.

        Args:
            service_name: Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂÃ§Â§Â°
            service_manager: Ã¦ÂÂÃ¥ÂÂ¡Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨Ã¥Â®ÂÃ¤Â¾Â

        Returns:
            float: Ã¥ÂÂÃ¥ÂºÂÃ¦ÂÂ¶Ã©ÂÂ´Ã¯Â¼ÂÃ¦Â¯Â«Ã§Â§ÂÃ¯Â¼Â
        """
        try:
            service = service_manager.get_service(service_name)
            if not service:
                return -1.0

            start_time = time.time()

            # Ã¨Â°ÂÃ§ÂÂ¨Ã¤Â¸ÂÃ¤Â¸ÂªÃ¨Â½Â»Ã©ÂÂÃ§ÂºÂ§Ã¦ÂÂ¹Ã¦Â³Â
            if hasattr(service, "health_check"):
                service.health_check()

            response_time_ms = (time.time() - start_time) * 1000
            return round(response_time_ms, 2)

        except Exception as e:
            self.logger.error("Ã¦Â£ÂÃ¦ÂÂ¥Ã¥ÂÂÃ¥ÂºÂÃ¦ÂÂ¶Ã©ÂÂ´Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
            return -1.0

    def check_external_dependencies(self) -> Dict[str, Any]:
        """Ã¦Â£ÂÃ¦ÂÂ¥Ã¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂÃ§ÂÂ¶Ã¦ÂÂ.

        Returns:
            Dict: Ã¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂÃ¦Â£ÂÃ¦ÂÂ¥Ã§Â»ÂÃ¦ÂÂ
        """
        dependencies = {}

        # 1. Ã¦Â£ÂÃ¦ÂÂ¥EventEngine
        try:
            from backend.core.base import get_event_engine

            event_engine = get_event_engine()
            if event_engine:
                dependencies["event_engine"] = {
                    "name": "VnPy EventEngine",
                    "status": "online",
                    "online": True,
                    "message": "Ã¤ÂºÂÃ¤Â»Â¶Ã¥Â¼ÂÃ¦ÂÂÃ¨Â¿ÂÃ¨Â¡ÂÃ¦Â­Â£Ã¥Â¸Â¸",
                }
            else:
                dependencies["event_engine"] = {
                    "name": "VnPy EventEngine",
                    "status": "offline",
                    "online": False,
                    "message": "Ã¤ÂºÂÃ¤Â»Â¶Ã¥Â¼ÂÃ¦ÂÂÃ¦ÂÂªÃ¥ÂÂÃ¥Â§ÂÃ¥ÂÂ",
                }
        except Exception as e:
            dependencies["event_engine"] = {
                "name": "VnPy EventEngine",
                "status": "error",
                "online": False,
                "message": f"Ã¦Â£ÂÃ¦ÂÂ¥Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
            }

        # 2. Ã¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂÃ¨Â¿ÂÃ¦ÂÂ¥
        try:
            import sqlite3

            from backend.infrastructure.data_module_vnpy.config import config_manager

            db_file = config_manager.get_db_file()
            if db_file.exists():
                # Ã¥Â°ÂÃ¨Â¯ÂÃ¨Â¿ÂÃ¦ÂÂ¥Ã¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂ
                conn = sqlite3.connect(str(db_file), timeout=1)
                conn.close()
                dependencies["database"] = {
                    "name": "SQLiteÃ¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂ",
                    "status": "online",
                    "online": True,
                    "message": "Ã¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂÃ¨Â¿ÂÃ¦ÂÂ¥Ã¦Â­Â£Ã¥Â¸Â¸",
                }
            else:
                dependencies["database"] = {
                    "name": "SQLiteÃ¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂ",
                    "status": "offline",
                    "online": False,
                    "message": "Ã¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂÃ¦ÂÂÃ¤Â»Â¶Ã¤Â¸ÂÃ¥Â­ÂÃ¥ÂÂ¨",
                }
        except Exception as e:
            dependencies["database"] = {
                "name": "SQLiteÃ¦ÂÂ°Ã¦ÂÂ®Ã¥ÂºÂ",
                "status": "error",
                "online": False,
                "message": f"Ã¨Â¿ÂÃ¦ÂÂ¥Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
            }

        return dependencies

    def check_all_services(self, service_manager) -> Dict[str, Any]:
        """Ã¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂÃ¦ÂÂÃ¦Â³Â¨Ã¥ÂÂÃ§ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¯Â¼ÂÃ¥Â¢ÂÃ¥Â¼ÂºÃ§ÂÂ - Ã¥ÂÂÃ¥ÂÂ«Ã¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂÃ¯Â¼Â.

        Args:
            service_manager: Ã¦ÂÂÃ¥ÂÂ¡Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨Ã¥Â®ÂÃ¤Â¾Â

        Returns:
            Dict: Ã¦ÂÂÃ¦ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã§ÂÂÃ¦Â£ÂÃ¦ÂÂ¥Ã§Â»ÂÃ¦ÂÂÃ¯Â¼ÂÃ¥ÂÂÃ¥ÂÂ«Ã¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂÃ§ÂÂ¶Ã¦ÂÂ
        """
        try:
            service_status = service_manager.get_service_status()
            results = []

            online_count = 0
            total_response_time = 0

            for service_name, _status in service_status.items():
                check_result = self.quick_check(service_name, service_manager)
                results.append(check_result)

                if check_result["online"]:
                    online_count += 1
                    total_response_time += check_result["response_time_ms"]

            total_count = len(results)
            health_score = (online_count / total_count * 100) if total_count > 0 else 0
            avg_response_time = (total_response_time / online_count) if online_count > 0 else 0

            # Ã¦Â£ÂÃ¦ÂÂ¥Ã¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂ
            external_dependencies = self.check_external_dependencies()

            # Ã¨Â®Â¡Ã§Â®ÂÃ¥Â¤ÂÃ©ÂÂ¨Ã¤Â¾ÂÃ¨ÂµÂÃ¥ÂÂ¥Ã¥ÂºÂ·Ã¥ÂºÂ¦
            dep_online = sum(
                1 for dep in external_dependencies.values() if dep.get("online") is True
            )
            dep_total = len(external_dependencies)
            dep_health_score = (dep_online / dep_total * 100) if dep_total > 0 else 0

            # Ã§Â»Â¼Ã¥ÂÂÃ¥ÂÂ¥Ã¥ÂºÂ·Ã¨Â¯ÂÃ¥ÂÂÃ¯Â¼ÂÃ¦ÂÂÃ¥ÂÂ¡Ã¦ÂÂÃ©ÂÂ70%Ã¯Â¼ÂÃ¤Â¾ÂÃ¨ÂµÂÃ¦ÂÂÃ©ÂÂ30%Ã¯Â¼Â
            overall_health_score = health_score * 0.7 + dep_health_score * 0.3

            return {
                "success": True,
                "total_services": total_count,
                "online_services": online_count,
                "health_score": round(overall_health_score, 1),
                "service_health_score": round(health_score, 1),
                "dependency_health_score": round(dep_health_score, 1),
                "avg_response_time_ms": round(avg_response_time, 2),
                "services": results,
                "external_dependencies": external_dependencies,
            }

        except Exception as e:
            self.logger.error("Ã¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂÃ¦ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥: %s", e)
            return {
                "success": False,
                "message": f"Ã¦Â£ÂÃ¦ÂÂ¥Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
                "services": [],
                "external_dependencies": {},
            }


class ServiceRestarter:
    """Ã¦ÂÂÃ¥ÂÂ¡Ã©ÂÂÃ¥ÂÂ¯Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨."""

    def __init__(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã©ÂÂÃ¥ÂÂ¯Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨."""
        self.logger = logging.getLogger(__name__)

    def restart_service(self, service_name: str, service_manager) -> Dict[str, Any]:
        """Ã©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥Â®ÂÃ¦ÂÂÃ¥ÂÂ¡.

        Args:
            service_name: Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂÃ§Â§Â°
            service_manager: Ã¦ÂÂÃ¥ÂÂ¡Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨Ã¥Â®ÂÃ¤Â¾Â

        Returns:
            Dict: Ã©ÂÂÃ¥ÂÂ¯Ã§Â»ÂÃ¦ÂÂ
        """
        try:
            self.logger.info("Ã¥Â¼ÂÃ¥Â§ÂÃ©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ¡: %s", service_name)

            # Ã¨ÂÂ·Ã¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥Â®ÂÃ¤Â¾Â
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "success": False,
                    "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¦ÂÂªÃ¦Â³Â¨Ã¥ÂÂ",
                }

            # Ã¥ÂÂ³Ã©ÂÂ­Ã¦ÂÂÃ¥ÂÂ¡
            if hasattr(service, "shutdown"):
                try:
                    service.shutdown()
                    self.logger.info("Ã¦ÂÂÃ¥ÂÂ¡ %s Ã¥Â·Â²Ã¥ÂÂ³Ã©ÂÂ­", service_name)
                except Exception as e:
                    self.logger.warning("Ã¥ÂÂ³Ã©ÂÂ­Ã¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)

            # Ã§Â­ÂÃ¥Â¾ÂÃ¤Â¸ÂÃ¥Â°ÂÃ¦Â®ÂµÃ¦ÂÂ¶Ã©ÂÂ´
            time.sleep(0.5)

            # Ã©ÂÂÃ¦ÂÂ°Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡
            if hasattr(service, "initialize"):
                try:
                    success = service.initialize()
                    if success:
                        self.logger.info("Ã¦ÂÂÃ¥ÂÂ¡ %s Ã¥Â·Â²Ã©ÂÂÃ¦ÂÂ°Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂ", service_name)
                        return {
                            "success": True,
                            "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ",
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â¤Â±Ã¨Â´Â¥",
                        }
                except Exception as e:
                    self.logger.error("Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
                    return {
                        "success": False,
                        "message": f"Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
                    }
            else:
                return {
                    "success": False,
                    "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¤Â¸ÂÃ¦ÂÂ¯Ã¦ÂÂÃ©ÂÂÃ¥ÂÂ¯",
                }

        except Exception as e:
            self.logger.error("Ã©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
            return {
                "success": False,
                "message": f"Ã©ÂÂÃ¥ÂÂ¯Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
            }

    def graceful_restart(
        self, service_name: str, service_manager, timeout: int = 30
    ) -> Dict[str, Any]:
        """Ã¤Â¼ÂÃ©ÂÂÃ¥ÂÂ°Ã©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ¡Ã¯Â¼ÂÃ¥Â¸Â¦Ã¨Â¶ÂÃ¦ÂÂ¶Ã¦ÂÂ§Ã¥ÂÂ¶Ã¯Â¼Â.

        Args:
            service_name: Ã¦ÂÂÃ¥ÂÂ¡Ã¥ÂÂÃ§Â§Â°
            service_manager: Ã¦ÂÂÃ¥ÂÂ¡Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨Ã¥Â®ÂÃ¤Â¾Â
            timeout: Ã¨Â¶ÂÃ¦ÂÂ¶Ã¦ÂÂ¶Ã©ÂÂ´Ã¯Â¼ÂÃ§Â§ÂÃ¯Â¼Â

        Returns:
            Dict: Ã©ÂÂÃ¥ÂÂ¯Ã§Â»ÂÃ¦ÂÂ
        """
        try:
            self.logger.info("Ã¥Â¼ÂÃ¥Â§ÂÃ¤Â¼ÂÃ©ÂÂÃ©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ¡: %s (timeout=%ds)", service_name, timeout)

            start_time = time.time()

            # Ã¨ÂÂ·Ã¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥Â®ÂÃ¤Â¾Â
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "success": False,
                    "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¦ÂÂªÃ¦Â³Â¨Ã¥ÂÂ",
                }

            # Ã¤Â¼ÂÃ©ÂÂÃ¥ÂÂ³Ã©ÂÂ­
            if hasattr(service, "shutdown"):
                try:
                    service.shutdown()
                    self.logger.info("Ã¦ÂÂÃ¥ÂÂ¡ %s Ã¥Â·Â²Ã¤Â¼ÂÃ©ÂÂÃ¥ÂÂ³Ã©ÂÂ­", service_name)
                except Exception as e:
                    self.logger.warning("Ã¥ÂÂ³Ã©ÂÂ­Ã¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
                    # Ã§Â»Â§Ã§Â»Â­Ã¦ÂÂ§Ã¨Â¡ÂÃ¯Â¼ÂÃ¥Â°ÂÃ¨Â¯ÂÃ©ÂÂÃ¦ÂÂ°Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂ

            # Ã¦Â£ÂÃ¦ÂÂ¥Ã¦ÂÂ¯Ã¥ÂÂ¦Ã¨Â¶ÂÃ¦ÂÂ¶
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return {
                    "success": False,
                    "message": f"Ã¥ÂÂ³Ã©ÂÂ­Ã¦ÂÂÃ¥ÂÂ¡Ã¨Â¶ÂÃ¦ÂÂ¶ ({elapsed:.1f}s)",
                }

            # Ã§Â­ÂÃ¥Â¾ÂÃ¨ÂµÂÃ¦ÂºÂÃ©ÂÂÃ¦ÂÂ¾
            time.sleep(1)

            # Ã©ÂÂÃ¦ÂÂ°Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂ
            if hasattr(service, "initialize"):
                try:
                    success = service.initialize()

                    elapsed = time.time() - start_time

                    if success:
                        self.logger.info(
                            "Ã¦ÂÂÃ¥ÂÂ¡ %s Ã¤Â¼ÂÃ©ÂÂÃ©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ (Ã¨ÂÂÃ¦ÂÂ¶: %.1fs)",
                            service_name,
                            elapsed,
                        )
                        return {
                            "success": True,
                            "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¤Â¼ÂÃ©ÂÂÃ©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ",
                            "elapsed_time": round(elapsed, 1),
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â¤Â±Ã¨Â´Â¥",
                            "elapsed_time": round(elapsed, 1),
                        }

                except Exception as e:
                    elapsed = time.time() - start_time
                    self.logger.error("Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
                    return {
                        "success": False,
                        "message": f"Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
                        "elapsed_time": round(elapsed, 1),
                    }
            else:
                return {
                    "success": False,
                    "message": f"Ã¦ÂÂÃ¥ÂÂ¡ {service_name} Ã¤Â¸ÂÃ¦ÂÂ¯Ã¦ÂÂÃ©ÂÂÃ¥ÂÂ¯",
                }

        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error("Ã¤Â¼ÂÃ©ÂÂÃ©ÂÂÃ¥ÂÂ¯Ã¦ÂÂÃ¥ÂÂ¡Ã¥Â¤Â±Ã¨Â´Â¥ %s: %s", service_name, e)
            return {
                "success": False,
                "message": f"Ã©ÂÂÃ¥ÂÂ¯Ã¥Â¤Â±Ã¨Â´Â¥: {str(e)}",
                "elapsed_time": round(elapsed, 1),
            }


# =============================================================================
# Ã¨Â¿ÂÃ§Â¨ÂÃ§Â®Â¡Ã§ÂÂ
# =============================================================================


class ProcessManager:
    """Ã¨Â¿ÂÃ§Â¨ÂÃ§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨ - Ã¦ÂÂÃ¤Â¾ÂÃ¨Â¿ÂÃ§Â¨ÂÃ§ÂÂÃ¥ÂÂ½Ã¥ÂÂ¨Ã¦ÂÂÃ§Â®Â¡Ã§ÂÂÃ¥ÂÂÃ¨ÂÂ½."""

    def __init__(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨."""
        self.logger = logging.getLogger(__name__)

    def get_process_info(self, pid: int) -> Dict[str, Any]:
        """Ã¨ÂÂ·Ã¥ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ¤Â¿Â¡Ã¦ÂÂ¯.

        Args:
            pid: Ã¨Â¿ÂÃ§Â¨ÂID

        Returns:
            Dict: Ã¨Â¿ÂÃ§Â¨ÂÃ¤Â¿Â¡Ã¦ÂÂ¯
        """
        try:
            import psutil

            process = psutil.Process(pid)
            return {
                "pid": pid,
                "name": process.name(),
                "status": process.status(),
                "cpu_percent": process.cpu_percent(),
                "memory_percent": process.memory_percent(),
                "create_time": process.create_time(),
            }
        except Exception as e:
            self.logger.error("Ã¨ÂÂ·Ã¥ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ¤Â¿Â¡Ã¦ÂÂ¯Ã¥Â¤Â±Ã¨Â´Â¥ (pid=%d): %s", pid, e)
            return {"pid": pid, "status": "unknown", "error": str(e)}

    def manage_process_lifecycle(self, action: str, params: Dict[str, Any]) -> bool:
        """Ã§Â®Â¡Ã§ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ§ÂÂÃ¥ÂÂ½Ã¥ÂÂ¨Ã¦ÂÂ.

        Args:
            action: Ã¦ÂÂÃ¤Â½ÂÃ§Â±Â»Ã¥ÂÂ (start, stop, restart, status)
            params: Ã¨Â¿ÂÃ§Â¨ÂÃ©ÂÂÃ§Â½Â®Ã¥ÂÂÃ¦ÂÂ°

        Returns:
            bool: Ã¦ÂÂÃ¤Â½ÂÃ¦ÂÂ¯Ã¥ÂÂ¦Ã¦ÂÂÃ¥ÂÂ

        Note:
            Ã¨Â¿ÂÃ¦ÂÂ¯Ã¤Â¸ÂÃ¤Â¸ÂªÃ¦Â¡ÂÃ¦ÂÂ¶Ã¦ÂÂ¹Ã¦Â³ÂÃ¯Â¼ÂÃ©ÂÂÃ¨Â¦ÂÃ¦Â Â¹Ã¦ÂÂ®Ã¥ÂÂ·Ã¤Â½ÂÃ©ÂÂÃ¦Â±ÂÃ¥Â®ÂÃ§ÂÂ°Ã¥Â®ÂÃ©ÂÂÃ§ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ§Â®Â¡Ã§ÂÂÃ©ÂÂ»Ã¨Â¾Â
        """
        self.logger.info("Ã¨Â¿ÂÃ§Â¨ÂÃ§ÂÂÃ¥ÂÂ½Ã¥ÂÂ¨Ã¦ÂÂÃ§Â®Â¡Ã§ÂÂÃ¦ÂÂÃ¤Â½Â: %s, Ã¥ÂÂÃ¦ÂÂ°: %s", action, params)
        raise NotImplementedError("Ã¨Â¿ÂÃ§Â¨ÂÃ§ÂÂÃ¥ÂÂ½Ã¥ÂÂ¨Ã¦ÂÂÃ§Â®Â¡Ã§ÂÂÃ©ÂÂÃ¨Â¦ÂÃ¥Â®ÂÃ§ÂÂ°Ã¥Â®ÂÃ©ÂÂÃ§ÂÂÃ¨Â¿ÂÃ§Â¨ÂÃ¦ÂÂ§Ã¥ÂÂ¶Ã©ÂÂ»Ã¨Â¾Â")


# =============================================================================
# Ã¥Â®ÂÃ¥ÂÂ¨Ã§Â®Â¡Ã§ÂÂ
# =============================================================================


class SecurityManager:
    """Ã¥Â®ÂÃ¥ÂÂ¨Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨ - Ã¨Â´ÂÃ¨Â´Â£Ã§Â³Â»Ã§Â»ÂÃ§ÂÂÃ¦ÂÂ´Ã¤Â½ÂÃ¥Â®ÂÃ¥ÂÂ¨Ã§Â®Â¡Ã§ÂÂ,Ã¥ÂÂÃ¦ÂÂ¬Ã¦ÂÂÃ©ÂÂÃ©ÂªÂÃ¨Â¯Â,Ã¥Â®ÂÃ¥ÂÂ¨Ã§Â­ÂÃ§ÂÂ¥Ã¦ÂÂ§Ã¨Â¡ÂÃ§Â­Â."""

    def __init__(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â®ÂÃ¥ÂÂ¨Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨"""
        self.is_initialized = False
        self.security_policies = {}
        self.encryption_manager = EncryptionManager()
        self.audit_logger = AuditLogger()
        self.permission_controller = PermissionController()

    def initialize(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â®ÂÃ¥ÂÂ¨Ã§Â³Â»Ã§Â»Â"""
        try:
            # Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥ÂÂ Ã¥Â¯ÂÃ§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨
            self.encryption_manager.initialize()

            # Ã¨Â®Â¾Ã§Â½Â®Ã©Â»ÂÃ¨Â®Â¤Ã¥Â®ÂÃ¥ÂÂ¨Ã§Â­ÂÃ§ÂÂ¥
            self.security_policies = {
                "password_min_length": 8,
                "session_timeout": 3600,  # 1Ã¥Â°ÂÃ¦ÂÂ¶
                "max_login_attempts": 5,
                "encryption_algorithm": "AES-256",
                "audit_log_retention_days": 90,
            }

            # Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â®Â¡Ã¨Â®Â¡Ã¦ÂÂ¥Ã¥Â¿Â
            self.audit_logger.initialize()

            # Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ©ÂÂÃ¦ÂÂ§Ã¥ÂÂ¶Ã¥ÂÂ¨
            self.permission_controller.initialize()

            self.is_initialized = True
            logger.info("SecurityManager initialized successfully")
            self.audit_logger.log_system_event(
                "security_init", "Security system initialized", "success"
            )

        except Exception as e:
            logger.error("Failed to initialize SecurityManager: %s", e)
            self.audit_logger.log_system_event(
                "security_init", f"Security system initialization failed: {e}", "error"
            )
            raise

    def validate_permissions(self, user_id: str, resource: str) -> bool:
        """Ã©ÂªÂÃ¨Â¯ÂÃ§ÂÂ¨Ã¦ÂÂ·Ã¦ÂÂÃ©ÂÂ

        Args:
            user_id: Ã§ÂÂ¨Ã¦ÂÂ·ID
            resource: Ã¨ÂµÂÃ¦ÂºÂÃ¦Â ÂÃ¨Â¯Â

        Returns:
            bool: Ã¦ÂÂ¯Ã¥ÂÂ¦Ã¦ÂÂÃ¦ÂÂÃ©ÂÂÃ¨Â®Â¿Ã©ÂÂ®
        """
        if not self.is_initialized:
            logger.warning("SecurityManager not initialized")
            return False

        try:
            # Ã¦Â£ÂÃ¦ÂÂ¥Ã§ÂÂ¨Ã¦ÂÂ·Ã¦ÂÂ¯Ã¥ÂÂ¦Ã¥Â­ÂÃ¥ÂÂ¨
            if not self.permission_controller.user_exists(user_id):
                logger.warning("User %s does not exist", user_id)
                self.audit_logger.log_user_action(
                    user_id, "access_denied", resource, "user_not_found"
                )
                return False

            # Ã©ÂªÂÃ¨Â¯ÂÃ¦ÂÂÃ©ÂÂ
            has_permission = self.permission_controller.has_permission(user_id, resource)

            # Ã¨Â®Â°Ã¥Â½ÂÃ¨Â®Â¿Ã©ÂÂ®Ã¥Â°ÂÃ¨Â¯Â
            result = "granted" if has_permission else "denied"
            self.audit_logger.log_user_action(user_id, "access_attempt", resource, result)

            return has_permission

        except (ValueError, RuntimeError, KeyError) as e:
            logger.error(
                "Permission validation error for user %s, resource %s: %s",
                user_id,
                resource,
                e,
            )
            self.audit_logger.log_user_action(user_id, "access_error", resource, f"error: {e}")
            return False


class PermissionController:
    """Ã¦ÂÂÃ©ÂÂÃ¦ÂÂ§Ã¥ÂÂ¶Ã¥ÂÂ¨ - Ã¨Â´ÂÃ¨Â´Â£Ã§ÂÂ¨Ã¦ÂÂ·Ã¦ÂÂÃ©ÂÂÃ§ÂÂÃ¥ÂÂÃ©ÂÂ,Ã©ÂªÂÃ¨Â¯ÂÃ¥ÂÂÃ§Â®Â¡Ã§ÂÂ."""

    def __init__(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ©ÂÂÃ¦ÂÂ§Ã¥ÂÂ¶Ã¥ÂÂ¨"""
        self.permissions = {}
        self.user_roles = {}
        self.role_permissions = {}
        self.is_initialized = False

    def initialize(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¦ÂÂÃ©ÂÂÃ¦ÂÂ§Ã¥ÂÂ¶Ã¥ÂÂ¨"""
        # Ã¨Â®Â¾Ã§Â½Â®Ã©Â»ÂÃ¨Â®Â¤Ã¨Â§ÂÃ¨ÂÂ²Ã¥ÂÂÃ¦ÂÂÃ©ÂÂ
        self.role_permissions = {
            "admin": {"read", "write", "delete", "manage_users", "system_config"},
            "trader": {"read", "write", "trading"},
            "viewer": {"read"},
            "analyst": {"read", "analysis"},
        }

        # Ã¥ÂÂÃ¥Â»ÂºÃ©Â»ÂÃ¨Â®Â¤Ã§Â®Â¡Ã§ÂÂÃ¥ÂÂÃ§ÂÂ¨Ã¦ÂÂ·
        self.user_roles["admin"] = "admin"
        self.permissions["admin"] = self.role_permissions["admin"].copy()

        self.is_initialized = True
        logger.info("PermissionController initialized")

    def user_exists(self, user_id: str) -> bool:
        """Ã¦Â£ÂÃ¦ÂÂ¥Ã§ÂÂ¨Ã¦ÂÂ·Ã¦ÂÂ¯Ã¥ÂÂ¦Ã¥Â­ÂÃ¥ÂÂ¨"""
        return user_id in self.user_roles

    def has_permission(self, user_id: str, resource: str) -> bool:
        """Ã¦Â£ÂÃ¦ÂÂ¥Ã§ÂÂ¨Ã¦ÂÂ·Ã¦ÂÂ¯Ã¥ÂÂ¦Ã¦ÂÂÃ§ÂÂ¹Ã¥Â®ÂÃ¦ÂÂÃ©ÂÂ"""
        if user_id not in self.permissions:
            return False

        # Ã¦Â£ÂÃ¦ÂÂ¥Ã§ÂÂ´Ã¦ÂÂ¥Ã¦ÂÂÃ©ÂÂ
        if resource in self.permissions[user_id]:
            return True

        # Ã¦Â£ÂÃ¦ÂÂ¥Ã¨Â§ÂÃ¨ÂÂ²Ã¦ÂÂÃ©ÂÂ
        if user_id in self.user_roles:
            role = self.user_roles[user_id]
            if role in self.role_permissions:
                return resource in self.role_permissions[role]

        return False

    def grant_permission(self, user_id: str, permission: str):
        """Ã¦ÂÂÃ¤ÂºÂÃ§ÂÂ¨Ã¦ÂÂ·Ã¦ÂÂÃ©ÂÂ

        Args:
            user_id: Ã§ÂÂ¨Ã¦ÂÂ·ID
            permission: Ã¦ÂÂÃ©ÂÂÃ¦Â ÂÃ¨Â¯Â
        """
        if not self.is_initialized:
            logger.warning("PermissionController not initialized")
            return

        if user_id not in self.permissions:
            self.permissions[user_id] = set()

        self.permissions[user_id].add(permission)
        logger.info("Granted permission %s to user %s", permission, user_id)

    def revoke_permission(self, user_id: str, permission: str):
        """Ã¦ÂÂ¤Ã©ÂÂÃ§ÂÂ¨Ã¦ÂÂ·Ã¦ÂÂÃ©ÂÂ

        Args:
            user_id: Ã§ÂÂ¨Ã¦ÂÂ·ID
            permission: Ã¦ÂÂÃ©ÂÂÃ¦Â ÂÃ¨Â¯Â
        """
        if not self.is_initialized:
            logger.warning("PermissionController not initialized")
            return

        if user_id in self.permissions:
            self.permissions[user_id].discard(permission)
            logger.info("Revoked permission %s from user %s", permission, user_id)

    def assign_role(self, user_id: str, role: str):
        """Ã¤Â¸ÂºÃ§ÂÂ¨Ã¦ÂÂ·Ã¥ÂÂÃ©ÂÂÃ¨Â§ÂÃ¨ÂÂ²

        Args:
            user_id: Ã§ÂÂ¨Ã¦ÂÂ·ID
            role: Ã¨Â§ÂÃ¨ÂÂ²Ã¥ÂÂÃ§Â§Â°
        """
        if role not in self.role_permissions:
            logger.error("Unknown role: %s", role)
            return

        self.user_roles[user_id] = role
        self.permissions[user_id] = self.role_permissions[role].copy()
        logger.info("Assigned role %s to user %s", role, user_id)


class EncryptionManager:
    """Ã¥ÂÂ Ã¥Â¯ÂÃ§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨ - Ã¨Â´ÂÃ¨Â´Â£Ã¦ÂÂ°Ã¦ÂÂ®Ã§ÂÂÃ¥ÂÂ Ã¥Â¯Â,Ã¨Â§Â£Ã¥Â¯ÂÃ¥ÂÂÃ¥Â¯ÂÃ©ÂÂ¥Ã§Â®Â¡Ã§ÂÂ."""

    def __init__(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥ÂÂ Ã¥Â¯ÂÃ§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨"""
        self.encryption_key = None
        self.fernet = None
        self.is_initialized = False

    def initialize(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥ÂÂ Ã¥Â¯ÂÃ§Â®Â¡Ã§ÂÂÃ¥ÂÂ¨"""
        try:
            # Ã§ÂÂÃ¦ÂÂÃ¦ÂÂÃ¥ÂÂ Ã¨Â½Â½Ã¥Â¯ÂÃ©ÂÂ¥
            self.generate_key()
            self.is_initialized = True
            logger.info("EncryptionManager initialized")
        except Exception as e:
            logger.error("Failed to initialize EncryptionManager: %s", e)
            raise

    def generate_key(self) -> str:
        """Ã§ÂÂÃ¦ÂÂÃ¥ÂÂ Ã¥Â¯ÂÃ¥Â¯ÂÃ©ÂÂ¥

        Returns:
            str: Ã§ÂÂÃ¦ÂÂÃ§ÂÂÃ¥Â¯ÂÃ©ÂÂ¥
        """
        # Ã¤Â½Â¿Ã§ÂÂ¨PBKDF2Ã§ÂÂÃ¦ÂÂÃ¥Â¯ÂÃ©ÂÂ¥
        password = secrets.token_bytes(32)
        salt = secrets.token_bytes(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        key = base64.urlsafe_b64encode(kdf.derive(password))
        self.encryption_key = key
        self.fernet = Fernet(key)

        logger.info("Generated new encryption key")
        return key.decode()

    def encrypt_data(self, data: str) -> str:
        """Ã¥ÂÂ Ã¥Â¯ÂÃ¦ÂÂ°Ã¦ÂÂ®

        Args:
            data: Ã¨Â¦ÂÃ¥ÂÂ Ã¥Â¯ÂÃ§ÂÂÃ¦ÂÂ°Ã¦ÂÂ®

        Returns:
            str: Ã¥ÂÂ Ã¥Â¯ÂÃ¥ÂÂÃ§ÂÂÃ¦ÂÂ°Ã¦ÂÂ®
        """
        if not self.is_initialized or not self.fernet:
            logger.error("EncryptionManager not properly initialized")
            raise RuntimeError("EncryptionManager not initialized")

        try:
            # Ã¥Â°ÂÃ¥Â­ÂÃ§Â¬Â¦Ã¤Â¸Â²Ã¨Â½Â¬Ã¦ÂÂ¢Ã¤Â¸ÂºÃ¥Â­ÂÃ¨ÂÂ
            data_bytes = data.encode("utf-8")

            # Ã¤Â½Â¿Ã§ÂÂ¨FernetÃ¥ÂÂ Ã¥Â¯Â
            encrypted_bytes = self.fernet.encrypt(data_bytes)

            # Ã¨Â½Â¬Ã¦ÂÂ¢Ã¤Â¸Âºbase64Ã¥Â­ÂÃ§Â¬Â¦Ã¤Â¸Â²
            encrypted_data = base64.urlsafe_b64encode(encrypted_bytes).decode("utf-8")

            logger.info("Data encrypted successfully")
            return encrypted_data

        except Exception as e:
            logger.error("Data encryption failed: %s", e)
            raise

    def decrypt_data(self, encrypted_data: str) -> str:
        """Ã¨Â§Â£Ã¥Â¯ÂÃ¦ÂÂ°Ã¦ÂÂ®

        Args:
            encrypted_data: Ã¥ÂÂ Ã¥Â¯ÂÃ§ÂÂÃ¦ÂÂ°Ã¦ÂÂ®

        Returns:
            str: Ã¨Â§Â£Ã¥Â¯ÂÃ¥ÂÂÃ§ÂÂÃ¦ÂÂ°Ã¦ÂÂ®
        """
        if not self.is_initialized or not self.fernet:
            logger.error("EncryptionManager not properly initialized")
            raise RuntimeError("EncryptionManager not initialized")

        try:
            # Ã¥Â°Âbase64Ã¥Â­ÂÃ§Â¬Â¦Ã¤Â¸Â²Ã¨Â½Â¬Ã¦ÂÂ¢Ã¤Â¸ÂºÃ¥Â­ÂÃ¨ÂÂ
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode("utf-8"))

            # Ã¤Â½Â¿Ã§ÂÂ¨FernetÃ¨Â§Â£Ã¥Â¯Â
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)

            # Ã¨Â½Â¬Ã¦ÂÂ¢Ã¤Â¸ÂºÃ¥Â­ÂÃ§Â¬Â¦Ã¤Â¸Â²
            decrypted_data = decrypted_bytes.decode("utf-8")

            logger.info("Data decrypted successfully")
            return decrypted_data

        except Exception as e:
            logger.error("Data decryption failed: %s", e)
            raise


class AuditLogger:
    """Ã¥Â®Â¡Ã¨Â®Â¡Ã¦ÂÂ¥Ã¥Â¿ÂÃ¥ÂÂ¨ - Ã¨Â´ÂÃ¨Â´Â£Ã¨Â®Â°Ã¥Â½ÂÃ§Â³Â»Ã§Â»ÂÃ§ÂÂÃ¥Â®ÂÃ¥ÂÂ¨Ã¥Â®Â¡Ã¨Â®Â¡Ã¦ÂÂ¥Ã¥Â¿Â,Ã¥ÂÂÃ¦ÂÂ¬Ã§ÂÂ¨Ã¦ÂÂ·Ã¦ÂÂÃ¤Â½Â,Ã¦ÂÂÃ©ÂÂÃ¥ÂÂÃ¦ÂÂ´Ã§Â­Â."""

    def __init__(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â®Â¡Ã¨Â®Â¡Ã¦ÂÂ¥Ã¥Â¿ÂÃ¥ÂÂ¨"""
        self.audit_logs = []
        self.is_initialized = False

    def initialize(self):
        """Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¥Â®Â¡Ã¨Â®Â¡Ã¦ÂÂ¥Ã¥Â¿ÂÃ¥ÂÂ¨"""
        self.is_initialized = True
        logger.info("AuditLogger initialized")

    def log_user_action(self, user_id: str, action: str, resource: str, result: str):
        """Ã¨Â®Â°Ã¥Â½ÂÃ§ÂÂ¨Ã¦ÂÂ·Ã¦ÂÂÃ¤Â½ÂÃ¦ÂÂ¥Ã¥Â¿Â

        Args:
            user_id: Ã§ÂÂ¨Ã¦ÂÂ·ID
            action: Ã¦ÂÂÃ¤Â½ÂÃ§Â±Â»Ã¥ÂÂ
            resource: Ã¦ÂÂÃ¤Â½ÂÃ§ÂÂÃ¨ÂµÂÃ¦ÂºÂ
            result: Ã¦ÂÂÃ¤Â½ÂÃ§Â»ÂÃ¦ÂÂ
        """
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "result": result,
        }
        self.audit_logs.append(log_entry)
        logger.info("Audit log: %s performed %s on %s - %s", user_id, action, resource, result)

    def log_permission_change(
        self, admin_user: str, target_user: str, permission: str, action: str
    ):
        """Ã¨Â®Â°Ã¥Â½ÂÃ¦ÂÂÃ©ÂÂÃ¥ÂÂÃ¦ÂÂ´Ã¦ÂÂ¥Ã¥Â¿Â

        Args:
            admin_user: Ã¦ÂÂ§Ã¨Â¡ÂÃ¦ÂÂÃ©ÂÂÃ¥ÂÂÃ¦ÂÂ´Ã§ÂÂÃ§Â®Â¡Ã§ÂÂÃ¥ÂÂ
            target_user: Ã§ÂÂ®Ã¦Â ÂÃ§ÂÂ¨Ã¦ÂÂ·
            permission: Ã¦ÂÂÃ©ÂÂÃ¦Â ÂÃ¨Â¯Â
            action: Ã¦ÂÂÃ¤Â½ÂÃ§Â±Â»Ã¥ÂÂ(grant/revoke)
        """
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "admin_user": admin_user,
            "target_user": target_user,
            "permission": permission,
            "action": action,
        }
        self.audit_logs.append(log_entry)
        logger.info(
            "Permission audit: %s %sed %s for %s",
            admin_user,
            action,
            permission,
            target_user,
        )

    def log_system_event(self, event_type: str, description: str, result: str):
        """Ã¨Â®Â°Ã¥Â½ÂÃ§Â³Â»Ã§Â»ÂÃ¤ÂºÂÃ¤Â»Â¶Ã¦ÂÂ¥Ã¥Â¿Â

        Args:
            event_type: Ã¤ÂºÂÃ¤Â»Â¶Ã§Â±Â»Ã¥ÂÂ
            description: Ã¤ÂºÂÃ¤Â»Â¶Ã¦ÂÂÃ¨Â¿Â°
            result: Ã¤ÂºÂÃ¤Â»Â¶Ã§Â»ÂÃ¦ÂÂ
        """
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "event_type": event_type,
            "description": description,
            "result": result,
            "source": "system",
        }
        self.audit_logs.append(log_entry)
        logger.info("System event: %s - %s (%s)", event_type, description, result)

    def get_audit_logs(self, user_id: str | None = None) -> list:
        """Ã¨ÂÂ·Ã¥ÂÂÃ¥Â®Â¡Ã¨Â®Â¡Ã¦ÂÂ¥Ã¥Â¿Â

        Args:
            user_id: Ã¥ÂÂ¯Ã©ÂÂ,Ã¦ÂÂÃ¥Â®ÂÃ§ÂÂ¨Ã¦ÂÂ·IDÃ¨Â¿ÂÃ¦Â»Â¤Ã¦ÂÂ¥Ã¥Â¿Â

        Returns:
            list: Ã¥Â®Â¡Ã¨Â®Â¡Ã¦ÂÂ¥Ã¥Â¿ÂÃ¥ÂÂÃ¨Â¡Â¨
        """
        if user_id:
            return [
                log
                for log in self.audit_logs
                if (log.get("user_id") == user_id or log.get("target_user") == user_id)
            ]
        return self.audit_logs.copy()


# =============================================================================
# Ã¥Â¯Â¼Ã¥ÂÂº
# =============================================================================

# Part 2: 诊断/文件/网络/性能工具（来自 tools.py）
# =============================================================================


logger = logging.getLogger(__name__)


# =============================================================================
# 诊断工具
# =============================================================================


class LogAnalyzer:
    """日志分析器 - 智能分析错误模式."""

    def __init__(self):
        """初始化日志分析器."""
        self.logger = logging.getLogger(__name__)

        # 常见错误模式
        self.error_patterns = {
            "module_not_found": r"ModuleNotFoundError|ImportError",
            "connection_error": r"ConnectionError|ConnectionTimeout|ConnectionRefusedError",
            "timeout": r"TimeoutError|timeout",
            "permission": r"PermissionError|AccessDenied",
            "file_not_found": r"FileNotFoundError",
            "type_error": r"TypeError",
            "value_error": r"ValueError",
            "key_error": r"KeyError",
            "attribute_error": r"AttributeError",
            "memory_error": r"MemoryError|Out of memory",
        }

    def analyze_error_logs(self, log_file: str, hours: int = 24) -> Dict[str, Any]:
        """分析错误日志.

        Args:
            log_file: 日志文件路径
            hours: 分析最近多少小时的日志

        Returns:
            Dict: 分析结果
        """
        try:
            log_path = Path(log_file)
            if not log_path.exists():
                return {
                    "success": False,
                    "message": f"日志文件不存在: {log_file}",
                }

            # 读取日志
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                logs = f.readlines()

            # 时间过滤
            cutoff_time = datetime.now() - timedelta(hours=hours)
            filtered_logs = self._filter_by_time(logs, cutoff_time)

            # 识别错误模式
            error_patterns = self.identify_error_patterns(filtered_logs)

            # 统计错误频率
            error_counts = Counter([e["type"] for e in error_patterns])

            # 提取TOP错误
            top_errors = error_counts.most_common(10)

            return {
                "success": True,
                "total_errors": len(error_patterns),
                "error_types": len(error_counts),
                "top_errors": [
                    {"type": error_type, "count": count} for error_type, count in top_errors
                ],
                "error_patterns": error_patterns[:50],  # 最多返回50条
                "analysis_time": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("分析日志失败: %s", e)
            return {
                "success": False,
                "message": f"分析失败: {str(e)}",
            }

    def identify_error_patterns(self, logs: List[str]) -> List[Dict[str, Any]]:
        """识别错误模式.

        Args:
            logs: 日志行列表

        Returns:
            List: 错误模式列表
        """
        errors = []

        for i, line in enumerate(logs):
            # 检查是否包含ERROR或CRITICAL
            if "ERROR" not in line and "CRITICAL" not in line:
                continue

            # 匹配错误类型
            error_type = "unknown"
            for pattern_name, pattern in self.error_patterns.items():
                if re.search(pattern, line, re.IGNORECASE):
                    error_type = pattern_name
                    break

            # 提取时间戳
            timestamp = self._extract_timestamp(line)

            # 提取错误消息
            error_msg = line.strip()

            errors.append(
                {
                    "type": error_type,
                    "message": error_msg[:200],  # 限制长度
                    "timestamp": timestamp,
                    "line_number": i + 1,
                }
            )

        return errors

    def _filter_by_time(self, logs: List[str], cutoff_time: datetime) -> List[str]:
        """按时间过滤日志.

        Args:
            logs: 日志行列表
            cutoff_time: 截止时间

        Returns:
            List: 过滤后的日志
        """
        filtered = []
        for line in logs:
            timestamp = self._extract_timestamp(line)
            if timestamp:
                try:
                    log_time = datetime.fromisoformat(timestamp)
                    if log_time >= cutoff_time:
                        filtered.append(line)
                except (ValueError, TypeError):
                    # 无法解析时间，保留该行
                    filtered.append(line)
            else:
                # 没有时间戳，保留该行
                filtered.append(line)

        return filtered

    def _extract_timestamp(self, line: str) -> Optional[str]:
        """提取日志时间戳.

        Args:
            line: 日志行

        Returns:
            Optional[str]: 时间戳字符串
        """
        # 尝试匹配常见时间戳格式
        patterns = [
            r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}",  # 2025-01-01 12:00:00
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",  # 2025-01-01T12:00:00
        ]

        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(0).replace(" ", "T")

        return None


class PerformanceAnalyzer:
    """性能分析器 - 识别瓶颈."""

    def __init__(self):
        """初始化性能分析器."""
        self.logger = logging.getLogger(__name__)

    def analyze_bottlenecks(self) -> List[Dict[str, Any]]:
        """分析性能瓶颈.

        Returns:
            List: 瓶颈列表
        """
        try:
            import psutil

            bottlenecks = []

            # CPU瓶颈检查
            cpu_percent: float = psutil.cpu_percent(interval=1, percpu=False)  # type: ignore[assignment]
            if cpu_percent > 80:
                bottlenecks.append(
                    {
                        "type": "cpu",
                        "severity": "high" if cpu_percent > 90 else "medium",
                        "current_value": cpu_percent,
                        "threshold": 80,
                        "description": f"CPU使用率过高: {cpu_percent:.1f}%",
                        "impact": "系统响应变慢，策略计算延迟增加",
                    }
                )

            # 内存瓶颈检查
            memory = psutil.virtual_memory()
            if memory.percent > 80:
                bottlenecks.append(
                    {
                        "type": "memory",
                        "severity": "high" if memory.percent > 90 else "medium",
                        "current_value": memory.percent,
                        "threshold": 80,
                        "description": f"内存使用率过高: {memory.percent:.1f}%",
                        "impact": "可能导致OOM错误，系统崩溃风险增加",
                    }
                )

            # 磁盘瓶颈检查
            disk = psutil.disk_usage("/")
            if disk.percent > 85:
                bottlenecks.append(
                    {
                        "type": "disk",
                        "severity": "high" if disk.percent > 95 else "medium",
                        "current_value": disk.percent,
                        "threshold": 85,
                        "description": f"磁盘使用率过高: {disk.percent:.1f}%",
                        "impact": "数据写入失败，日志丢失风险",
                    }
                )

            # 磁盘I/O瓶颈检查
            disk_io = psutil.disk_io_counters()
            if disk_io:
                # 检查I/O等待时间（如果可用）
                io_time_ms = getattr(disk_io, "busy_time", 0) / 1000  # 转换为秒
                if io_time_ms > 0:
                    bottlenecks.append(
                        {
                            "type": "disk_io",
                            "severity": "medium",
                            "current_value": io_time_ms,
                            "threshold": 0,
                            "description": "磁盘I/O繁忙",
                            "impact": "数据读写速度下降",
                        }
                    )

            # 网络瓶颈检查（简化版）
            net_io = psutil.net_io_counters()
            if net_io and hasattr(net_io, "errin") and hasattr(net_io, "errout"):
                # 检查错误包
                error_count: int = net_io.errin + net_io.errout  # type: ignore[attr-defined]

                if error_count > 100:
                    bottlenecks.append(
                        {
                            "type": "network",
                            "severity": "medium",
                            "current_value": error_count,
                            "threshold": 100,
                            "description": f"网络错误包数量: {error_count}",
                            "impact": "网络连接不稳定",
                        }
                    )

            return bottlenecks

        except Exception as e:
            self.logger.error("分析性能瓶颈失败: %s", e)
            return []

    def generate_optimization_suggestions(
        self, bottlenecks: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        """生成优化建议.

        Args:
            bottlenecks: 瓶颈列表（可选）

        Returns:
            List: 优化建议列表
        """
        if bottlenecks is None:
            bottlenecks = self.analyze_bottlenecks()

        suggestions = []

        # 根据瓶颈类型生成建议
        bottleneck_types = {b["type"] for b in bottlenecks}

        if "cpu" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 启用策略结果缓存，减少重复计算",
                    "2. 优化策略算法，降低计算复杂度",
                    "3. 考虑使用多进程并行处理",
                    "4. 检查是否有死循环或无限递归",
                ]
            )

        if "memory" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 启用数据分页加载，避免一次性加载大量数据",
                    "2. 及时释放不再使用的对象",
                    "3. 使用生成器代替列表减少内存占用",
                    "4. 检查是否存在内存泄漏",
                ]
            )

        if "disk" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 清理临时文件和日志文件",
                    "2. 启用日志轮转和自动清理",
                    "3. 将大文件迁移到其他磁盘",
                    "4. 考虑扩展磁盘容量",
                ]
            )

        if "disk_io" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 启用SSD固态硬盘提升I/O性能",
                    "2. 使用异步I/O操作",
                    "3. 批量读写减少I/O次数",
                    "4. 启用数据库连接池",
                ]
            )

        if "network" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 检查网络连接质量",
                    "2. 启用数据压缩减少传输量",
                    "3. 增加请求重试次数",
                    "4. 考虑使用CDN加速",
                ]
            )

        # 通用优化建议
        if not suggestions:
            suggestions = [
                "系统运行正常，暂无优化建议",
                "建议定期监控系统性能指标",
                "保持系统和依赖库的更新",
            ]

        return suggestions


class AutoFixer:
    """自动修复建议生成器."""

    def __init__(self):
        """初始化自动修复器."""
        self.logger = logging.getLogger(__name__)

    def suggest_fixes(self, issue_type: str) -> List[Dict[str, Any]]:
        """生成修复建议.

        Args:
            issue_type: 问题类型

        Returns:
            List: 修复建议列表
        """
        fixes = []

        if issue_type == "module_not_found":
            fixes.append(
                {
                    "title": "安装缺失的模块",
                    "command": "pip install <module_name>",
                    "description": "使用pip安装缺失的Python模块",
                    "auto_fixable": False,
                    "risk_level": "low",
                }
            )

        elif issue_type == "connection_error":
            fixes.extend(
                [
                    {
                        "title": "检查网络连接",
                        "command": "ping <target_host>",
                        "description": "检查目标主机是否可达",
                        "auto_fixable": False,
                        "risk_level": "low",
                    },
                    {
                        "title": "增加连接超时时间",
                        "command": None,
                        "description": "在配置中增加timeout参数",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                    {
                        "title": "启用连接重试",
                        "command": None,
                        "description": "启用自动重试机制",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                ]
            )

        elif issue_type == "permission":
            fixes.append(
                {
                    "title": "修改文件权限",
                    "command": "chmod 755 <file_path>",
                    "description": "给予文件适当的读写权限",
                    "auto_fixable": False,
                    "risk_level": "medium",
                }
            )

        elif issue_type == "file_not_found":
            fixes.extend(
                [
                    {
                        "title": "检查文件路径",
                        "command": None,
                        "description": "确认文件路径是否正确",
                        "auto_fixable": False,
                        "risk_level": "low",
                    },
                    {
                        "title": "创建缺失的目录",
                        "command": "mkdir -p <dir_path>",
                        "description": "创建必要的目录结构",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                ]
            )

        elif issue_type == "memory_error":
            fixes.extend(
                [
                    {
                        "title": "增加系统内存",
                        "command": None,
                        "description": "扩展物理内存或虚拟内存",
                        "auto_fixable": False,
                        "risk_level": "low",
                    },
                    {
                        "title": "启用内存优化",
                        "command": None,
                        "description": "启用数据分页和惰性加载",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                    {
                        "title": "清理内存缓存",
                        "command": None,
                        "description": "手动触发垃圾回收",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                ]
            )

        else:
            fixes.append(
                {
                    "title": "查看详细日志",
                    "command": None,
                    "description": "检查日志文件获取更多信息",
                    "auto_fixable": False,
                    "risk_level": "low",
                }
            )

        return fixes


# =============================================================================
# 网络工具
# =============================================================================


class NetworkTester:
    """网络测试器."""

    def __init__(self):
        """初始化网络测试器."""
        self.logger = logging.getLogger(__name__)

    def test_host(self, host: str, port: int = 80) -> bool:
        """测试主机连通性."""
        return test_connectivity(host, port)

    def ping(self, host: str) -> bool:
        """Ping主机（简单版本）."""
        return test_connectivity(host, 80)


class PortScanner:
    """端口扫描器."""

    def __init__(self):
        """初始化端口扫描器."""
        self.logger = logging.getLogger(__name__)

    def scan(self, host: str, ports: List[int]) -> List[Dict[str, Any]]:
        """扫描指定端口."""
        return scan_ports(host, ports)

    def scan_range(self, host: str, start_port: int, end_port: int) -> List[Dict[str, Any]]:
        """扫描端口范围."""
        ports = list(range(start_port, end_port + 1))
        return self.scan(host, ports)


class SSLValidator:
    """SSL验证器."""

    def __init__(self):
        """初始化SSL验证器."""
        self.logger = logging.getLogger(__name__)

    def validate_ssl_cert(self, host: str, port: int = 443) -> Dict[str, Any]:
        """验证SSL证书."""
        try:
            context = ssl.create_default_context()
            with (
                socket.create_connection((host, port)) as sock,
                context.wrap_socket(sock, server_hostname=host) as ssock,
            ):
                cert = ssock.getpeercert()
                return {"valid": True, "cert_info": cert, "host": host, "port": port}
        except (ssl.SSLError, OSError) as e:
            return {"valid": False, "error": str(e), "host": host, "port": port}

    def check_ssl_expiry(self, host: str, port: int = 443) -> Dict[str, Any]:
        """检查SSL证书到期时间."""
        try:
            context = ssl.create_default_context()
            with (
                socket.create_connection((host, port)) as sock,
                context.wrap_socket(sock, server_hostname=host) as ssock,
            ):
                cert = ssock.getpeercert()
                if cert is None:
                    return {
                        "valid": False,
                        "error": "No certificate information available",
                        "host": host,
                        "port": port,
                    }

                expiry_date = cert.get("notAfter")
                if expiry_date and isinstance(expiry_date, str):
                    expiry = datetime.strptime(expiry_date, "%b %d %H:%M:%S %Y %Z")
                    return {
                        "valid": True,
                        "expiry_date": expiry,
                        "days_until_expiry": (expiry - datetime.now()).days,
                        "host": host,
                        "port": port,
                    }
                else:
                    return {
                        "valid": False,
                        "error": "No expiry date found in certificate",
                        "host": host,
                        "port": port,
                    }
        except (ssl.SSLError, OSError, ValueError) as e:
            return {"valid": False, "error": str(e), "host": host, "port": port}


def test_connectivity(host: str, port: int = 80) -> bool:
    """测试连通性."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except OSError:
        return False


def scan_ports(host: str, ports: List[int]) -> List[Dict[str, Any]]:
    """扫描端口."""
    results = []
    for port in ports:
        is_open = test_connectivity(host, port)
        results.append({"port": port, "open": is_open})
    return results


# =============================================================================
# 文件操作工具
# =============================================================================


class FileOperations:
    """文件操作工具集 - 包含文件管理、目录管理和权限管理."""

    def __init__(self):
        """初始化文件操作工具."""
        self.file_manager = FileManager()
        self.directory_manager = DirectoryManager()
        self.permission_manager = FilePermissionManager()


class FileManager:
    """文件管理器."""

    def create_directory(self, path: str, exist_ok: bool = True) -> bool:
        """创建目录."""
        try:
            os.makedirs(path, exist_ok=exist_ok)
            return True
        except OSError as e:
            logger.error("创建目录失败: %s", e)
            return False

    def delete_file(self, path: str) -> bool:
        """删除文件."""
        try:
            if os.path.isfile(path):
                os.remove(path)
                return True
            return False
        except OSError as e:
            logger.error("删除文件失败: %s", e)
            return False

    def copy_file(self, src: str, dst: str) -> bool:
        """复制文件."""
        try:
            shutil.copy2(src, dst)
            return True
        except (OSError, shutil.Error) as e:
            logger.error("复制文件失败: %s", e)
            return False


class DirectoryManager:
    """目录管理器."""

    def __init__(self):
        """初始化目录管理器."""
        self.logger = logging.getLogger(__name__)

    def create_directory(self, path: str, exist_ok: bool = True) -> bool:
        """创建目录."""
        try:
            os.makedirs(path, exist_ok=exist_ok)
            return True
        except OSError as e:
            self.logger.error("创建目录失败: %s", e)
            return False

    def list_directory(self, path: str, pattern: str = "*", recursive: bool = False) -> List[str]:
        """列出目录内容."""
        try:
            if not os.path.exists(path):
                self.logger.warning("目录不存在: %s", path)
                return []

            if not os.path.isdir(path):
                self.logger.warning("路径不是目录: %s", path)
                return []

            if recursive:
                # 递归搜索
                search_pattern = os.path.join(path, "**", pattern)
                return glob.glob(search_pattern, recursive=True)
            else:
                # 非递归搜索
                search_pattern = os.path.join(path, pattern)
                return glob.glob(search_pattern)

        except OSError as e:
            self.logger.error("列出目录内容失败: %s", e)
            return []

    def get_directory_info(self, path: str) -> Optional[Dict[str, Any]]:
        """获取目录信息."""
        try:
            if not os.path.exists(path):
                return None

            stat_info = os.stat(path)
            return {
                "path": path,
                "size": stat_info.st_size,
                "created": stat_info.st_ctime,
                "modified": stat_info.st_mtime,
                "accessed": stat_info.st_atime,
                "permissions": oct(stat_info.st_mode)[-3:],
                "is_directory": os.path.isdir(path),
                "is_file": os.path.isfile(path),
                "is_symlink": os.path.islink(path),
            }
        except OSError as e:
            self.logger.error("获取目录信息失败: %s", e)
            return None

    def delete_directory(self, path: str, recursive: bool = False) -> bool:
        """删除目录."""
        try:
            if not os.path.exists(path):
                self.logger.warning("目录不存在: %s", path)
                return True

            if not os.path.isdir(path):
                self.logger.warning("路径不是目录: %s", path)
                return False

            if recursive:
                shutil.rmtree(path)
            else:
                os.rmdir(path)

            return True
        except (OSError, shutil.Error) as e:
            self.logger.error("删除目录失败: %s", e)
            return False

    def copy_directory(
        self, src: str, dst: str, ignore_patterns: Optional[List[str]] = None
    ) -> bool:
        """复制目录."""
        try:
            if not os.path.exists(src):
                self.logger.error("源目录不存在: %s", src)
                return False

            if not os.path.isdir(src):
                self.logger.error("源路径不是目录: %s", src)
                return False

            # 创建目标目录的父目录
            os.makedirs(os.path.dirname(dst), exist_ok=True)

            if ignore_patterns:

                def ignore_func(_directory, names):  # noqa: U101
                    # directory parameter required by shutil.copytree
                    # but not used in this implementation
                    ignored = []
                    for pattern in ignore_patterns:
                        for name in names:
                            if fnmatch.fnmatch(name, pattern):
                                ignored.append(name)
                    return ignored

                shutil.copytree(src, dst, ignore=ignore_func)
            else:
                shutil.copytree(src, dst)

            return True
        except (OSError, shutil.Error) as e:
            self.logger.error("复制目录失败: %s", e)
            return False

    def move_directory(self, src: str, dst: str) -> bool:
        """移动目录."""
        try:
            if not os.path.exists(src):
                self.logger.error("源目录不存在: %s", src)
                return False

            if not os.path.isdir(src):
                self.logger.error("源路径不是目录: %s", src)
                return False

            shutil.move(src, dst)
            return True
        except (OSError, shutil.Error) as e:
            self.logger.error("移动目录失败: %s", e)
            return False

    def get_directory_size(self, path: str) -> int:
        """获取目录大小(字节)."""
        try:
            if not os.path.exists(path):
                return 0

            total_size = 0
            for dirpath, _, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except OSError:
                        continue

            return total_size
        except OSError as e:
            self.logger.error("获取目录大小失败: %s", e)
            return 0

    def clean_empty_directories(self, path: str) -> int:
        """清理空目录,返回清理的目录数量."""
        try:
            cleaned_count = 0

            for root, dirs, _ in os.walk(path, topdown=False):
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    try:
                        if not os.listdir(dir_path):  # 目录为空
                            os.rmdir(dir_path)
                            cleaned_count += 1
                    except OSError:
                        continue

            return cleaned_count
        except OSError as e:
            self.logger.error("清理空目录失败: %s", e)
            return 0


class FilePermissionManager:
    """文件权限管理器."""

    def __init__(self):
        """初始化文件权限管理器."""
        self.logger = logging.getLogger(__name__)

    def get_permissions(self, path: str) -> Optional[Dict[str, Any]]:
        """获取文件或目录权限信息."""
        try:
            if not os.path.exists(path):
                self.logger.warning("路径不存在: %s", path)
                return None

            stat_info = os.stat(path)
            mode = stat_info.st_mode

            return {
                "path": path,
                "mode": oct(mode),
                "permissions": oct(mode)[-3:],
                "owner_read": bool(mode & stat.S_IRUSR),
                "owner_write": bool(mode & stat.S_IWUSR),
                "owner_execute": bool(mode & stat.S_IXUSR),
                "group_read": bool(mode & stat.S_IRGRP),
                "group_write": bool(mode & stat.S_IWGRP),
                "group_execute": bool(mode & stat.S_IXGRP),
                "other_read": bool(mode & stat.S_IROTH),
                "other_write": bool(mode & stat.S_IWOTH),
                "other_execute": bool(mode & stat.S_IXOTH),
                "is_directory": stat.S_ISDIR(mode),
                "is_file": stat.S_ISREG(mode),
                "is_symlink": stat.S_ISLNK(mode),
            }
        except OSError as e:
            self.logger.error("获取权限信息失败: %s", e)
            return None

    def set_permissions(self, path: str, mode: Union[int, str]) -> bool:
        """设置文件或目录权限."""
        try:
            if not os.path.exists(path):
                self.logger.error("路径不存在: %s", path)
                return False

            if isinstance(mode, str):
                # 如果是字符串格式(如 "755", "644")
                if mode.startswith("0"):
                    mode = int(mode, 8)
                else:
                    mode = int(mode, 8)

            os.chmod(path, mode)
            return True
        except OSError as e:
            self.logger.error("设置权限失败: %s", e)
            return False

    def _get_permission_mask(self, permission: str) -> Optional[int]:
        """获取权限掩码."""
        permission_masks = {
            "read": stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH,
            "write": stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH,
            "execute": stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
            "owner_read": stat.S_IRUSR,
            "owner_write": stat.S_IWUSR,
            "owner_execute": stat.S_IXUSR,
            "group_read": stat.S_IRGRP,
            "group_write": stat.S_IWGRP,
            "group_execute": stat.S_IXGRP,
            "other_read": stat.S_IROTH,
            "other_write": stat.S_IWOTH,
            "other_execute": stat.S_IXOTH,
        }
        return permission_masks.get(permission)

    def add_permission(self, path: str, permission: str) -> bool:
        """添加权限."""
        try:
            if not os.path.exists(path):
                self.logger.error("路径不存在: %s", path)
                return False

            current_mode = os.stat(path).st_mode
            permission_mask = self._get_permission_mask(permission)

            if permission_mask is None:
                self.logger.error("未知的权限类型: %s", permission)
                return False

            new_mode = current_mode | permission_mask
            os.chmod(path, new_mode)
            return True
        except OSError as e:
            self.logger.error("添加权限失败: %s", e)
            return False

    def remove_permission(self, path: str, permission: str) -> bool:
        """移除权限."""
        try:
            if not os.path.exists(path):
                self.logger.error("路径不存在: %s", path)
                return False

            current_mode = os.stat(path).st_mode
            permission_mask = self._get_permission_mask(permission)

            if permission_mask is None:
                self.logger.error("未知的权限类型: %s", permission)
                return False

            new_mode = current_mode & ~permission_mask
            os.chmod(path, new_mode)
            return True
        except OSError as e:
            self.logger.error("移除权限失败: %s", e)
            return False

    def is_readable(self, path: str) -> bool:
        """检查文件或目录是否可读."""
        try:
            return os.access(path, os.R_OK)
        except OSError as e:
            self.logger.error("检查读权限失败: %s", e)
            return False

    def is_writable(self, path: str) -> bool:
        """检查文件或目录是否可写."""
        try:
            return os.access(path, os.W_OK)
        except OSError as e:
            self.logger.error("检查写权限失败: %s", e)
            return False

    def is_executable(self, path: str) -> bool:
        """检查文件或目录是否可执行."""
        try:
            return os.access(path, os.X_OK)
        except OSError as e:
            self.logger.error("检查执行权限失败: %s", e)
            return False

    def set_secure_permissions(self, path: str, is_directory: bool = False) -> bool:
        """设置安全权限(文件644,目录755)."""
        try:
            if is_directory:
                mode = 0o755  # rwxr-xr-x
            else:
                mode = 0o644  # rw-r--r--

            return self.set_permissions(path, mode)
        except OSError as e:
            self.logger.error("设置安全权限失败: %s", e)
            return False

    def batch_set_permissions(self, paths: List[str], mode: Union[int, str]) -> List[bool]:
        """批量设置权限."""
        results = []
        for path in paths:
            results.append(self.set_permissions(path, mode))
        return results


def batch_file_operations(operations: List[Dict[str, Any]]) -> List[bool]:
    """批量文件操作.

    Args:
        operations: 操作列表,每个操作包含以下字段:
            - operation: 操作类型
            - path: 文件或目录路径
            - 其他操作特定参数

    Returns:
        操作结果列表,True表示成功,False表示失败
    """
    file_manager = FileManager()
    dir_manager = DirectoryManager()
    perm_manager = FilePermissionManager()

    results = []

    for operation in operations:
        try:
            op_type = operation.get("operation")
            path = operation.get("path")

            if not op_type or not path:
                results.append(False)
                continue

            # 根据操作类型执行不同操作
            if op_type == "delete_file":
                results.append(file_manager.delete_file(path))
            elif op_type == "copy_file":
                dst = operation.get("destination")
                results.append(file_manager.copy_file(path, dst) if dst else False)
            elif op_type == "create_directory":
                exist_ok = operation.get("exist_ok", True)
                results.append(dir_manager.create_directory(path, exist_ok))
            elif op_type == "delete_directory":
                recursive = operation.get("recursive", False)
                results.append(dir_manager.delete_directory(path, recursive))
            elif op_type == "set_permissions":
                mode = operation.get("mode")
                results.append(perm_manager.set_permissions(path, mode) if mode else False)
            else:
                logger.warning("未知的操作类型: %s", op_type)
                results.append(False)

        except (OSError, shutil.Error) as e:
            logger.error("批量操作执行失败: %s", e)
            results.append(False)

    return results


# =============================================================================
# 性能优化工具
# =============================================================================


class PerformanceOptimizer:
    """性能优化器 - 包含缓存、内存和并发优化."""

    def __init__(self):
        """初始化性能优化器."""
        self.cache_manager = CacheManager()
        self.memory_optimizer = MemoryOptimizer()
        self.concurrency_optimizer = ConcurrencyOptimizer()


class CacheManager:
    """缓存管理器 - 缓存管理功能待实现."""


class MemoryOptimizer:
    """内存优化器 - 内存优化功能待实现."""


class ConcurrencyOptimizer:
    """并发优化器 - 并发优化功能待实现."""


def optimize_performance(params: Dict[str, Any]) -> bool:
    """性能优化 - 需要实际的性能优化实现.

    Args:
        params: 优化参数字典

    Returns:
        bool: 优化是否成功
    """
    _ = params  # 避免未使用参数警告
    raise NotImplementedError("性能优化需要实现实际的缓存,内存和并发优化逻辑")


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    # 诊断工具
    "LogAnalyzer",
    "PerformanceAnalyzer",
    "AutoFixer",
    # 网络工具
    "NetworkTester",
    "PortScanner",
    "SSLValidator",
    "test_connectivity",
    "scan_ports",
    # 文件操作
    "FileOperations",
    "FileManager",
    "DirectoryManager",
    "FilePermissionManager",
    "batch_file_operations",
    # 性能优化
    "PerformanceOptimizer",
    "CacheManager",
    "MemoryOptimizer",
    "ConcurrencyOptimizer",
    "optimize_performance",
]
