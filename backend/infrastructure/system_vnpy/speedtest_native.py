# -*- coding: utf-8 -*-
"""
自研网络测速模块 - 无需第三方测速库

使用公共测速站点进行网络延迟和下载速度测试，无限流风险。
"""
import time
import random
import requests
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime

# 导入日志系统
import logging

logger = logging.getLogger(__name__)


class NetworkSpeedTester:
    """网络测速器 - 基于公共测速站点的纯Python实现"""

    def __init__(self, timeout: int = 15, use_browser_headers: bool = False):
        """初始化测速器

        Args:
            timeout: 单次请求超时时间（秒）
            use_browser_headers: 是否使用完整浏览器头部（用于延迟测试模拟真实浏览器）
        """
        self.timeout = timeout
        self.session = requests.Session()

        if use_browser_headers:
            # 完整模拟真实浏览器头部，降低被识别为爬虫的风险
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            })
            logger.info(f"[SPEEDTEST-INIT] 初始化网络测速器（浏览器模式），超时={timeout}秒")
        else:
            # 简化头部（用于带宽测试，镜像站使用）
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Terminal/0.50 NetworkSpeedTester'
            })
            logger.info(f"[SPEEDTEST-INIT] 初始化网络测速器，超时={timeout}秒")

    def test_latency(self, url: str) -> Dict[str, Any]:
        """测试网络延迟（ms）

        Args:
            url: 测试URL

        Returns:
            测试结果字典，包含 ping_ms、url、status
        """
        try:
            logger.debug(f"[SPEEDTEST-PING] 开始测试延迟: {url} (超时={self.timeout}秒)")
            start = time.perf_counter()
            # 使用实例的超时时间（支持动态配置），设置连接和读取超时
            response = self.session.head(url, timeout=(self.timeout, self.timeout), allow_redirects=True)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if response.status_code < 400:
                result = {
                    'ping_ms': round(elapsed_ms, 2),
                    'url': url,
                    'status': 'success'
                }
                logger.info(f"[SPEEDTEST-PING] ✅ 成功: {elapsed_ms:.2f}ms - {url}")
                return result
            else:
                logger.warning(f"[SPEEDTEST-PING] ❌ HTTP {response.status_code}: {url}")
                return {
                    'ping_ms': -1,
                    'url': url,
                    'error': f'HTTP {response.status_code}',
                    'status': 'failed'
                }

        except requests.exceptions.Timeout:
            elapsed_ms = (time.perf_counter() - start) * 1000 if 'start' in locals() else 0
            logger.warning(f"[SPEEDTEST-PING] ❌ 超时({elapsed_ms:.0f}ms, 超时设置={self.timeout}秒): {url}")
            return {
                'ping_ms': -1,
                'url': url,
                'error': f'请求超时（{self.timeout}秒）',
                'status': 'timeout'
            }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000 if 'start' in locals() else 0
            logger.error(f"[SPEEDTEST-PING] ❌ 失败({elapsed_ms:.0f}ms): {url} - {e}")
            return {
                'ping_ms': -1,
                'url': url,
                'error': str(e),
                'status': 'failed'
            }

    def test_latency_browser_mode(self, url: str) -> Dict[str, Any]:
        """测试网络延迟（浏览器模式：GET请求+完整头部，但只读响应头）

        使用GET请求模拟真实浏览器访问，但只读取响应头就关闭连接，不下载内容。
        这样可以更真实地模拟用户打开网页的行为，降低被识别为爬虫的风险。

        Args:
            url: 测试URL

        Returns:
            测试结果字典，包含 ping_ms、url、status
        """
        try:
            logger.debug(f"[SPEEDTEST-PING-BROWSER] 开始测试延迟（浏览器模式）: {url} (超时={self.timeout}秒)")
            start = time.perf_counter()

            # 使用GET请求模拟浏览器，但stream=True可以在读取响应头后立即关闭
            response = self.session.get(
                url,
                timeout=(self.timeout, self.timeout),
                allow_redirects=True,
                stream=True  # 流式模式，可以立即关闭连接
            )

            # 只测量到响应头返回的时间（不下载内容）
            elapsed_ms = (time.perf_counter() - start) * 1000

            # 立即关闭连接，不下载内容
            response.close()

            if response.status_code < 400:
                result = {
                    'ping_ms': round(elapsed_ms, 2),
                    'url': url,
                    'status': 'success'
                }
                logger.info(f"[SPEEDTEST-PING-BROWSER] ✅ 成功: {elapsed_ms:.2f}ms - {url}")
                return result
            else:
                logger.warning(f"[SPEEDTEST-PING-BROWSER] ❌ HTTP {response.status_code}: {url}")
                return {
                    'ping_ms': -1,
                    'url': url,
                    'error': f'HTTP {response.status_code}',
                    'status': 'failed'
                }

        except requests.exceptions.Timeout:
            elapsed_ms = (time.perf_counter() - start) * 1000 if 'start' in locals() else 0
            logger.warning(f"[SPEEDTEST-PING-BROWSER] ❌ 超时({elapsed_ms:.0f}ms, 超时设置={self.timeout}秒): {url}")
            return {
                'ping_ms': -1,
                'url': url,
                'error': f'请求超时（{self.timeout}秒）',
                'status': 'timeout'
            }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000 if 'start' in locals() else 0
            logger.error(f"[SPEEDTEST-PING-BROWSER] ❌ 失败({elapsed_ms:.0f}ms): {url} - {e}")
            return {
                'ping_ms': -1,
                'url': url,
                'error': str(e),
                'status': 'failed'
            }

    def test_download_speed(self, url: str, max_duration: int = 10, max_bytes: Optional[int] = None) -> Dict[str, Any]:
        """测试下载速度

        Args:
            url: 测速文件URL
            max_duration: 最大测试时长（秒）
            max_bytes: 最大下载字节数（可选，用于Range请求，仅下载文件的前N字节）

        Returns:
            测试结果字典，包含 download_mbps、download_MB_s、total_bytes、elapsed_seconds
        """
        try:
            logger.info(f"[SPEEDTEST-DOWNLOAD] 开始测速: {url} (超时={self.timeout}秒, 最大时长={max_duration}秒, 最大字节数={max_bytes or '无限制'})")
            start = time.perf_counter()

            # 设置请求头（如果需要Range请求）
            headers = {}
            if max_bytes:
                headers['Range'] = f'bytes=0-{max_bytes - 1}'
                logger.debug(f"[SPEEDTEST-DOWNLOAD] 使用Range请求: bytes=0-{max_bytes - 1}")

            # 设置连接和读取超时
            response = self.session.get(
                url,
                timeout=(self.timeout, self.timeout),  # (连接超时, 读取超时)
                stream=True,  # 流式下载
                headers=headers
            )

            # 支持200（完整下载）和206（部分内容，Range请求）
            if response.status_code not in (200, 206):
                # 404或其他错误，记录详细错误信息
                error_msg = f'HTTP {response.status_code}'
                if response.status_code == 404:
                    error_msg = f'HTTP 404 (文件不存在，URL可能已失效): {url}'
                logger.error(f"[SPEEDTEST-DOWNLOAD] {error_msg}")
                return {
                    'download_mbps': -1,
                    'download_MB_s': -1,
                    'error': error_msg,
                    'url': url,
                    'status': 'failed',
                    'http_status': response.status_code
                }

            # Range请求返回206是正常的
            if response.status_code == 206:
                logger.debug(f"[SPEEDTEST-DOWNLOAD] Range请求成功（206 Partial Content）")

            total_bytes = 0
            chunk_size = 65536  # 64KB 每块
            last_progress_time = start
            no_progress_timeout = 3.0  # 3秒无进度则认为卡住
            stop_flag = threading.Event()

            # 使用线程监控超时，避免iter_content无限阻塞
            def timeout_monitor():
                """超时监控线程"""
                while not stop_flag.is_set():
                    current_time = time.perf_counter()
                    elapsed = current_time - start
                    no_progress_elapsed = current_time - last_progress_time

                    # 检查总超时时间
                    if elapsed > max_duration:
                        logger.debug(f"[SPEEDTEST-DOWNLOAD] 达到最大时长 {max_duration}秒，停止下载")
                        stop_flag.set()
                        try:
                            response.close()
                        except:
                            pass
                        break

                    # 检查无进度超时（关键修复：防止iter_content无限阻塞）
                    if no_progress_elapsed > no_progress_timeout and elapsed > 2.0:  # 至少等待2秒才开始检查无进度
                        logger.warning(f"[SPEEDTEST-DOWNLOAD] 无进度超时（{no_progress_timeout}秒无数据），停止下载")
                        stop_flag.set()
                        try:
                            response.close()
                        except:
                            pass
                        break

                    time.sleep(0.5)  # 每0.5秒检查一次

            monitor_thread = threading.Thread(target=timeout_monitor, daemon=True)
            monitor_thread.start()

            # 流式下载并计算速度（添加chunk读取超时保护）
            try:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if stop_flag.is_set():
                        break

                    if chunk:
                        total_bytes += len(chunk)
                        last_progress_time = time.perf_counter()

                        # 如果设置了最大字节数，且已达到，停止下载
                        if max_bytes and total_bytes >= max_bytes:
                            logger.debug(f"[SPEEDTEST-DOWNLOAD] 已下载{max_bytes}字节，达到上限，停止下载")
                            break

                    # 双重检查（虽然monitor线程会处理，但这里也检查一次）
                    current_time = time.perf_counter()
                    if current_time - start > max_duration:
                        break

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                logger.warning(f"[SPEEDTEST-DOWNLOAD] 连接异常: {e}（已下载{total_bytes}字节）")
                stop_flag.set()
                try:
                    response.close()
                except:
                    pass
            except Exception as e:
                logger.warning(f"[SPEEDTEST-DOWNLOAD] 读取异常: {e}（已下载{total_bytes}字节）")
                stop_flag.set()
                try:
                    response.close()
                except:
                    pass
            finally:
                stop_flag.set()  # 确保监控线程退出

            elapsed = time.perf_counter() - start

            # 计算速度
            if elapsed > 0 and total_bytes > 0:
                speed_bps = (total_bytes * 8) / elapsed  # bits per second
                speed_mbps = speed_bps / 1_000_000       # Mbps
                speed_MB_s = total_bytes / elapsed / 1_048_576  # MB/s
            else:
                speed_mbps = 0
                speed_MB_s = 0

            # 如果没有下载到任何数据，返回失败
            if total_bytes == 0:
                logger.error(f"[SPEEDTEST-DOWNLOAD] 未下载到任何数据（耗时{elapsed:.2f}秒）")
                return {
                    'download_mbps': -1,
                    'download_MB_s': -1,
                    'error': f'未下载到任何数据（耗时{elapsed:.2f}秒）',
                    'url': url,
                    'status': 'failed'
                }

            result = {
                'download_mbps': round(speed_mbps, 2),
                'download_MB_s': round(speed_MB_s, 2),
                'total_bytes': total_bytes,
                'total_MB': round(total_bytes / 1_048_576, 2),
                'elapsed_seconds': round(elapsed, 2),
                'url': url,
                'status': 'success'
            }

            logger.info(
                f"[SPEEDTEST-DOWNLOAD] 成功: {result['download_mbps']} Mbps "
                f"({result['download_MB_s']} MB/s) - 下载 {result['total_MB']} MB"
            )
            return result

        except requests.exceptions.Timeout:
            logger.error(f"[SPEEDTEST-DOWNLOAD] 超时({self.timeout}秒): {url}")
            return {
                'download_mbps': -1,
                'download_MB_s': -1,
                'error': f'超时({self.timeout}秒)',
                'url': url,
                'status': 'timeout'
            }
        except Exception as e:
            logger.error(f"[SPEEDTEST-DOWNLOAD] 失败: {url} - {e}")
            return {
                'download_mbps': -1,
                'download_MB_s': -1,
                'error': str(e),
                'url': url,
                'status': 'failed'
            }

    def test_with_fallback(
        self,
        server_configs: List[Dict[str, Any]],
        test_type: str = 'both'
    ) -> Dict[str, Any]:
        """带降级的测速（尝试多个服务器，按顺序）

        注意：此方法已不再使用，保留仅用于兼容性。
        当前使用 test_ping_with_random_retry 和 test_bandwidth_with_random_retry。

        Args:
            server_configs: 服务器配置列表，每个包含 name、ping_url、download_url
            test_type: 测试类型 'ping', 'download', 'both'

        Returns:
            测试结果字典
        """
        last_error = None
        start_time = time.perf_counter()

        # 添加总体超时保护（避免所有服务器都超时导致总时间过长）
        max_total_time = 30 if test_type == 'ping' else 60  # 延迟测试30秒，完整测试60秒

        logger.info(f"[SPEEDTEST-FALLBACK] 开始测速（类型={test_type}，最多{len(server_configs)}个服务器，总体超时={max_total_time}秒）")

        for i, config in enumerate(server_configs, 1):
            # 检查总体超时
            elapsed = time.perf_counter() - start_time
            if elapsed >= max_total_time:
                logger.warning(f"[SPEEDTEST-FALLBACK] 总体超时（{elapsed:.1f}秒 >= {max_total_time}秒），停止测试")
                break

            server_name = config.get('name', f'服务器{i}')
            server_timeout = config.get('timeout', self.timeout)
            logger.info(f"[SPEEDTEST-FALLBACK] 尝试服务器 {i}/{len(server_configs)}: {server_name} (超时={server_timeout}秒)")

            result = {
                'server_name': server_name,
                'server_index': i,
                'test_time': datetime.now().isoformat(),
                'test_type': test_type
            }

            # 测试延迟
            if test_type in ('ping', 'both'):
                ping_url = config.get('ping_url')
                if ping_url:
                    ping_start = time.perf_counter()
                    ping_result = self.test_latency(ping_url)
                    ping_elapsed = time.perf_counter() - ping_start
                    logger.debug(f"[SPEEDTEST-FALLBACK] 延迟测试耗时: {ping_elapsed:.2f}秒")

                    if ping_result.get('status') == 'success':
                        result['ping_ms'] = ping_result['ping_ms']
                        result['ping_url'] = ping_url
                        logger.info(f"[SPEEDTEST-FALLBACK] ✅ 延迟测试成功: {server_name} ({ping_result['ping_ms']}ms)")
                    else:
                        logger.warning(
                            f"[SPEEDTEST-FALLBACK] ❌ 延迟测试失败: {server_name} - "
                            f"{ping_result.get('error')} (耗时{ping_elapsed:.2f}秒)"
                        )
                        last_error = ping_result.get('error')
                        continue

            # 测试下载速度
            if test_type in ('download', 'both'):
                download_url = config.get('download_url')
                if download_url:
                    download_start = time.perf_counter()
                    # 使用服务器配置的超时时间
                    original_timeout = self.timeout
                    self.timeout = server_timeout
                    try:
                        download_result = self.test_download_speed(download_url)
                    finally:
                        self.timeout = original_timeout

                    download_elapsed = time.perf_counter() - download_start
                    logger.debug(f"[SPEEDTEST-FALLBACK] 下载测试耗时: {download_elapsed:.2f}秒")

                    if download_result.get('status') == 'success':
                        result['download_mbps'] = download_result['download_mbps']
                        result['download_MB_s'] = download_result['download_MB_s']
                        result['download_url'] = download_url
                        result['status'] = 'success'
                        total_elapsed = time.perf_counter() - start_time
                        logger.info(
                            f"[SPEEDTEST-FALLBACK] ✅ 测速成功: {server_name} "
                            f"(下载{result['download_mbps']}Mbps, 总耗时{total_elapsed:.2f}秒)"
                        )
                        return result
                    else:
                        logger.warning(
                            f"[SPEEDTEST-FALLBACK] ❌ 下载测速失败: {server_name} - "
                            f"{download_result.get('error')} (耗时{download_elapsed:.2f}秒)"
                        )
                        last_error = download_result.get('error')
                        continue

            # 如果只测延迟且成功，返回结果
            if test_type == 'ping' and 'ping_ms' in result:
                result['status'] = 'success'
                total_elapsed = time.perf_counter() - start_time
                logger.info(
                    f"[SPEEDTEST-FALLBACK] ✅ 延迟测试成功: {server_name} "
                    f"(延迟{result['ping_ms']}ms, 总耗时{total_elapsed:.2f}秒)"
                )
                return result

        # 所有服务器都失败
        total_elapsed = time.perf_counter() - start_time
        logger.error(
            f"[SPEEDTEST-FALLBACK] ❌ 所有测速服务器均不可用 "
            f"(尝试了{len(server_configs)}个服务器，总耗时{total_elapsed:.2f}秒)"
        )
        return {
            'error': last_error or '所有测速服务器均不可用',
            'status': 'all_failed',
            'test_time': datetime.now().isoformat(),
            'test_type': test_type,
            'total_time_seconds': round(total_elapsed, 2)
        }

    def test_ping_with_random_retry(
        self,
        server_configs: List[Dict[str, Any]],
        max_retries: int = 3,
        timeout: int = 5
    ) -> Dict[str, Any]:
        """延迟测试（随机选择+重试策略）

        策略：
        1. 从服务器池中随机选择一个服务器
        2. 超时时间5秒
        3. 超时后重新随机选择重测
        4. 成功即停止
        5. 最多重试3次

        Args:
            server_configs: 服务器配置列表
            max_retries: 最大重试次数
            timeout: 超时时间（秒）

        Returns:
            测试结果字典
        """
        if not server_configs:
            return {
                'error': '服务器池为空',
                'status': 'failed',
                'test_time': datetime.now().isoformat()
            }

        # 过滤出启用的服务器
        enabled_servers = [s for s in server_configs if s.get('enabled', True)]
        if not enabled_servers:
            return {
                'error': '没有启用的服务器',
                'status': 'failed',
                'test_time': datetime.now().isoformat()
            }

        last_error = None
        tested_servers = []  # 记录已测试的服务器，避免重复
        test_start_time = time.perf_counter()

        for attempt in range(1, max_retries + 1):
            # 检查总体超时（如果已经超过最大允许时间，提前退出）
            total_elapsed = time.perf_counter() - test_start_time
            max_total_time = timeout * max_retries + 2  # 允许稍微超过一点
            if total_elapsed > max_total_time:
                logger.warning(f"[PING-RANDOM] 总体超时（{total_elapsed:.1f}秒 > {max_total_time}秒），停止重试")
                break

            # 随机选择一个未测试的服务器
            available_servers = [s for s in enabled_servers if s not in tested_servers]
            if not available_servers:
                # 所有服务器都测试过了，重置列表重新开始
                tested_servers = []
                available_servers = enabled_servers

            selected_server = random.choice(available_servers)
            tested_servers.append(selected_server)

            server_name = selected_server.get('name', '未知服务器')
            ping_url = selected_server.get('ping_url')

            if not ping_url:
                last_error = f'{server_name} 缺少ping_url配置'
                logger.warning(f"[PING-RANDOM] 第{attempt}次尝试失败: {last_error}")
                continue

            logger.info(f"[PING-RANDOM] 第{attempt}次尝试，随机选择: {server_name}")

            # 临时修改超时时间
            original_timeout = self.timeout
            self.timeout = timeout

            try:
                ping_result = self.test_latency(ping_url)
            finally:
                self.timeout = original_timeout

            if ping_result.get('status') == 'success':
                elapsed = time.perf_counter() - test_start_time
                logger.info(f"[PING-RANDOM] ✅ 成功（第{attempt}次，总耗时{elapsed:.2f}秒）: {server_name} ({ping_result['ping_ms']}ms)")
                return {
                    'ping_ms': ping_result['ping_ms'],
                    'server_name': server_name,
                    'ping_url': ping_url,
                    'attempt': attempt,
                    'status': 'success',
                    'test_time': datetime.now().isoformat(),
                    'total_time_seconds': round(elapsed, 2)
                }
            else:
                last_error = ping_result.get('error', '未知错误')
                elapsed = time.perf_counter() - test_start_time
                logger.warning(f"[PING-RANDOM] ❌ 第{attempt}次尝试失败（耗时{elapsed:.2f}秒）: {server_name} - {last_error}")

        # 所有重试都失败
        logger.error(f"[PING-RANDOM] ❌ 所有{max_retries}次尝试均失败")
        return {
            'error': last_error or '所有服务器测试失败',
            'status': 'all_failed',
            'attempts': max_retries,
            'test_time': datetime.now().isoformat()
        }

    def test_bandwidth_with_random_retry(
        self,
        server_configs: List[Dict[str, Any]],
        max_retries: int = 3,
        timeout: int = 10
    ) -> Dict[str, Any]:
        """带宽测试（随机选择+重试策略）

        策略：
        1. 从服务器池中随机选择一个服务器
        2. 先测试延迟（确保连通性）
        3. 延迟测试通过后，测试下载速度
        4. 超时时间10秒
        5. 失败后重新随机选择重测
        6. 成功即停止
        7. 最多重试3次

        Args:
            server_configs: 服务器配置列表
            max_retries: 最大重试次数
            timeout: 超时时间（秒）

        Returns:
            测试结果字典
        """
        if not server_configs:
            return {
                'error': '服务器池为空',
                'status': 'failed',
                'test_time': datetime.now().isoformat()
            }

        # 过滤出启用的服务器
        enabled_servers = [s for s in server_configs if s.get('enabled', True)]
        if not enabled_servers:
            return {
                'error': '没有启用的服务器',
                'status': 'failed',
                'test_time': datetime.now().isoformat()
            }

        last_error = None
        tested_servers = []  # 记录已测试的服务器，避免重复
        test_start_time = time.perf_counter()

        for attempt in range(1, max_retries + 1):
            # 检查总体超时（如果已经超过最大允许时间，提前退出）
            total_elapsed = time.perf_counter() - test_start_time
            max_total_time = (timeout + 10) * max_retries + 5  # 带宽测试更耗时，允许更长时间
            if total_elapsed > max_total_time:
                logger.warning(f"[BANDWIDTH-RANDOM] 总体超时（{total_elapsed:.1f}秒 > {max_total_time}秒），停止重试")
                break

            # 随机选择一个未测试的服务器
            available_servers = [s for s in enabled_servers if s not in tested_servers]
            if not available_servers:
                # 所有服务器都测试过了，重置列表重新开始
                tested_servers = []
                available_servers = enabled_servers

            selected_server = random.choice(available_servers)
            tested_servers.append(selected_server)

            server_name = selected_server.get('name', '未知服务器')
            ping_url = selected_server.get('ping_url')
            download_url = selected_server.get('download_url')

            if not ping_url or not download_url:
                last_error = f'{server_name} 缺少ping_url或download_url配置'
                logger.warning(f"[BANDWIDTH-RANDOM] 第{attempt}次尝试失败: {last_error}")
                continue

            logger.info(f"[BANDWIDTH-RANDOM] 第{attempt}次尝试，随机选择: {server_name}")

            # 临时修改超时时间
            original_timeout = self.timeout
            self.timeout = timeout

            try:
                # 步骤1：先测试延迟（确保连通性）
                ping_result = self.test_latency(ping_url)

                if ping_result.get('status') != 'success':
                    last_error = f'延迟测试失败: {ping_result.get("error")}'
                    elapsed = time.perf_counter() - test_start_time
                    logger.warning(f"[BANDWIDTH-RANDOM] ❌ 第{attempt}次延迟测试失败（耗时{elapsed:.2f}秒）: {server_name} - {last_error}")
                    continue

                logger.info(f"[BANDWIDTH-RANDOM] ✅ 延迟测试通过: {server_name} ({ping_result['ping_ms']}ms)")

                # 步骤2：测试下载速度（使用Range请求仅下载前10MB，使用20秒最大时长）
                download_result = self.test_download_speed(download_url, max_duration=20, max_bytes=10 * 1024 * 1024)

                if download_result.get('status') == 'success':
                    elapsed = time.perf_counter() - test_start_time
                    logger.info(
                        f"[BANDWIDTH-RANDOM] ✅ 成功（第{attempt}次，总耗时{elapsed:.2f}秒）: {server_name} "
                        f"(延迟{ping_result['ping_ms']}ms, 下载{download_result['download_mbps']}Mbps)"
                    )
                    return {
                        'ping_ms': ping_result['ping_ms'],
                        'download_mbps': download_result['download_mbps'],
                        'download_MB_s': download_result['download_MB_s'],
                        'server_name': server_name,
                        'ping_url': ping_url,
                        'download_url': download_url,
                        'attempt': attempt,
                        'status': 'success',
                        'test_time': datetime.now().isoformat(),
                        'total_time_seconds': round(elapsed, 2)
                    }
                else:
                    last_error = f'下载测试失败: {download_result.get("error")}'
                    elapsed = time.perf_counter() - test_start_time
                    logger.warning(f"[BANDWIDTH-RANDOM] ❌ 第{attempt}次下载测试失败（耗时{elapsed:.2f}秒）: {server_name} - {last_error}")

            finally:
                self.timeout = original_timeout

        # 所有重试都失败
        logger.error(f"[BANDWIDTH-RANDOM] ❌ 所有{max_retries}次尝试均失败")
        return {
            'error': last_error or '所有服务器测试失败',
            'status': 'all_failed',
            'attempts': max_retries,
            'test_time': datetime.now().isoformat()
        }

    def close(self):
        """关闭会话"""
        self.session.close()
        logger.debug("[SPEEDTEST] 会话已关闭")

