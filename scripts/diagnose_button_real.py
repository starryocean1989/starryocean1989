# -*- coding: utf-8 -*-
"""
实时诊断：检查按钮状态和缺失品种数
"""
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def check_database_missing_count():
    """从数据库查询缺失品种数"""
    print("=" * 70)
    print("步骤1：从数据库查询缺失品种")
    print("=" * 70)
    
    try:
        from backend.services.database_adapter import get_db_manager
        
        db = get_db_manager()
        
        # 获取本地数据索引
        local_symbols = db.get_local_data_index()
        print(f"✅ 本地品种数: {len(local_symbols)}")
        
        # 获取失效品种
        invalid_symbols = db.get_invalid_symbols()
        print(f"✅ 失效品种数: {len(invalid_symbols)}")
        
        return local_symbols, invalid_symbols
        
    except Exception as e:
        print(f"❌ 查询数据库失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def check_reference_symbols():
    """从缓存文件获取参考品种"""
    print("\n" + "=" * 70)
    print("步骤2：从缓存文件获取参考品种")
    print("=" * 70)
    
    try:
        from backend.core.base import get_service_manager
        
        service_manager = get_service_manager()
        data_center_service = service_manager.get_service("data_center_service")
        
        if not data_center_service:
            print("❌ data_center_service不可用")
            return None
            
        china_stock_engine = getattr(data_center_service, 'china_stock_engine', None)
        if not china_stock_engine:
            print("❌ china_stock_engine不可用")
            return None
            
        cache_manager = getattr(china_stock_engine, 'cache_manager', None)
        if not cache_manager:
            print("❌ cache_manager不可用")
            return None
            
        today = cache_manager.get_today()
        symbols_cache_file = cache_manager.root / f"symbols_{today}.json"
        
        print(f"📁 缓存文件路径: {symbols_cache_file}")
        
        if not symbols_cache_file.exists():
            print(f"❌ 缓存文件不存在")
            return None
            
        import json
        with open(symbols_cache_file, 'r', encoding='utf-8') as f:
            symbols_data = json.load(f)
            all_symbols = symbols_data.get('all_symbols', [])
            
            print(f"✅ 参考品种数: {len(all_symbols)}")
            
            # 提取symbol列表
            reference_symbols = set()
            for s in all_symbols:
                if isinstance(s, dict):
                    reference_symbols.add(s.get('symbol', ''))
                elif isinstance(s, str):
                    reference_symbols.add(s)
                    
            return reference_symbols
            
    except Exception as e:
        print(f"❌ 读取缓存文件失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def calculate_missing_symbols(reference_symbols, local_symbols):
    """计算缺失品种"""
    print("\n" + "=" * 70)
    print("步骤3：计算缺失品种")
    print("=" * 70)
    
    if not reference_symbols or not local_symbols:
        print("❌ 数据不完整，无法计算")
        return None
        
    local_symbols_set = set(local_symbols)
    missing_symbols_set = reference_symbols - local_symbols_set
    
    print(f"📊 统计结果:")
    print(f"  - 参考品种: {len(reference_symbols)}")
    print(f"  - 本地品种: {len(local_symbols_set)}")
    print(f"  - 缺失品种: {len(missing_symbols_set)}")
    
    if missing_symbols_set:
        print(f"\n🔍 缺失品种列表（前10个）:")
        for i, symbol in enumerate(sorted(missing_symbols_set)[:10], 1):
            print(f"  {i}. {symbol}")
            
    return missing_symbols_set

def main():
    """主诊断函数"""
    print("🔍 实时诊断：检查按钮状态和缺失品种数")
    print("=" * 70)
    
    # 步骤1：从数据库获取数据
    local_symbols, invalid_symbols = check_database_missing_count()
    
    # 步骤2：从缓存获取参考品种
    reference_symbols = check_reference_symbols()
    
    # 步骤3：计算缺失品种
    if local_symbols and reference_symbols:
        missing_symbols = calculate_missing_symbols(reference_symbols, local_symbols)
        
        print("\n" + "=" * 70)
        print("🎯 诊断结论")
        print("=" * 70)
        
        if missing_symbols:
            print(f"✅ 检测到 {len(missing_symbols)} 个缺失品种")
            print(f"✅ 按钮应该是蓝色（可点击）")
            print(f"\n💡 如果按钮还是绿色，说明UI状态更新逻辑有问题")
        else:
            print(f"✅ 没有缺失品种")
            print(f"✅ 按钮应该是绿色（禁用）")
            print(f"\n💡 这是正确的行为")
    else:
        print("\n❌ 诊断失败：数据不完整")
    
    print("=" * 70)

if __name__ == "__main__":
    main()
