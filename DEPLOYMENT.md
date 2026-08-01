# 部署说明

当前种子用户推荐本地运行，不需要 Render 或其他云服务器。请先阅读项目根目录的 `README.md`，macOS 用户直接双击 `start.command` 即可。

下面的内容是未来需要云端部署时的备忘录，不是种子用户的必需步骤。

这个项目是 Flask + FFmpeg + 可选 faster-whisper。线上部署建议先用 Docker，因为容器可以稳定安装 FFmpeg，并避免把本机 `work/`、`bin/`、模型缓存和测试产物打进部署包。

## 推荐配置

- Python: 3.11
- Web server: Gunicorn
- Health check: `/health`
- Persistent disk: 挂载到 `/data`，并设置 `PODCAST_CUTTER_WORK_DIR=/data/work`
- Upload size: 根据平台网关限制设置 `PODCAST_CUTTER_MAX_UPLOAD_MB`
- AI: 线上环境建议使用 API 通道，设置 `PODCAST_CUTTER_AI_PROVIDER=api`
- Local AI: 公共线上环境设置 `PODCAST_CUTTER_AI_LOCAL_ENABLED=false`，隐藏本机模型入口

## Docker 本地验证

```bash
docker build -t podcast-cutter .
docker run --rm -p 8964:8964 -v podcast-cutter-data:/data podcast-cutter
```

打开 <http://127.0.0.1:8964>，确认 `/health` 里的 FFmpeg 和 FFprobe 都是可用状态。

## Render 部署

仓库里已经包含 `render.yaml`。部署时选择 Blueprint 或 Docker Web Service，并在 Render 控制台补充：

```bash
PODCAST_CUTTER_AI_API_KEY=你的在线 AI Key
```

如果上传和转写的文件较大，请使用带持久磁盘的实例，并根据实际需求调整磁盘大小。免费实例通常不适合长音视频转写。

## 通用 PaaS

不使用 Docker 时，服务器需要先安装系统 FFmpeg：

```bash
python -m pip install -e '.[speech,prod]'
gunicorn app:app --bind 0.0.0.0:${PORT:-8964} --workers ${WEB_CONCURRENCY:-1} --threads ${WEB_THREADS:-4} --timeout ${WEB_TIMEOUT:-600}
```

至少设置这些环境变量：

```bash
PODCAST_CUTTER_WORK_DIR=/data/work
PODCAST_CUTTER_BIN_DIR=/usr/bin
PODCAST_CUTTER_AI_PROVIDER=api
PODCAST_CUTTER_AI_LOCAL_ENABLED=false
PODCAST_CUTTER_AI_API_KEY=你的在线 AI Key
```

## 注意事项

- 当前任务仍由 Web 进程里的后台线程执行，适合个人或小流量使用；多人并发和长任务队列建议后续接 Redis/RQ/Celery。
- Whisper 模型首次使用会下载模型文件，冷启动和磁盘占用会比较明显。
- `/api/install-ffmpeg` 更适合本地环境，线上推荐在镜像或服务器层安装 FFmpeg。
