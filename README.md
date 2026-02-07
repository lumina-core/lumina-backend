# Lumina Backend

FastAPI backend service for Lumina application.

## Quick Start

### 1. Clone and Setup Environment

```bash
# Install dependencies
uv sync

# Copy environment template
cp .env.example .env  # Edit with your configuration
```

### 2. Start the Application

`main.py` 已封装完整的启动配置（host、port、workers、日志），直接运行即可：

```bash
# 开发环境（前台运行）
uv run python main.py
```

**启动后自动完成：**
- ✓ 初始化日志系统，输出到 `logs/` 目录（按天轮转，自动压缩）
- ✓ 检查并创建数据库和表结构
- ✓ 启动 2 个 worker 进程，监听 `0.0.0.0:8000`

**Configuration**: Edit `DATABASE_URL` in `.env` file

Visit http://localhost:8000/docs for interactive API documentation.

### 3. 日志说明

日志统一由 loguru 管理，自动输出到 `logs/` 目录：

| 文件 | 内容 | 轮转 | 保留 |
|------|------|------|------|
| `logs/app_YYYY-MM-DD.log` | 全部日志 | 每天 | 30 天 |
| `logs/error_YYYY-MM-DD.log` | 仅 ERROR 及以上 | 每天 | 60 天 |

```bash
# 实时查看日志
tail -f logs/app_$(date +%Y-%m-%d).log

# 查看错误日志
tail -f logs/error_$(date +%Y-%m-%d).log
```

## Linux 后台运行

### 方式一：nohup（简单快捷）

```bash
# 后台启动
nohup uv run python main.py &

# 查看进程
ps aux | grep "main.py"

# 停止服务
pkill -f "python main.py"
```

### 方式二：systemd（推荐生产环境）

相比 nohup，systemd 的优势：
- **进程崩溃自动重启** — `Restart=always` 确保服务挂了会自动拉起
- **开机自启动** — `systemctl enable` 后服务器重启也会自动运行
- **标准化管理** — `start/stop/restart/status` 统一命令，不用手动 `ps/kill`
- **日志集成** — `journalctl` 可以查看历史日志，支持按时间筛选

#### 1. 创建服务文件

```bash
# 先查看 uv 的绝对路径，替换到下面的 ExecStart 中
which uv
```

```bash
sudo vim /etc/systemd/system/lumina.service
```

```ini
[Unit]
Description=Lumina Backend Service
After=network.target

[Service]
Type=simple
User=your_user                                        # 改成你的 Linux 用户名
WorkingDirectory=/path/to/lumina-backend               # 改成项目实际路径
ExecStart=/home/your_user/.local/bin/uv run python main.py  # uv 绝对路径，用 which uv 查
Restart=always
RestartSec=5
Environment="PATH=/usr/local/bin:/usr/bin"

[Install]
WantedBy=multi-user.target
```

#### 2. 启用并启动

```bash
sudo systemctl daemon-reload    # 加载新的服务文件
sudo systemctl enable lumina    # 设置开机自启
sudo systemctl start lumina     # 立即启动
```

#### 3. 日常管理命令

```bash
sudo systemctl status lumina                # 查看状态（是否运行、PID、最近日志）
sudo systemctl restart lumina               # 重启服务（部署新代码后用）
sudo systemctl stop lumina                  # 停止服务

# 查看日志
journalctl -u lumina -f                     # 实时跟踪日志
journalctl -u lumina --since "1 hour ago"   # 查最近 1 小时
```

#### 4. 典型的部署更新流程

```bash
cd /path/to/lumina-backend
git pull
uv sync                         # 更新依赖
sudo systemctl restart lumina   # 重启生效
sudo systemctl status lumina    # 确认正常
```

## API Endpoints

See [DATABASE.md](DATABASE.md) for detailed API documentation.

## Project Structure

```
app/
├── core/
│   ├── config.py          # Application configuration
│   └── database.py        # Database engine and session
├── models/
│   └── user.py            # SQLModel models
└── api/routes/
    └── users.py           # User routes
scripts/
└── setup.sh               # Setup script for initialization
```

## Data Migration

### Compress data directory

```bash
# tar.gz (recommended)
tar -czvf data.tar.gz data/

# tar.zst (faster, smaller, requires zstd)
tar -I zstd -cvf data.tar.zst data/

# zip
zip -r data.zip data/
```

### Upload to server

```bash
# scp
scp data.tar.gz user@server:/path/to/destination/

# rsync (supports resume)
rsync -avzP data.tar.gz user@server:/path/to/destination/
```

### Extract on server

```bash
# tar.gz
tar -xzvf data.tar.gz

# tar.zst
tar -I zstd -xvf data.tar.zst

# zip
unzip data.zip
```
