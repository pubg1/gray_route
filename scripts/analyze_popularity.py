#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析popularity字段的分布情况
"""

import json

def analyze_popularity():
    data = []
    with open('case_recovery_phenomena.jsonl', 'r', encoding='utf-8') as f:
        for line in f:
            data.append(json.loads(line))
    
    # 按popularity排序
    sorted_data = sorted(data, key=lambda x: x['popularity'], reverse=True)
    
    print("=== Popularity 分析报告 ===")
    print(f"总记录数: {len(data)}")
    
    popularities = [item['popularity'] for item in data]
    print(f"Popularity 范围: {min(popularities)} - {max(popularities)}")
    print(f"平均值: {sum(popularities) / len(popularities):.1f}")
    
    print("\n最高popularity的5个:")
    for item in sorted_data[:5]:
        print(f"  ID: {item['id']}, Popularity: {item['popularity']}, System: {item['system']}")
        print(f"  Text: {item['text'][:60]}...")
        print()
    
    print("最低popularity的5个:")
    for item in sorted_data[-5:]:
        print(f"  ID: {item['id']}, Popularity: {item['popularity']}, System: {item['system']}")
        print(f"  Text: {item['text'][:60]}...")
        print()
    
    # 按系统统计平均popularity
    system_stats = {}
    for item in data:
        system = item['system']
        if system not in system_stats:
            system_stats[system] = []
        system_stats[system].append(item['popularity'])
    
    print("各系统平均popularity:")
    for system, pops in sorted(system_stats.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True):
        avg_pop = sum(pops) / len(pops)
        print(f"  {system}: {avg_pop:.1f} (共{len(pops)}条)")

if __name__ == "__main__":
    analyze_popularity()
