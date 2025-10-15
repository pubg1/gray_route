#!/bin/bash
# 设置 SSH 隧道连接 VPC 端点

# 配置变量
EC2_HOST="your-ec2-public-ip"
EC2_USER="ubuntu"
KEY_FILE="your-key.pem"
VPC_ENDPOINT="vpc-carbobo-hty6sxiqn2a5x4dbbiqjtj5reu.us-east-1.es.amazonaws.com"
LOCAL_PORT="9200"

echo "🔗 设置 SSH 隧道到 OpenSearch VPC 端点"
echo "========================================="
echo "本地端口: $LOCAL_PORT"
echo "远程端点: $VPC_ENDPOINT:443"
echo "通过 EC2: $EC2_HOST"

# 创建 SSH 隧道
ssh -i "$KEY_FILE" -L "$LOCAL_PORT:$VPC_ENDPOINT:443" -N "$EC2_USER@$EC2_HOST"
