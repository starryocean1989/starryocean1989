"""
简易的Mock TCP服务器,用于netprobe测试
启动一个会立即拒绝连接或接受连接的服务器
"""
import socket
import threading
import time


class MockTCPServer:
    """Mock TCP服务器,支持快速接受/拒绝连接"""
    
    def __init__(self, host='127.0.0.1', port=0, accept_connections=True):
        """
        Args:
            host: 监听地址
            port: 监听端口(0表示随机端口)
            accept_connections: True=接受连接, False=立即关闭socket拒绝连接
        """
        self.host = host
        self.port = port
        self.accept_connections = accept_connections
        self.socket = None
        self.thread = None
        self.running = False
        self.actual_port = None
        
    def start(self):
        """启动服务器"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.actual_port = self.socket.getsockname()[1]
        self.socket.listen(5)
        self.socket.settimeout(0.1)  # 短超时,方便停止
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        time.sleep(0.05)  # 等待服务器启动
        
    def _run(self):
        """服务器主循环"""
        while self.running:
            try:
                if self.socket is None:
                    break
                conn, addr = self.socket.accept()
                if self.accept_connections:
                    # 接受连接但立即关闭
                    conn.close()
                else:
                    # 这种情况不应该发生,因为我们会在listen前关闭
                    conn.close()
            except socket.timeout:
                continue
            except Exception:
                if self.running:
                    break
                    
    def stop(self):
        """停止服务器"""
        self.running = False
        if self.socket:
            self.socket.close()
        if self.thread:
            self.thread.join(timeout=1.0)
            
    def __enter__(self):
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
