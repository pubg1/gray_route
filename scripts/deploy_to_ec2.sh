#!/bin/bash
# 部署脚本到 EC2 实例并运行导入

# 配置变量
EC2_HOST="your-ec2-public-ip"  # 替换为你的 EC2 公网 IP
EC2_USER="ubuntu"              # 或 ec2-user (取决于 AMI)
KEY_FILE="your-key.pem"        # 替换为你的密钥文件路径

echo "🚀 部署 OpenSearch 导入脚本到 EC2"
echo "=================================="

# 1. 创建远程目录
echo "📁 创建远程目录..."
ssh -i "$KEY_FILE" "$EC2_USER@$EC2_HOST" "mkdir -p ~/opensearch-import/{scripts,data}"

# 2. 上传脚本文件
echo "📤 上传脚本文件..."
scp -i "$KEY_FILE" *.py "$EC2_USER@$EC2_HOST:~/opensearch-import/scripts/"

# 3. 上传数据文件
echo "📤 上传数据文件..."
scp -i "$KEY_FILE" ../data/servicingcase_last.json "$EC2_USER@$EC2_HOST:~/opensearch-import/data/"

# 4. 在 EC2 上安装依赖并运行
echo "🔧 在 EC2 上安装依赖并运行导入..."
ssh -i "$KEY_FILE" "$EC2_USER@$EC2_HOST" << 'EOF'
cd ~/opensearch-import/scripts

# 安装 Python 和 pip（如果需要）
sudo apt update
sudo apt install -y python3 python3-pip

# 安装依赖
python3 install_opensearch_deps.py

# 运行导入
python3 run_import.py
EOF

echo "✅ 部署和导入完成!"
