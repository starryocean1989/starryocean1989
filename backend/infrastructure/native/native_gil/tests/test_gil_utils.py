# -*- coding: utf-8 -*-
"""
测试GIL管理工具
"""

import unittest
import threading
import time

try:
    import native_gil
    NATIVE_GIL_AVAILABLE = True
except ImportError:
    NATIVE_GIL_AVAILABLE = False
    print("Warning: native_gil extension not available, skipping tests")


@unittest.skipUnless(NATIVE_GIL_AVAILABLE, "native_gil extension not available")
class TestGilUtils(unittest.TestCase):
    """测试GIL管理工具"""
    
    def test_release_restore_gil(self):
        """测试释放和恢复GIL"""
        tstate = native_gil.release_gil()
        self.assertIsNotNone(tstate)
        
        # 恢复GIL
        native_gil.restore_gil(tstate)
    
    def test_gil_release_allows_parallel_execution(self):
        """测试释放GIL后允许并行执行"""
        results = []
        lock = threading.Lock()
        
        def cpu_task(task_id):
            """模拟CPU密集型任务"""
            tstate = native_gil.release_gil()
            try:
                # CPU密集型计算
                total = 0
                for i in range(1000000):
                    total += i
                
                with lock:
                    results.append((task_id, total))
            finally:
                native_gil.restore_gil(tstate)
        
        # 创建多个线程并行执行
        threads = []
        for i in range(4):
            t = threading.Thread(target=cpu_task, args=(i,))
            t.start()
            threads.append(t)
        
        # 等待所有线程完成
        for t in threads:
            t.join()
        
        # 验证结果
        self.assertEqual(len(results), 4)
        self.assertEqual(sorted([r[0] for r in results]), [0, 1, 2, 3])
    
    def test_execute_cpu_task(self):
        """测试执行CPU密集型任务"""
        def cpu_function(x, y):
            return x + y
        
        result = native_gil.execute_cpu_task(cpu_function, (1, 2), None)
        self.assertEqual(result, 3)


if __name__ == '__main__':
    unittest.main()

