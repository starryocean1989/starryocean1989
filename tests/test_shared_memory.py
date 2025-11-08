import multiprocessing
import time
from native_calendar import NativeCalendar
import importlib.resources

def worker(start_year, bitmap_path):
    """子进程工作函数"""
    calendar = NativeCalendar(start_year, bitmap_path)
    # 在这里可以添加更多测试，例如，检查特定的交易日
    is_trading = calendar.is_trading_day(2024, 5, 20)
    print(f"子进程: 2024-05-20 是否是交易日? {is_trading}")
    time.sleep(2) # 等待，以确保主进程不会过早退出

def test_shared_memory():
    """测试多进程共享内存"""
    with importlib.resources.path('native_calendar', 'sse_calendar.bin') as bitmap_path:
        bitmap_path_str = str(bitmap_path)
        
        # 在主进程中创建日历实例
        main_calendar = NativeCalendar(1990, bitmap_path_str)
        is_trading_main = main_calendar.is_trading_day(2024, 5, 20)
        print(f"主进程: 2024-05-20 是否是交易日? {is_trading_main}")

        # 创建并启动子进程
        p = multiprocessing.Process(target=worker, args=(1990, bitmap_path_str))
        p.start()
        p.join()

        # 可以在这里添加断言来验证结果
        assert p.exitcode == 0