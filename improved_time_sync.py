#!/usr/bin/env python3
"""
改进的时间同步解决方案
支持NTP和HTTP时间服务的混合方案
"""

import ntplib
import requests
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)

class ImprovedNetworkTimeSync:
    """
    改进的网络时间同步器
    支持NTP和HTTP时间服务的混合方案
    """
    
    def __init__(self):
        # NTP服务器列表（国内优先）
        self.ntp_servers = [
            "ntp.aliyun.com",
            "ntp.tencent.com", 
            "cn.ntp.org.cn",
            "ntp1.aliyun.com",
            "ntp2.aliyun.com",
            "time.windows.com",
            "pool.ntp.org",
            "time.nist.gov"
        ]
        
        # HTTP时间服务列表（备选方案）
        self.http_time_services = [
            "http://worldtimeapi.org/api/timezone/Asia/Shanghai",
            "https://timeapi.io/api/Time/current/zone?timeZone=Asia/Shanghai",
            "http://worldclockapi.com/api/json/utc/now"
        ]
        
        # 缓存机制
        self._cached_offset: Optional[float] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl: int = 1800  # 30分钟TTL（降低频率）
        
        # 统计信息
        self._ntp_success_count = 0
        self._http_success_count = 0
        self._total_failures = 0
        
        # 线程安全
        self._sync_lock = threading.Lock()
        
        # NTP客户端
        try:
            self.ntp_client = ntplib.NTPClient()
            self.ntp_available = True
        except:
            self.ntp_client = None
            self.ntp_available = False
    
    def sync_time_ntp(self, timeout: float = 5.0) -> Tuple[bool, Optional[float]]:
        """使用NTP同步时间"""
        if not self.ntp_available:
            return False, None
            
        for server in self.ntp_servers:
            try:
                response = self.ntp_client.request(server, version=3, timeout=timeout)
                offset = response.offset
                
                logger.info(f"✓ NTP同步成功: {server}, 偏移 {offset:.3f}秒")
                self._ntp_success_count += 1
                return True, offset
                
            except Exception as e:
                logger.debug(f"NTP服务器 {server} 失败: {e}")
                continue
                
        return False, None
    
    def sync_time_http(self, timeout: float = 10.0) -> Tuple[bool, Optional[float]]:
        """使用HTTP时间服务同步时间"""
        for service_url in self.http_time_services:
            try:
                response = requests.get(service_url, timeout=timeout)
                response.raise_for_status()
                
                data = response.json()
                
                # 解析不同API的时间格式
                if "worldtimeapi.org" in service_url:
                    time_str = data.get("datetime", "")
                    # 格式: 2023-11-02T21:30:00.123456+08:00
                    if time_str:
                        # 移除时区信息进行简单解析
                        time_str = time_str.split('+')[0].split('-')[0:3]
                        time_str = '-'.join(time_str[0:3]) + 'T' + time_str[2].split('T')[1]
                        network_time = datetime.fromisoformat(time_str.split('.')[0])
                        
                elif "timeapi.io" in service_url:
                    time_str = data.get("dateTime", "")
                    if time_str:
                        network_time = datetime.fromisoformat(time_str.split('.')[0])
                        
                elif "worldclockapi.com" in service_url:
                    time_str = data.get("currentDateTime", "")
                    if time_str:
                        network_time = datetime.fromisoformat(time_str.split('.')[0])
                else:
                    continue
                
                # 计算偏移量
                system_time = datetime.now()
                offset = (network_time - system_time).total_seconds()
                
                logger.info(f"✓ HTTP时间同步成功: {service_url}, 偏移 {offset:.3f}秒")
                self._http_success_count += 1
                return True, offset
                
            except Exception as e:
                logger.debug(f"HTTP时间服务 {service_url} 失败: {e}")
                continue
                
        return False, None
    
    def sync_time(self) -> Tuple[bool, Optional[float]]:
        """
        混合时间同步策略
        1. 优先尝试NTP（更准确）
        2. NTP失败则尝试HTTP时间服务
        3. 都失败则返回失败
        """
        with self._sync_lock:
            # 尝试NTP同步
            success, offset = self.sync_time_ntp()
            if success:
                return True, offset
            
            # NTP失败，尝试HTTP同步
            logger.warning("⚠️ NTP同步失败，尝试HTTP时间服务...")
            success, offset = self.sync_time_http()
            if success:
                return True, offset
            
            # 都失败
            self._total_failures += 1
            logger.error("❌ 所有时间同步方法都失败")
            return False, None
    
    def get_real_datetime(self) -> datetime:
        """
        获取真实的当前时间
        
        策略：
        1. 检查缓存是否有效（30分钟TTL）
        2. 缓存失效则重新同步
        3. 同步失败则降级使用系统时间
        """
        # 检查缓存
        if self._cached_offset is not None and self._cache_timestamp is not None:
            cache_age = (datetime.now() - self._cache_timestamp).total_seconds()
            
            if cache_age < self._cache_ttl:
                # 使用缓存的偏移量
                real_time = datetime.now() + timedelta(seconds=self._cached_offset)
                logger.debug(f"使用缓存的时间偏移: {self._cached_offset:.3f}秒")
                return real_time
        
        # 缓存失效，重新同步
        logger.info("时间偏移缓存失效，重新同步...")
        success, offset = self.sync_time()
        
        if success and offset is not None:
            # 更新缓存
            self._cached_offset = offset
            self._cache_timestamp = datetime.now()
            
            # 返回修正后的时间
            return datetime.now() + timedelta(seconds=offset)
        else:
            # 同步失败，降级使用系统时间
            logger.warning("⚠️ 网络时间同步失败，将使用系统时间")
            logger.warning("⚠️ 如果系统时间不准确，可能导致数据新鲜度误判")
            return datetime.now()
    
    def get_real_date(self) -> str:
        """获取真实的当前日期"""
        return self.get_real_datetime().date()
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "ntp_success_count": self._ntp_success_count,
            "http_success_count": self._http_success_count,
            "total_failures": self._total_failures,
            "cached_offset": self._cached_offset,
            "cache_age_seconds": (
                (datetime.now() - self._cache_timestamp).total_seconds()
                if self._cache_timestamp else None
            )
        }

def test_improved_sync():
    """测试改进的时间同步"""
    print("测试改进的时间同步解决方案")
    print("=" * 50)
    
    sync = ImprovedNetworkTimeSync()
    
    # 测试同步
    print("1. 测试时间同步...")
    success, offset = sync.sync_time()
    
    if success:
        print(f"✅ 时间同步成功，偏移: {offset:.3f}秒")
    else:
        print("❌ 时间同步失败")
    
    # 测试获取真实时间
    print("\n2. 测试获取真实时间...")
    real_time = sync.get_real_datetime()
    system_time = datetime.now()
    
    print(f"系统时间: {system_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"网络时间: {real_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 显示统计信息
    print("\n3. 统计信息:")
    stats = sync.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    test_improved_sync()