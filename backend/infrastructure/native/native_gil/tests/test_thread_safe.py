# -*- coding: utf-8 -*-
"""
测试线程安全数据结构
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
class TestThreadSafeQueue(unittest.TestCase):
    """测试线程安全队列"""
    
    def test_queue_basic_operations(self):
        """测试队列基本操作"""
        queue = native_gil.ThreadSafeQueue()
        
        # 测试空队列
        self.assertTrue(queue.empty())
        self.assertEqual(queue.size(), 0)
        
        # 放入元素
        queue.put("item1")
        queue.put("item2")
        queue.put("item3")
        
        # 检查大小
        self.assertEqual(queue.size(), 3)
        self.assertFalse(queue.empty())
        
        # 获取元素
        item1 = queue.get()
        self.assertEqual(item1, "item1")
        self.assertEqual(queue.size(), 2)
        
        item2 = queue.get()
        self.assertEqual(item2, "item2")
        self.assertEqual(queue.size(), 1)
        
        item3 = queue.get()
        self.assertEqual(item3, "item3")
        self.assertEqual(queue.size(), 0)
        self.assertTrue(queue.empty())
        
        # 测试空队列获取
        with self.assertRaises(IndexError):
            queue.get()
    
    def test_queue_thread_safety(self):
        """测试队列线程安全性"""
        queue = native_gil.ThreadSafeQueue()
        results = []
        lock = threading.Lock()
        
        def producer(thread_id, count):
            """生产者线程"""
            for i in range(count):
                queue.put(f"thread_{thread_id}_item_{i}")
        
        def consumer(thread_id, count):
            """消费者线程"""
            for i in range(count):
                try:
                    item = queue.get()
                    with lock:
                        results.append(item)
                except IndexError:
                    pass
        
        # 创建生产者线程
        producer_threads = []
        for i in range(3):
            t = threading.Thread(target=producer, args=(i, 10))
            t.start()
            producer_threads.append(t)
        
        # 创建消费者线程
        consumer_threads = []
        for i in range(3):
            t = threading.Thread(target=consumer, args=(i, 10))
            t.start()
            consumer_threads.append(t)
        
        # 等待所有线程完成
        for t in producer_threads:
            t.join()
        for t in consumer_threads:
            t.join()
        
        # 验证结果
        self.assertEqual(len(results), 30)
        self.assertEqual(queue.size(), 0)


@unittest.skipUnless(NATIVE_GIL_AVAILABLE, "native_gil extension not available")
class TestThreadSafeCounter(unittest.TestCase):
    """测试线程安全计数器"""
    
    def test_counter_basic_operations(self):
        """测试计数器基本操作"""
        counter = native_gil.ThreadSafeCounter(0)
        
        # 初始值
        self.assertEqual(counter.get(), 0)
        
        # 增加
        counter.increment()
        self.assertEqual(counter.get(), 1)
        
        counter.increment(5)
        self.assertEqual(counter.get(), 6)
        
        # 减少
        counter.decrement(2)
        self.assertEqual(counter.get(), 4)
        
        # 设置值
        counter.set(10)
        self.assertEqual(counter.get(), 10)
    
    def test_counter_thread_safety(self):
        """测试计数器线程安全性"""
        counter = native_gil.ThreadSafeCounter(0)
        
        def increment_task(count):
            """增加任务"""
            for i in range(count):
                counter.increment()
        
        def decrement_task(count):
            """减少任务"""
            for i in range(count):
                counter.decrement()
        
        # 创建多个线程并发操作
        threads = []
        for i in range(5):
            t = threading.Thread(target=increment_task, args=(1000,))
            t.start()
            threads.append(t)
        
        for i in range(3):
            t = threading.Thread(target=decrement_task, args=(500,))
            t.start()
            threads.append(t)
        
        # 等待所有线程完成
        for t in threads:
            t.join()
        
        # 验证结果：5 * 1000 - 3 * 500 = 3500
        self.assertEqual(counter.get(), 3500)


if __name__ == '__main__':
    unittest.main()

