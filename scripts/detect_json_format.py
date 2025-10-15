#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检测JSON文件格式并提供修复建议
"""

import json
import os
import sys

def detect_json_format(file_path):
    """检测JSON文件格式"""
    print(f"🔍 检测文件格式: {file_path}")
    
    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # 读取前几行来判断格式
            first_line = f.readline().strip()
            f.seek(0)
            
            # 读取前1000个字符来分析
            sample = f.read(1000)
            f.seek(0)
            
            print(f"📄 文件大小: {os.path.getsize(file_path):,} 字节")
            print(f"🔤 前100个字符: {sample[:100]}...")
            
            # 判断格式
            if first_line.startswith('['):
                print("📋 格式: 标准JSON数组")
                try:
                    data = json.load(f)
                    print(f"✅ JSON解析成功，包含 {len(data)} 个元素")
                    return "json_array"
                except json.JSONDecodeError as e:
                    print(f"❌ JSON解析失败: {e}")
                    return False
                    
            elif first_line.startswith('{'):
                # 检查是否是JSONL格式
                f.seek(0)
                lines = f.readlines()
                
                if len(lines) > 1 and lines[1].strip().startswith('{'):
                    print("📋 格式: JSONL (每行一个JSON对象)")
                    
                    # 验证前几行
                    valid_lines = 0
                    for i, line in enumerate(lines[:5]):
                        line = line.strip()
                        if line:
                            try:
                                json.loads(line)
                                valid_lines += 1
                            except json.JSONDecodeError:
                                print(f"⚠️  第 {i+1} 行格式错误")
                    
                    print(f"✅ 验证了前5行，{valid_lines}/5 行有效")
                    print(f"📊 总行数: {len(lines)}")
                    return "jsonl"
                else:
                    print("📋 格式: 单个JSON对象")
                    try:
                        f.seek(0)
                        data = json.load(f)
                        print("✅ JSON解析成功")
                        return "json_object"
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON解析失败: {e}")
                        return False
            else:
                print("❌ 无法识别的文件格式")
                return False
                
    except Exception as e:
        print(f"❌ 文件读取失败: {e}")
        return False

def convert_to_json_array(input_file, output_file=None):
    """将JSONL格式转换为JSON数组格式"""
    if output_file is None:
        base, ext = os.path.splitext(input_file)
        output_file = f"{base}_array{ext}"
    
    print(f"🔄 转换 JSONL 到 JSON 数组...")
    print(f"   输入: {input_file}")
    print(f"   输出: {output_file}")
    
    try:
        data = []
        with open(input_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        data.append(record)
                    except json.JSONDecodeError as e:
                        print(f"⚠️  第 {line_num} 行跳过: {e}")
        
        print(f"📊 成功解析 {len(data)} 条记录")
        
        # 写入JSON数组
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 转换完成: {output_file}")
        print(f"📄 输出文件大小: {os.path.getsize(output_file):,} 字节")
        
        return output_file
        
    except Exception as e:
        print(f"❌ 转换失败: {e}")
        return None

def main():
    """主函数"""
    print("🔍 JSON 文件格式检测工具")
    print("=" * 50)
    
    # 检查数据文件
    data_file = "../data/servicingcase_last.json"
    
    if len(sys.argv) > 1:
        data_file = sys.argv[1]
    
    format_type = detect_json_format(data_file)
    
    if format_type == "jsonl":
        print("\n💡 建议:")
        print("   文件是JSONL格式，导入脚本已支持此格式")
        print("   可以直接运行导入，或者转换为标准JSON数组")
        
        choice = input("\n是否转换为JSON数组格式？(y/N): ").strip().lower()
        if choice == 'y':
            output_file = convert_to_json_array(data_file)
            if output_file:
                print(f"\n✅ 转换完成!")
                print(f"💡 现在可以使用转换后的文件进行导入:")
                print(f"   python import_to_opensearch_preserve_fields.py")
                
    elif format_type == "json_array":
        print("\n✅ 文件格式正确，可以直接导入")
        
    elif format_type == "json_object":
        print("\n⚠️  文件是单个JSON对象，需要转换为数组格式")
        
    else:
        print("\n❌ 文件格式有问题，请检查文件内容")
        
        # 显示文件开头内容
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                content = f.read(500)
                print(f"\n📄 文件开头内容:")
                print("-" * 40)
                print(content)
                print("-" * 40)
        except:
            pass

if __name__ == "__main__":
    main()
