"""
直接打印spblock.dat中的所有板块名称（使用print确保输出）
"""

from pathlib import Path

def find_spblock():
    """查找spblock.dat文件"""
    search_dirs = [
        Path("C:/new_tdx"),
        Path("C:/通达信金融终端V7"),
        Path("C:/Program Files/通达信金融终端V7"),
        Path("D:/通达信金融终端V7"),
        Path("C:/tdx"),
        Path("D:/tdx"),
    ]
    
    for root_dir in search_dirs:
        if root_dir.exists():
            print(f"搜索目录: {root_dir}")
            for spblock_file in root_dir.rglob("spblock.dat"):
                if spblock_file.is_file():
                    print(f"✓ 找到spblock.dat: {spblock_file}")
                    return spblock_file
    
    print("❌ 未找到spblock.dat文件")
    return None


def parse_and_show_blocks():
    """解析并显示所有板块"""
    spblock_path = find_spblock()
    
    if not spblock_path:
        return
    
    print("\n" + "=" * 80)
    print("开始解析spblock.dat文件")
    print("=" * 80)
    
    try:
        # 使用GBK编码读取
        with open(spblock_path, 'r', encoding='gbk', errors='ignore') as f:
            lines = f.readlines()
        
        print(f"\n文件共有 {len(lines)} 行")
        
        # 收集所有板块名称
        blocks = []
        block_stocks = {}  # 板块 -> 品种列表
        current_block = ""
        
        for line in lines:
            line = line.strip()
            
            if not line:
                continue
            
            # 板块名称行（以#开头）
            if line.startswith("#"):
                block_name = line[1:].strip()
                blocks.append(block_name)
                current_block = block_name
                block_stocks[current_block] = []
            
            # 股票代码行
            elif line.isdigit() and len(line) >= 6:
                if current_block:
                    block_stocks[current_block].append(line)
        
        print(f"\n共找到 {len(blocks)} 个板块")
        print("\n" + "=" * 80)
        print("所有板块名称列表：")
        print("=" * 80)
        
        # 打印所有板块及品种数
        for i, block_name in enumerate(sorted(blocks), 1):
            stock_count = len(block_stocks.get(block_name, []))
            print(f"{i:3d}. {block_name} ({stock_count}个品种)")
        
        print("\n" + "=" * 80)
        print("关键板块检查：")
        print("=" * 80)
        
        # 检查关键板块
        keywords = ["T+0", "基金", "可转债", "融资融券", "北证"]
        
        for keyword in keywords:
            print(f"\n包含 '{keyword}' 的板块：")
            matched = [b for b in blocks if keyword in b]
            if matched:
                for m in matched:
                    count = len(block_stocks.get(m, []))
                    print(f"  ✓ {m} ({count}个品种)")
            else:
                print(f"  ✗ 未找到")
        
        print("\n" + "=" * 80)
        
    except Exception as e:
        print(f"❌ 解析失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    parse_and_show_blocks()
