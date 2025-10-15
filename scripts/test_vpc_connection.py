#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AWS OpenSearch VPC 端点连接测试脚本
"""

import sys
import ssl
import socket
from opensearchpy import OpenSearch
from opensearch_config import OPENSEARCH_CONFIG
import requests
from urllib3.exceptions import InsecureRequestWarning
import urllib3

# 禁用 SSL 警告（仅用于测试）
urllib3.disable_warnings(InsecureRequestWarning)

def test_dns_resolution():
    """测试 DNS 解析"""
    host = OPENSEARCH_CONFIG['host']
    print(f"🔍 测试 DNS 解析: {host}")
    
    try:
        ip = socket.gethostbyname(host)
        print(f"✅ DNS 解析成功: {host} -> {ip}")
        return True
    except socket.gaierror as e:
        print(f"❌ DNS 解析失败: {e}")
        print("💡 提示: 请确保你在 VPC 内部或配置了正确的 DNS")
        return False

def test_port_connectivity():
    """测试端口连接"""
    host = OPENSEARCH_CONFIG['host']
    port = OPENSEARCH_CONFIG['port']
    
    print(f"🔍 测试端口连接: {host}:{port}")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print(f"✅ 端口 {port} 连接成功")
            return True
        else:
            print(f"❌ 端口 {port} 连接失败")
            return False
    except Exception as e:
        print(f"❌ 端口连接测试异常: {e}")
        return False

def test_ssl_certificate():
    """测试 SSL 证书"""
    host = OPENSEARCH_CONFIG['host']
    port = OPENSEARCH_CONFIG['port']
    
    print(f"🔍 测试 SSL 证书: {host}:{port}")
    
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                print(f"✅ SSL 证书有效")
                print(f"   颁发给: {cert.get('subject', [{}])[0].get('commonName', 'N/A')}")
                print(f"   颁发者: {cert.get('issuer', [{}])[-1].get('commonName', 'N/A')}")
                return True
    except ssl.SSLError as e:
        print(f"⚠️  SSL 证书问题: {e}")
        print("💡 提示: 可能需要设置 verify_certs=False")
        return False
    except Exception as e:
        print(f"❌ SSL 测试异常: {e}")
        return False

def test_http_request():
    """测试 HTTP 请求"""
    host = OPENSEARCH_CONFIG['host']
    port = OPENSEARCH_CONFIG['port']
    username = OPENSEARCH_CONFIG['username']
    password = OPENSEARCH_CONFIG['password']
    
    print(f"🔍 测试 HTTP 请求")
    
    # 构建 URL
    protocol = 'https' if OPENSEARCH_CONFIG['use_ssl'] else 'http'
    url = f"{protocol}://{host}:{port}"
    
    try:
        # 测试基本连接
        response = requests.get(
            url,
            auth=(username, password) if username and password else None,
            verify=OPENSEARCH_CONFIG['verify_certs'],
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ HTTP 请求成功")
            print(f"   集群名称: {data.get('cluster_name', 'N/A')}")
            print(f"   版本: {data.get('version', {}).get('number', 'N/A')}")
            return True
        else:
            print(f"❌ HTTP 请求失败: {response.status_code}")
            print(f"   响应: {response.text[:200]}...")
            return False
            
    except requests.exceptions.SSLError as e:
        print(f"❌ SSL 错误: {e}")
        print("💡 提示: 尝试设置 verify_certs=False")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"❌ 连接错误: {e}")
        return False
    except requests.exceptions.Timeout as e:
        print(f"❌ 请求超时: {e}")
        return False
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return False

def test_opensearch_client():
    """测试 OpenSearch 客户端连接"""
    print(f"🔍 测试 OpenSearch 客户端")
    
    try:
        # 创建客户端
        client = OpenSearch(
            hosts=[{
                'host': OPENSEARCH_CONFIG['host'],
                'port': OPENSEARCH_CONFIG['port']
            }],
            http_auth=(OPENSEARCH_CONFIG['username'], OPENSEARCH_CONFIG['password']),
            use_ssl=OPENSEARCH_CONFIG['use_ssl'],
            verify_certs=OPENSEARCH_CONFIG['verify_certs'],
            ssl_assert_hostname=OPENSEARCH_CONFIG.get('ssl_assert_hostname', False),
            ssl_show_warn=OPENSEARCH_CONFIG.get('ssl_show_warn', False),
            timeout=OPENSEARCH_CONFIG.get('timeout', 30)
        )
        
        # 测试连接
        info = client.info()
        print(f"✅ OpenSearch 客户端连接成功")
        print(f"   集群名称: {info.get('cluster_name', 'N/A')}")
        print(f"   版本: {info.get('version', {}).get('number', 'N/A')}")
        
        # 测试集群健康状态
        health = client.cluster.health()
        print(f"   集群状态: {health.get('status', 'N/A')}")
        print(f"   节点数: {health.get('number_of_nodes', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ OpenSearch 客户端连接失败: {e}")
        return False

def test_network_connectivity():
    """测试网络连通性"""
    print(f"🔍 测试网络连通性")
    
    # 测试到 AWS 的连接
    test_hosts = [
        'aws.amazon.com',
        's3.amazonaws.com',
        'ec2.us-east-1.amazonaws.com'
    ]
    
    success_count = 0
    for test_host in test_hosts:
        try:
            socket.gethostbyname(test_host)
            print(f"   ✅ {test_host}")
            success_count += 1
        except:
            print(f"   ❌ {test_host}")
    
    if success_count > 0:
        print(f"✅ 网络连通性正常 ({success_count}/{len(test_hosts)})")
        return True
    else:
        print(f"❌ 网络连通性异常")
        return False

def main():
    """主函数"""
    print("🧪 AWS OpenSearch VPC 端点连接测试")
    print("=" * 60)
    
    print(f"📋 连接配置:")
    print(f"   主机: {OPENSEARCH_CONFIG['host']}")
    print(f"   端口: {OPENSEARCH_CONFIG['port']}")
    print(f"   SSL: {OPENSEARCH_CONFIG['use_ssl']}")
    print(f"   验证证书: {OPENSEARCH_CONFIG['verify_certs']}")
    print(f"   用户名: {OPENSEARCH_CONFIG['username']}")
    print()
    
    # 执行测试
    tests = [
        ("网络连通性", test_network_connectivity),
        ("DNS 解析", test_dns_resolution),
        ("端口连接", test_port_connectivity),
        ("SSL 证书", test_ssl_certificate),
        ("HTTP 请求", test_http_request),
        ("OpenSearch 客户端", test_opensearch_client),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            results.append((test_name, False))
    
    # 汇总结果
    print(f"\n{'='*60}")
    print(f"📊 测试结果汇总:")
    print(f"{'='*60}")
    
    success_count = 0
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name}: {status}")
        if result:
            success_count += 1
    
    total_tests = len(results)
    pass_rate = success_count / total_tests if total_tests > 0 else 0
    
    print(f"\n🎯 总体结果: {success_count}/{total_tests} 通过 ({pass_rate:.1%})")
    
    if pass_rate >= 0.8:
        print("🎉 连接测试基本通过，可以尝试导入数据!")
    elif pass_rate >= 0.5:
        print("⚠️  部分测试失败，可能需要调整配置")
    else:
        print("❌ 连接测试失败，请检查网络和配置")
    
    # 提供建议
    print(f"\n💡 故障排查建议:")
    if not results[0][1]:  # 网络连通性失败
        print("   - 检查网络连接和防火墙设置")
    if not results[1][1]:  # DNS 解析失败
        print("   - 确保在 VPC 内部或配置了正确的 DNS")
        print("   - 检查 VPC 端点的访问策略")
    if not results[2][1]:  # 端口连接失败
        print("   - 检查安全组是否允许 443 端口")
        print("   - 确认 VPC 端点状态正常")
    if not results[3][1]:  # SSL 证书问题
        print("   - 尝试设置 verify_certs=False")
    if not results[4][1]:  # HTTP 请求失败
        print("   - 检查用户名密码是否正确")
        print("   - 确认访问策略允许当前 IP")
    
    return pass_rate >= 0.5

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 用户中断测试")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试过程出错: {e}")
        sys.exit(1)
