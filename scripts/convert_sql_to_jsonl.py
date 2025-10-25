#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将case_recovery.sql文件转换为phenomena_sample.jsonl格式的脚本
symptoms字段 -> 故障现象
discussion字段 -> 故障点
"""

import re
import json
import html
from typing import List, Dict, Optional

def clean_html_content(content: str) -> str:
    """清理HTML内容，提取纯文本"""
    if not content:
        return ""
    
    # 移除HTML标签
    content = re.sub(r'<[^>]+>', '', content)
    # 解码HTML实体
    content = html.unescape(content)
    # 移除多余的空白字符
    content = re.sub(r'\s+', ' ', content).strip()
    
    return content

def extract_insert_values(sql_content: str) -> List[tuple]:
    """从SQL INSERT语句中提取值"""
    values = []
    
    # 匹配INSERT INTO语句
    insert_pattern = r"INSERT INTO `case_recovery` VALUES \((.*?)\);"
    matches = re.findall(insert_pattern, sql_content, re.DOTALL)
    
    for match in matches:
        # 解析VALUES中的字段
        # 这里需要处理复杂的SQL值解析，包括转义字符和NULL值
        try:
            # 简单的字段分割（可能需要更复杂的解析）
            fields = parse_sql_values(match)
            values.append(fields)
        except Exception as e:
            print(f"解析INSERT语句时出错: {e}")
            continue
    
    return values

def parse_sql_values(values_str: str) -> List[str]:
    """解析SQL VALUES字符串"""
    fields = []
    current_field = ""
    in_quotes = False
    quote_char = None
    i = 0
    
    while i < len(values_str):
        char = values_str[i]
        
        if not in_quotes:
            if char in ("'", '"'):
                in_quotes = True
                quote_char = char
                current_field += char
            elif char == ',' and not in_quotes:
                fields.append(current_field.strip())
                current_field = ""
            else:
                current_field += char
        else:
            if char == quote_char:
                # 检查是否是转义的引号
                if i + 1 < len(values_str) and values_str[i + 1] == quote_char:
                    current_field += char + char
                    i += 1  # 跳过下一个引号
                else:
                    in_quotes = False
                    quote_char = None
                    current_field += char
            else:
                current_field += char
        
        i += 1
    
    # 添加最后一个字段
    if current_field.strip():
        fields.append(current_field.strip())
    
    return fields

def extract_system_from_discussion(discussion: str) -> str:
    """从故障点描述中提取系统信息"""
    # 常见汽车系统关键词
    systems = {
        "发动机": ["发动机", "引擎", "ECM", "ECU", "点火", "燃油", "进气", "排气", "冷却", "润滑"],
        "制动": ["制动", "刹车", "ABS", "ESP", "制动器", "制动盘", "制动片"],
        "变速箱/传动": ["变速箱", "变速器", "离合器", "传动", "CVT", "差速器", "传动轴"],
        "底盘/悬挂": ["悬挂", "减震", "弹簧", "控制臂", "稳定杆", "底盘", "副车架"],
        "转向": ["转向", "方向盘", "助力", "转向机", "转向拉杆"],
        "空调": ["空调", "制冷", "压缩机", "冷凝器", "蒸发器", "鼓风机"],
        "电子电气": ["电瓶", "电池", "线束", "插头", "传感器", "模块", "控制器", "MCU"],
        "车身": ["车门", "车窗", "大灯", "尾灯", "雨刮", "后视镜"]
    }
    
    discussion_lower = discussion.lower()
    for system, keywords in systems.items():
        for keyword in keywords:
            if keyword.lower() in discussion_lower:
                return system
    
    return "其他"

def extract_part_from_discussion(discussion: str) -> Optional[str]:
    """从故障点描述中提取具体部件信息"""
    # 提取前30个字符作为部件描述，去除HTML和多余空格
    part = discussion[:30].strip()
    if len(discussion) > 30:
        part += "..."
    return part

def calculate_popularity(symptoms: str, discussion: str, brand: str, system: str) -> int:
    """基于故障特征计算流行度分数"""
    base_score = 100
    content = (symptoms + " " + discussion).lower()
    
    # 品牌影响因子（基于市场占有率和普及度）
    brand_factors = {
        "大众": 1.3, "丰田": 1.3, "本田": 1.2, "日产": 1.2, "现代": 1.2,
        "比亚迪": 1.4, "吉利": 1.3, "长安": 1.2, "奇瑞": 1.1, "长城": 1.1,
        "奔驰": 1.1, "宝马": 1.1, "奥迪": 1.2, "福特": 1.2, "别克": 1.1,
        "雪佛兰": 1.1, "起亚": 1.1, "马自达": 1.0, "三菱": 1.0, "斯巴鲁": 0.9,
        "保时捷": 0.8, "法拉利": 0.7, "兰博基尼": 0.6, "劳斯莱斯": 0.6
    }
    brand_factor = brand_factors.get(brand, 1.0)
    
    # 系统影响因子（基于故障频率）
    system_factors = {
        "发动机": 1.5,      # 发动机故障最常见
        "电子电气": 1.4,    # 电子系统故障频发
        "变速箱/传动": 1.3, # 传动系统故障较多
        "制动": 1.2,        # 制动系统安全相关
        "空调": 1.1,        # 空调故障较常见
        "转向": 1.1,        # 转向系统重要
        "底盘/悬挂": 1.0,   # 底盘故障中等
        "车身": 0.9,        # 车身故障相对较少
        "其他": 0.8
    }
    system_factor = system_factors.get(system, 1.0)
    
    # 故障严重程度因子
    severity_factor = 1.0
    if any(word in content for word in ["无法启动", "不能启动", "打不着火"]):
        severity_factor = 1.6  # 启动故障严重
    elif any(word in content for word in ["失去动力", "动力中断", "突然熄火"]):
        severity_factor = 1.5  # 动力故障严重
    elif any(word in content for word in ["制动失效", "刹车失灵", "制动距离长"]):
        severity_factor = 1.4  # 制动故障安全相关
    elif any(word in content for word in ["故障灯", "报警", "警告灯"]):
        severity_factor = 1.3  # 故障灯提示问题
    elif any(word in content for word in ["异响", "噪音", "声音异常"]):
        severity_factor = 1.2  # 异响问题常见
    elif any(word in content for word in ["抖动", "震动", "颤抖"]):
        severity_factor = 1.2  # 抖动问题影响驾驶
    elif any(word in content for word in ["漏油", "渗油", "油液泄漏"]):
        severity_factor = 1.1  # 漏油问题需要关注
    
    # 故障频率因子（基于关键词出现频率）
    frequency_factor = 1.0
    if any(word in content for word in ["偶发", "间歇", "偶尔"]):
        frequency_factor = 0.8  # 偶发故障相对少见
    elif any(word in content for word in ["持续", "一直", "经常"]):
        frequency_factor = 1.3  # 持续故障更常见
    elif any(word in content for word in ["冷车", "热车"]):
        frequency_factor = 1.1  # 温度相关故障较常见
    
    # 计算最终流行度
    popularity = int(base_score * brand_factor * system_factor * severity_factor * frequency_factor)
    
    # 添加随机扰动，避免完全相同的分数
    import random
    random.seed(hash(symptoms + discussion) % 2147483647)  # 基于内容的固定种子
    popularity += random.randint(-10, 10)
    
    # 确保在合理范围内
    return max(50, min(500, popularity))

def generate_tags_from_content(symptoms: str, discussion: str, brand: str) -> List[str]:
    """根据内容生成标签"""
    tags = []
    
    # 添加品牌标签
    if brand:
        tags.append(brand)
    
    # 根据症状和讨论内容生成标签
    content = (symptoms + " " + discussion).lower()
    
    # 故障类型标签
    if any(word in content for word in ["无法启动", "启动困难", "打不着火"]):
        tags.append("启动故障")
    if any(word in content for word in ["异响", "噪音", "声音"]):
        tags.append("异响")
    if any(word in content for word in ["漏油", "渗油", "油液"]):
        tags.append("漏油")
    if any(word in content for word in ["故障灯", "报警", "警告灯"]):
        tags.append("故障灯")
    if any(word in content for word in ["抖动", "震动", "颤抖"]):
        tags.append("抖动")
    if any(word in content for word in ["无力", "动力不足", "加速慢"]):
        tags.append("动力不足")
    if any(word in content for word in ["过热", "高温", "温度高"]):
        tags.append("过热")
    if any(word in content for word in ["漏电", "短路", "断路"]):
        tags.append("电路故障")
    
    # 确保至少有基本标签
    if not tags:
        tags.append("故障诊断")
    
    tags.append("维修案例")
    
    return tags[:5]  # 限制标签数量

def clean_sql_value(value: str) -> Optional[str]:
    """清理SQL值，移除引号并处理NULL"""
    if not value or value.strip().upper() == 'NULL':
        return None
    
    value = value.strip()
    if value.startswith("'") and value.endswith("'"):
        value = value[1:-1]
        # 处理转义的单引号
        value = value.replace("''", "'")
        value = value.replace("\\'", "'")
    
    return value

def convert_sql_to_jsonl(sql_file_path: str, output_file_path: str):
    """将SQL文件转换为JSONL格式"""
    
    print(f"正在读取SQL文件: {sql_file_path}")
    
    try:
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
    except UnicodeDecodeError:
        # 尝试其他编码
        with open(sql_file_path, 'r', encoding='gbk') as f:
            sql_content = f.read()
    
    print("正在解析INSERT语句...")
    
    # 使用正则表达式匹配完整的INSERT语句（可能跨多行）
    jsonl_data = []
    record_id = 1
    
    # 匹配INSERT语句，包括跨行的情况
    insert_pattern = r"INSERT INTO `case_recovery` VALUES \((.*?)\);"
    matches = re.findall(insert_pattern, sql_content, re.DOTALL)
    
    print(f"找到 {len(matches)} 条INSERT语句")
    
    for match_num, values_part in enumerate(matches, 1):
        try:
            # 解析字段值
            fields = parse_sql_values_advanced(values_part)
            
            if len(fields) >= 13:  # 确保有足够的字段（至少到discussion字段）
                # 根据CREATE TABLE语句，字段顺序为：
                # 0:id, 1:creatorid, 2:vehicletype, 3:rate, 4:vin, 5:egon, 6:vehiclebrand, 
                # 7:topic, 8:symptoms, 9:search, 10:solution, 11:summary, 12:discussion, ...
                
                symptoms = clean_sql_value(fields[8]) if len(fields) > 8 else None
                discussion = clean_sql_value(fields[12]) if len(fields) > 12 else None
                vehiclebrand = clean_sql_value(fields[6]) if len(fields) > 6 else None
                vehicletype = clean_sql_value(fields[2]) if len(fields) > 2 else None
                topic = clean_sql_value(fields[7]) if len(fields) > 7 else None
                
                if symptoms and discussion:
                    # 清理HTML内容
                    symptoms_clean = clean_html_content(symptoms)
                    discussion_clean = clean_html_content(discussion)
                    
                    if symptoms_clean and discussion_clean and len(symptoms_clean) > 5:
                        # 从discussion中提取系统信息（通常在开头）
                        system_info = extract_system_from_discussion(discussion_clean)
                        part_info = extract_part_from_discussion(discussion_clean)
                        tags_info = generate_tags_from_content(symptoms_clean, discussion_clean, vehiclebrand)
                        popularity_score = calculate_popularity(symptoms_clean, discussion_clean, vehiclebrand or "", system_info)
                        
                        # 创建JSONL记录，格式参考phenomena_sample.jsonl
                        record = {
                            "id": f"C{record_id:04d}",
                            "text": symptoms_clean,  # 故障现象
                            "system": system_info,  # 故障系统
                            "part": part_info or vehicletype or "未知部件",  # 故障部件
                            "tags": tags_info,
                            "popularity": popularity_score  # 基于特征的流行度计算
                        }
                        
                        jsonl_data.append(record)
                        record_id += 1
                        
                        if record_id % 100 == 0:
                            print(f"已处理 {record_id-1} 条记录...")
            
        except Exception as e:
            print(f"处理第 {match_num} 条INSERT语句时出错: {e}")
            continue
    
    print(f"共提取到 {len(jsonl_data)} 条有效记录")
    
    # 写入JSONL文件
    print(f"正在写入JSONL文件: {output_file_path}")
    with open(output_file_path, 'w', encoding='utf-8') as f:
        for record in jsonl_data:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    print(f"转换完成！生成了 {len(jsonl_data)} 条记录")

def parse_sql_values_advanced(values_str: str) -> List[str]:
    """高级SQL值解析，处理复杂的嵌套引号和转义"""
    fields = []
    current_field = ""
    in_quotes = False
    quote_char = None
    paren_count = 0
    
    i = 0
    while i < len(values_str):
        char = values_str[i]
        
        if char == '(' and not in_quotes:
            paren_count += 1
            current_field += char
        elif char == ')' and not in_quotes:
            paren_count -= 1
            current_field += char
        elif not in_quotes and char in ("'", '"'):
            in_quotes = True
            quote_char = char
            current_field += char
        elif in_quotes and char == quote_char:
            # 检查转义
            if i + 1 < len(values_str) and values_str[i + 1] == quote_char:
                current_field += char + char
                i += 1
            else:
                in_quotes = False
                quote_char = None
                current_field += char
        elif char == ',' and not in_quotes and paren_count == 0:
            fields.append(current_field.strip())
            current_field = ""
        else:
            current_field += char
        
        i += 1
    
    if current_field.strip():
        fields.append(current_field.strip())
    
    return fields

def parse_sql_values_simple(values_str: str) -> List[str]:
    """简化的SQL值解析"""
    fields = []
    current_field = ""
    in_quotes = False
    quote_char = None
    paren_count = 0
    
    i = 0
    while i < len(values_str):
        char = values_str[i]
        
        if char == '(' and not in_quotes:
            paren_count += 1
            current_field += char
        elif char == ')' and not in_quotes:
            paren_count -= 1
            current_field += char
        elif not in_quotes and char in ("'", '"'):
            in_quotes = True
            quote_char = char
            current_field += char
        elif in_quotes and char == quote_char:
            # 检查转义
            if i + 1 < len(values_str) and values_str[i + 1] == quote_char:
                current_field += char + char
                i += 1
            else:
                in_quotes = False
                quote_char = None
                current_field += char
        elif char == ',' and not in_quotes and paren_count == 0:
            fields.append(current_field.strip())
            current_field = ""
        else:
            current_field += char
        
        i += 1
    
    if current_field.strip():
        fields.append(current_field.strip())
    
    return fields

if __name__ == "__main__":
    sql_file = "case_recovery.sql"
    output_file = "case_recovery_phenomena.jsonl"
    
    convert_sql_to_jsonl(sql_file, output_file)
