# -*- coding: utf-8 -*-
"""
分析data_fetcher.py中的所有类和方法
"""
import ast
from pathlib import Path


def analyze_data_fetcher():
    """分析data_fetcher.py的结构"""
    
    file_path = Path(__file__).parent.parent / "backend" / "infrastructure" / "data_module_vnpy" / "data_fetcher.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    tree = ast.parse(content)
    
    # 收集类和方法
    classes_info = {}
    module_functions = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # 收集类的方法
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    # 获取方法的行号和参数
                    params = [arg.arg for arg in item.args.args]
                    methods.append({
                        'name': item.name,
                        'line': item.lineno,
                        'params': params,
                        'is_static': any(isinstance(d, ast.Name) and d.id == 'staticmethod' 
                                       for d in item.decorator_list),
                        'is_property': any(isinstance(d, ast.Name) and d.id == 'property' 
                                         for d in item.decorator_list),
                    })
            
            classes_info[node.name] = {
                'line': node.lineno,
                'methods': methods
            }
    
    # 收集模块级函数（不在类内部的函数）
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            params = [arg.arg for arg in node.args.args]
            module_functions.append({
                'name': node.name,
                'line': node.lineno,
                'params': params
            })
    
    # 输出结果
    print("\n" + "="*70)
    print("data_fetcher.py 结构分析")
    print("="*70)
    
    # 输出类及其方法
    print(f"\n📦 类定义 (共 {len(classes_info)} 个):")
    print("="*70)
    
    for class_name, info in classes_info.items():
        print(f"\n类: {class_name} (第 {info['line']} 行)")
        print("-" * 70)
        
        if info['methods']:
            print(f"  方法数: {len(info['methods'])}")
            for method in info['methods']:
                decorator = ""
                if method['is_static']:
                    decorator = "@staticmethod "
                elif method['is_property']:
                    decorator = "@property "
                
                params_str = ', '.join(method['params'])
                print(f"    {decorator}{method['name']}({params_str}) - 第{method['line']}行")
        else:
            print(f"  (无方法)")
    
    # 输出模块级函数
    print(f"\n" + "="*70)
    print(f"🔧 模块级函数 (共 {len(module_functions)} 个):")
    print("="*70)
    
    for func in module_functions:
        params_str = ', '.join(func['params'])
        print(f"  {func['name']}({params_str}) - 第{func['line']}行")
    
    # 统计
    total_methods = sum(len(info['methods']) for info in classes_info.values())
    total_functions = len(module_functions)
    
    print(f"\n" + "="*70)
    print("📊 统计")
    print("="*70)
    print(f"  类: {len(classes_info)}")
    print(f"  类方法: {total_methods}")
    print(f"  模块级函数: {total_functions}")
    print(f"  总计: {total_methods + total_functions} 个方法/函数")
    print("="*70)


if __name__ == "__main__":
    analyze_data_fetcher()

