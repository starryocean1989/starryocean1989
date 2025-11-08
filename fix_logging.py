def fix_logging():
    file_path = r'c:/Users/USER/Desktop/terminal_v0.50/ui/modules/system_manager_view.py'
    
    # Read the file content
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Define the old and new content
    old_content = """            # 强制输出确认
            self.logger.info(
                "[SystemManager] ✅ DEBUG日志文件已创建: %s",
                log_file.absolute(),
                extra={"log_type": "SYSTEM"},
            )
            self.logger.info(f"✅ DEBUG日志已启用: {log_file}")"""
    
    new_content = """            # 使用统一日志系统
            self.logger.info(
                "[SystemManager] ✅ DEBUG日志已启用（由LoggingHub统一管理）",
                extra={"log_type": "SYSTEM"},
            )"""
    
    # Replace the content
    if old_content in content:
        new_content_full = content.replace(old_content, new_content)
        
        # Write the updated content back to the file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content_full)
        print("Logging configuration updated successfully!")
    else:
        print("The target content was not found in the file. The file may have been modified.")
        print("Expected content to replace:")
        print("-" * 50)
        print(old_content)
        print("-" * 50)
        print("Current content at that location:")
        print("-" * 50)
        # Print the relevant section for debugging
        start_idx = content.find("# 强制输出确认")
        if start_idx != -1:
            end_idx = content.find("except Exception as e:", start_idx)
            if end_idx != -1:
                print(content[start_idx:end_idx].strip())
            else:
                print("Could not find the end of the target section.")
        else:
            print("Could not find the target section in the file.")

if __name__ == "__main__":
    fix_logging()
