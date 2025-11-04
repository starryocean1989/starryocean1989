# -*- coding: utf-8 -*-
"""
测试脚本：从调用链顶端测试北证、T+0基金、可转债列表获取和IPO日期下载
"""
import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from backend.infrastructure.data_module_vnpy.core_engine import ChinaStockEngine, ConfigManager
from backend.infrastructure.data_module_vnpy.data_acquisition import SymbolLoader
from vnpy.event import EventEngine

def test_symbol_classification():
    """测试品种分类（北证、T+0基金、可转债）"""
    print("=" * 80)
    print("测试1: 品种分类（北证、T+0基金、可转债）")
    print("=" * 80)
    
    # 初始化事件引擎
    event_engine = EventEngine()
    
    # 初始化SymbolLoader
    symbol_loader = SymbolLoader(event_engine)
    
    # 重新加载并分类
    print("\n正在重新加载并分类品种列表...")
    classified = symbol_loader.reload_and_classify(force_reload=True)
    
    if not classified:
        print("❌ 品种分类失败：返回结果为空")
        return False
    
    # 检查关键分类
    categories = ["北证A股", "T+0基金", "可转债"]
    all_good = True
    
    for category in categories:
        count = len(classified.get(category, []))
        if count > 0:
            print(f"✅ {category}: {count} 个品种")
            # 显示前3个示例
            examples = classified.get(category, [])[:3]
            for example in examples:
                code = example.get("code", "N/A")
                name = example.get("name", "N/A")
                print(f"   - {code}: {name}")
        else:
            print(f"❌ {category}: 0 个品种（分类失败）")
            all_good = False
    
    # 显示所有分类统计
    print("\n所有分类统计:")
    for category, items in classified.items():
        if isinstance(items, list):
            print(f"  {category}: {len(items)} 个品种")
    
    return all_good


def test_ipo_download():
    """测试IPO日期下载"""
    print("\n" + "=" * 80)
    print("测试2: IPO日期下载")
    print("=" * 80)
    
    # 初始化事件引擎
    event_engine = EventEngine()
    
    # 初始化SymbolLoader获取所有品种
    symbol_loader = SymbolLoader(event_engine)
    classified = symbol_loader.reload_and_classify(force_reload=False)
    
    if not classified:
        print("❌ 无法获取品种列表")
        return False
    
    # 收集所有品种代码
    all_symbols = []
    for category, items in classified.items():
        if isinstance(items, list):
            for item in items:
                code = item.get("code", "")
                if code:
                    all_symbols.append(code)
    
    print(f"\n收集到 {len(all_symbols)} 个品种代码")
    
    # 测试IPO日期下载（使用前100个品种进行测试）
    test_symbols = all_symbols[:100]
    print(f"使用前 {len(test_symbols)} 个品种进行IPO日期下载测试...")
    
    from backend.infrastructure.data_module_vnpy.data_acquisition import download_ipo_dates
    
    def progress_callback(completed, total, msg):
        """进度回调"""
        if completed % 10 == 0 or completed == total:
            print(f"  进度: {completed}/{total} ({completed*100//total}%) - {msg}")
    
    # 下载IPO日期
    print("\n开始下载IPO日期...")
    ipo_dates = download_ipo_dates(
        symbols=test_symbols,
        progress_callback=progress_callback,
        use_multiprocess=False,  # 使用单进程多协程模式进行测试
        max_workers=4
    )
    
    if not ipo_dates:
        print("❌ IPO日期下载失败：返回结果为空")
        return False
    
    # 统计结果
    success_count = sum(1 for v in ipo_dates.values() if v is not None)
    total_count = len(ipo_dates)
    
    print(f"\n✅ IPO日期下载完成:")
    print(f"  成功: {success_count}/{total_count} ({success_count*100//total_count if total_count > 0 else 0}%)")
    
    # 显示前10个成功示例
    print("\n前10个成功示例:")
    count = 0
    for symbol, ipo_date in ipo_dates.items():
        if ipo_date is not None and count < 10:
            print(f"   {symbol}: {ipo_date}")
            count += 1
    
    # 检查缓存文件
    config_manager = ConfigManager.get_instance()
    cache_file = config_manager.get_cache_dir() / "ipo_dates.json"
    
    if cache_file.exists():
        print(f"\n✅ IPO日期缓存文件已生成: {cache_file}")
        file_size = cache_file.stat().st_size
        print(f"   文件大小: {file_size} 字节")
        
        # 读取并验证缓存文件
        import json
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            # 处理缓存格式
            if isinstance(cached_data, dict):
                if "data" in cached_data:
                    cached_dates = cached_data["data"]
                else:
                    cached_dates = cached_data
                
                # 排除_meta字段
                cached_count = len([k for k in cached_dates.keys() if k != "_meta"])
                print(f"   缓存中的品种数: {cached_count}")
                
                if cached_count > 0:
                    print("   ✅ 缓存文件有效")
                    return True
                else:
                    print("   ❌ 缓存文件为空")
                    return False
        except Exception as e:
            print(f"   ❌ 读取缓存文件失败: {e}")
            return False
    else:
        print(f"\n❌ IPO日期缓存文件未生成: {cache_file}")
        return False


