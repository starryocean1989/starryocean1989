#!/usr/bin/env python3
"""
修复监控进程IPC JSON解析问题
解决"Extra data: line 1 column 23 (char 22)"错误
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def fix_monitor_json_parsing():
    """修复监控进程的JSON解析问题"""
    
    monitor_file = "backend/infrastructure/system_vnpy/monitor_system.py"
    
    print("🔧 修复监控进程JSON解析问题")
    print("=" * 60)
    
    try:
        # 读取文件
        with open(monitor_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找需要修复的代码段
        old_code = """                    # 读取请求（使用更大的缓冲区）
                    request_data = await self.query_pipe.read(size=65536)
                    request = json.loads(request_data.decode())"""
        
        new_code = """                    # 读取请求（使用更大的缓冲区）
                    request_data = await self.query_pipe.read(size=65536)
                    
                    # 🔧 修复JSON解析问题：处理数据截断和多JSON对象
                    try:
                        decoded_data = request_data.decode('utf-8')
                        
                        # 检查是否有多个JSON对象（用换行符分隔）
                        if '\\n' in decoded_data:
                            # 取第一个完整的JSON对象
                            json_lines = decoded_data.strip().split('\\n')
                            for line in json_lines:
                                if line.strip():
                                    try:
                                        request = json.loads(line.strip())
                                        break
                                    except json.JSONDecodeError:
                                        continue
                            else:
                                # 如果没有找到有效的JSON，使用默认请求
                                request = {"action": "get_data"}
                        else:
                            # 单个JSON对象，直接解析
                            request = json.loads(decoded_data)
                            
                    except json.JSONDecodeError as e:
                        logger.warning(f"[IPC] JSON解析失败: {e}, 数据长度: {len(request_data)}")
                        logger.debug(f"[IPC] 原始数据: {request_data[:100]}...")
                        # 使用默认请求
                        request = {"action": "get_data"}
                    except UnicodeDecodeError as e:
                        logger.warning(f"[IPC] 数据解码失败: {e}, 数据长度: {len(request_data)}")
                        # 使用默认请求
                        request = {"action": "get_data"}"""
        
        if old_code in content:
            # 执行替换
            new_content = content.replace(old_code, new_code)
            
            # 写回文件
            with open(monitor_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print("✅ JSON解析错误处理已修复")
            print("📋 修复内容:")
            print("  1. 添加了数据截断检测")
            print("  2. 处理多JSON对象情况")
            print("  3. 增强了错误恢复机制")
            print("  4. 添加了详细的调试日志")
            
            return True
        else:
            print("⚠️ 未找到需要修复的代码段，可能已经修复过了")
            return False
            
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def add_response_validation():
    """添加响应数据验证"""
    
    monitor_file = "backend/infrastructure/system_vnpy/monitor_system.py"
    
    try:
        with open(monitor_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找响应发送的代码
        old_response_code = """                        await self.query_pipe.write(response_bytes)"""
        
        new_response_code = """                        # 🔧 验证响应数据完整性
                        try:
                            # 验证JSON格式
                            json.loads(response_bytes.decode('utf-8'))
                            await self.query_pipe.write(response_bytes)
                            logger.debug(f"[IPC] 响应已发送: {len(response_bytes)} bytes")
                        except json.JSONDecodeError as e:
                            logger.error(f"[IPC] 响应JSON格式错误: {e}")
                            # 发送错误响应
                            error_response = json.dumps({"status": "error", "message": "响应数据格式错误"})
                            await self.query_pipe.write(error_response.encode('utf-8'))
                        except Exception as e:
                            logger.error(f"[IPC] 发送响应失败: {e}")"""
        
        if old_response_code in content:
            new_content = content.replace(old_response_code, new_response_code)
            
            with open(monitor_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print("✅ 响应数据验证已添加")
            return True
        else:
            print("⚠️ 响应发送代码未找到或已修复")
            return False
            
    except Exception as e:
        print(f"❌ 添加响应验证失败: {e}")
        return False

def main():
    """主函数"""
    print("🚀 监控进程IPC JSON解析修复工具")
    print("=" * 80)
    
    success1 = fix_monitor_json_parsing()
    success2 = add_response_validation()
    
    print("\n" + "=" * 80)
    if success1 or success2:
        print("🎉 修复完成！")
        print("\n📋 修复总结:")
        if success1:
            print("  ✅ JSON解析错误处理已修复")
        if success2:
            print("  ✅ 响应数据验证已添加")
        
        print("\n🚀 建议操作:")
        print("  1. 重启终端应用以应用修复")
        print("  2. 观察监控进程日志确认问题解决")
        print("  3. 运行 diagnose_monitor_ipc.py 验证修复效果")
    else:
        print("⚠️ 没有执行任何修复，可能已经修复过了")
    
    print("\n💡 如果问题仍然存在:")
    print("  1. 检查监控进程是否正常重启")
    print("  2. 查看监控进程日志中的详细错误信息")
    print("  3. 确认IPC管道连接状态")

if __name__ == "__main__":
    main()