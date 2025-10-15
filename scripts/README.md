# 服务管理脚本使用说明

## 脚本概述

本目录包含用于管理汽车故障诊断API服务的Shell脚本：

- **`run_local.sh`** - 启动服务（后台运行）
- **`stop_local.sh`** - 停止服务
- **`restart_local.sh`** - 重启服务
- **`status_local.sh`** - 查看服务状态

## 快速使用

### 启动服务
```bash
./scripts/run_local.sh
```

### 查看状态
```bash
./scripts/status_local.sh
```

### 停止服务
```bash
./scripts/stop_local.sh
```

### 重启服务
```bash
./scripts/restart_local.sh
```

## 详细说明

### 1. 启动服务 (`run_local.sh`)

**功能特性：**
- ✅ 后台运行，不阻塞终端
- ✅ 自动创建日志目录和文件
- ✅ PID文件管理，防止重复启动
- ✅ 启动状态检查和错误处理
- ✅ 详细的启动信息输出

**输出文件：**
- `logs/codex-gray-route.pid` - 进程ID文件
- `logs/codex-gray-route.log` - 访问日志
- `logs/codex-gray-route.error.log` - 错误日志

**示例输出：**
```
🚀 启动 codex-gray-route 服务...
   地址: http://0.0.0.0:8080
   日志: ./logs/codex-gray-route.log
   错误日志: ./logs/codex-gray-route.error.log
   PID文件: ./logs/codex-gray-route.pid
✅ 服务启动成功!
   PID: 12345
   状态检查: curl http://0.0.0.0:8080/health
   查看日志: tail -f ./logs/codex-gray-route.log
   停止服务: ./scripts/stop_local.sh
```

### 2. 停止服务 (`stop_local.sh`)

**功能特性：**
- ✅ 优雅停止（SIGTERM）
- ✅ 强制停止（SIGKILL）作为备用
- ✅ 自动清理PID文件
- ✅ 进程状态验证

**停止流程：**
1. 检查PID文件是否存在
2. 验证进程是否运行
3. 发送SIGTERM信号优雅停止
4. 等待最多10秒
5. 如果失败，发送SIGKILL强制停止
6. 清理PID文件

### 3. 重启服务 (`restart_local.sh`)

**功能特性：**
- ✅ 先停止后启动
- ✅ 等待确保完全停止
- ✅ 错误处理和状态反馈

### 4. 状态检查 (`status_local.sh`)

**检查项目：**
- ✅ 进程状态（PID、运行时间、内存、CPU）
- ✅ 网络端口监听状态
- ✅ API健康检查
- ✅ 日志文件状态和大小
- ✅ 最近错误日志

**示例输出：**
```
📊 codex-gray-route 服务状态
==================================
📝 PID文件: ./logs/codex-gray-route.pid
🆔 进程ID: 12345
🟢 进程状态: 运行中
⏱️  运行时间: 01:23:45
💾 内存使用: 156.7 MB
🖥️  CPU使用: 2.3%

🌐 网络状态:
   地址: http://0.0.0.0:8080
   端口状态: ✅ 8080 端口已监听

🏥 健康检查:
   API状态: ✅ 健康
   响应: {"status":"ok"}

📋 日志文件:
   访问日志: ✅ ./logs/codex-gray-route.log (2.3M, 1234 行)
   错误日志: ✅ ./logs/codex-gray-route.error.log (1.2K, 5 行)
```

## 配置说明

所有脚本使用相同的配置变量（在各脚本顶部）：

```bash
APP_NAME="codex-gray-route"        # 应用名称
HOST="0.0.0.0"                     # 监听地址
PORT="8080"                        # 监听端口
PID_FILE="./logs/${APP_NAME}.pid"  # PID文件路径
LOG_FILE="./logs/${APP_NAME}.log"  # 日志文件路径
ERROR_LOG_FILE="./logs/${APP_NAME}.error.log"  # 错误日志路径
```

## 常见问题

### 1. 权限问题
在Linux/Mac上，确保脚本有执行权限：
```bash
chmod +x scripts/*.sh
```

### 2. 端口被占用
```
❌ 服务启动失败
   请检查错误日志: cat ./logs/codex-gray-route.error.log
```

解决方法：
- 检查端口是否被占用：`netstat -tuln | grep 8080`
- 修改配置中的PORT变量
- 或停止占用端口的进程

### 3. 虚拟环境问题
```
source .venv/bin/activate: No such file or directory
```

解决方法：
- 确保在项目根目录运行脚本
- 检查虚拟环境是否正确创建：`python -m venv .venv`

### 4. 日志文件过大
定期清理日志文件：
```bash
# 清空日志但保留文件
> logs/codex-gray-route.log
> logs/codex-gray-route.error.log

# 或者备份后删除
mv logs/codex-gray-route.log logs/codex-gray-route.log.bak
```

## 系统服务集成

### systemd 服务文件示例
```ini
[Unit]
Description=Codex Gray Route API
After=network.target

[Service]
Type=forking
User=your-user
WorkingDirectory=/path/to/codex-gray-route-macos
ExecStart=/path/to/codex-gray-route-macos/scripts/run_local.sh
ExecStop=/path/to/codex-gray-route-macos/scripts/stop_local.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 开机自启动
```bash
# 复制服务文件
sudo cp codex-gray-route.service /etc/systemd/system/

# 启用服务
sudo systemctl enable codex-gray-route

# 启动服务
sudo systemctl start codex-gray-route
```

## 监控和维护

### 日志轮转
创建 `/etc/logrotate.d/codex-gray-route`：
```
/path/to/logs/codex-gray-route*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    postrotate
        /path/to/scripts/restart_local.sh > /dev/null 2>&1 || true
    endscript
}
```

### 健康检查脚本
```bash
#!/bin/bash
# health_check.sh
if ! curl -s http://localhost:8080/health > /dev/null; then
    echo "Service unhealthy, restarting..."
    ./scripts/restart_local.sh
fi
```

### 定时任务
```bash
# 每5分钟检查一次服务健康状态
*/5 * * * * /path/to/health_check.sh

# 每天凌晨2点重启服务（可选）
0 2 * * * /path/to/scripts/restart_local.sh
```

## 故障排查

### 查看实时日志
```bash
# 访问日志
tail -f logs/codex-gray-route.log

# 错误日志
tail -f logs/codex-gray-route.error.log

# 同时查看两个日志
tail -f logs/codex-gray-route.log logs/codex-gray-route.error.log
```

### 调试模式启动
临时修改 `run_local.sh` 中的日志级别：
```bash
--log-level debug
```

### 手动测试
```bash
# 健康检查
curl http://localhost:8080/health

# API测试
curl "http://localhost:8080/match?q=刹车发软"

# 性能测试
time curl "http://localhost:8080/match?q=发动机无法启动"
```