def test_cache_validation():
    """测试缓存验证流程（模拟启动流程）"""
    print("\n" + "=" * 80)
    print("测试3: 缓存验证流程（模拟启动流程）")
    print("=" * 80)
    
    # 初始化事件引擎
    event_engine = EventEngine()
    
    # 初始化引擎
    engine = ChinaStockEngine(event_engine)
    
    # 获取当前日期
    from datetime import datetime
    current_date = datetime.now().date()
    
    # 创建临时stage_logger（用于测试）
    import logging
    stage_logger = logging.getLogger("test.stage")
    
    # 测试品种列表缓存验证
    print("\n测试品种列表缓存验证...")
    result1 = engine._validate_symbol_list_cache(current_date, stage_logger)
    
    if result1.get("success"):
        print("✅ 品种列表缓存验证成功")
        total_count = result1.get("total_count", 0)
        print(f"   总品种数: {total_count}")
        
        # 检查关键分类
        cache_file = engine.config_manager.get_cache_dir() / "stock_list_classified.json"
        if cache_file.exists():
            import json
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                
                # 处理缓存格式
                if isinstance(cached_data, dict):
                    if "data" in cached_data:
                        classified = cached_data["data"]
                    elif "classified" in cached_data:
                        classified = cached_data["classified"]
                    else:
                        classified = cached_data
                    
                    categories = ["北证A股", "T+0基金", "可转债"]
                    print("\n   关键分类统计:")
                    for category in categories:
                        count = len(classified.get(category, []))
                        status = "✅" if count > 0 else "❌"
                        print(f"     {status} {category}: {count} 个品种")
            except Exception as e:
                print(f"   ⚠️ 读取缓存文件失败: {e}")
    else:
        print("❌ 品种列表缓存验证失败")
        print(f"   错误: {result1.get('error', 'Unknown')}")
    
    # 测试IPO日期缓存验证
    print("\n测试IPO日期缓存验证...")
    result2 = engine._validate_ipo_cache(current_date, stage_logger)
    
    if result2.get("success"):
        print("✅ IPO日期缓存验证成功")
        
        # 检查缓存文件
        cache_file = engine.config_manager.get_cache_dir() / "ipo_dates.json"
        if cache_file.exists():
            import json
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                
                # 处理缓存格式
                if isinstance(cached_data, dict):
                    if "data" in cached_data:
                        cached_dates = cached_data["data"]
                    else:
                        cached_dates = cached_data
                    
                    # 排除_meta字段
                    cached_count = len([k for k in cached_dates.keys() if k != "_meta"])
                    print(f"   缓存中的品种数: {cached_count}")
                    
                    if cached_count > 0:
                        print("   ✅ 缓存文件有效")
                    else:
                        print("   ❌ 缓存文件为空")
            except Exception as e:
                print(f"   ⚠️ 读取缓存文件失败: {e}")
    else:
        print("❌ IPO日期缓存验证失败")
        print(f"   错误: {result2.get('error', 'Unknown')}")
    
    return result1.get("success") and result2.get("success")


if __name__ == "__main__":
    print("开始测试品种分类和IPO日期下载...\n")
    
    # 测试1: 品种分类
    result1 = test_symbol_classification()
    
    # 测试2: IPO日期下载
    result2 = test_ipo_download()
    
    # 测试3: 缓存验证流程
    result3 = test_cache_validation()
    
    # 总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    print(f"品种分类测试: {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"IPO日期下载测试: {'✅ 通过' if result2 else '❌ 失败'}")
    print(f"缓存验证流程测试: {'✅ 通过' if result3 else '❌ 失败'}")
    
    if result1 and result2 and result3:
        print("\n🎉 所有测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败，请检查日志")
        sys.exit(1)

