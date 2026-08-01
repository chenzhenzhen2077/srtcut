# SRT Cutter

本地优先的播客字幕分析与视频剪辑工具。当前版本支持：

- 导入 SRT 字幕并生成时间轴
- 上传视频或音频，使用本地 Whisper 自动生成 SRT
- 检测口癖、重复词和静默
- 手动或 AI 标记剪辑段
- 使用 FFmpeg 生成初版剪辑视频
- 播客同步剪辑：先确认音频剪辑，再用同一套时间点生成音频和视频

## 播客同步剪辑

从首页进入“播客同步剪辑”后，可以上传播客视频或纯音频。上传视频时，系统会先生成字幕并找出长停顿、口癖等建议删除片段；用户确认后可以：

- 只生成 MP3，先试听内容和节奏；
- 之后继续生成同步视频；
- 或一次生成音频和视频两个版本。

音频和视频使用同一份服务端剪辑决定（`cuts`），因此两个输出的内容时间点保持一致。这个项目记录也为后续的账号隔离、任务队列和 AI 用量计费预留了接口。

## 本地运行

需要 Python 3.10 或更高版本，以及可用的 `ffmpeg` 和 `ffprobe`。项目会优先使用 `bin/` 下的本地二进制，其次使用系统 PATH。

```bash
cd srt-cutter
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python app.py
```

首次使用自动字幕功能，还需要安装本地语音识别依赖：

```bash
python -m pip install -e '.[speech]'
```

第一次选择模型时会下载 Whisper 模型。`tiny`/`base` 适合快速测试，`small` 是默认推荐，`medium` 和 `large-v3` 识别更准但需要更多内存和时间。默认使用 CPU + int8，可通过 `.env.example` 中的环境变量调整设备和计算类型。

打开 <http://127.0.0.1:8964>。

也可以通过环境变量调整端口、工作目录、二进制目录、上传大小和最大剪辑段数量，示例见 `.env.example`。

## 智能内容分析

智能剪辑支持两种语义模型通道，字幕生成仍由本地 Whisper 完成：

- 本机模型：默认连接 Ollama 的 `qwen2.5:14b`，内容不发送到外部服务。
- 在线 AI：连接 OpenAI 兼容接口，可使用 OpenAI、DeepSeek、通义等服务。

默认 `PODCAST_CUTTER_AI_PROVIDER=auto`：配置了在线 API Key 时优先使用在线 AI，否则自动尝试本机模型。也可以设置为 `local` 或 `api` 固定通道。服务端通过 `/api/check-ai` 返回当前实际使用的通道、模型和本机可用模型列表，不会把 API Key 返回给浏览器。

本机 Ollama 示例：

```bash
ollama serve
PODCAST_CUTTER_AI_PROVIDER=local \
PODCAST_CUTTER_AI_LOCAL_MODEL=qwen2.5:14b \
python app.py
```

在线 API 示例：

```bash
PODCAST_CUTTER_AI_PROVIDER=api \
PODCAST_CUTTER_AI_API_KEY=你的服务密钥 \
PODCAST_CUTTER_AI_BASE_URL=https://api.openai.com/v1 \
PODCAST_CUTTER_AI_MODEL=gpt-4.1-mini \
python app.py
```

## 检查与测试

```bash
pytest
```

健康检查地址为 `/health`，会同时报告 FFmpeg 和 FFprobe 状态。

## 线上部署

仓库已包含 `Dockerfile`、`Procfile` 和 Render Blueprint 示例 `render.yaml`。推荐使用 Docker 部署，镜像会安装 FFmpeg，并用 Gunicorn 启动 `app:app`。

```bash
docker build -t podcast-cutter .
docker run --rm -p 8964:8964 -v podcast-cutter-data:/data podcast-cutter
```

详细配置见 `DEPLOYMENT.md`。线上环境建议设置 `PODCAST_CUTTER_WORK_DIR=/data/work`，并使用 `PODCAST_CUTTER_AI_PROVIDER=api`、`PODCAST_CUTTER_AI_LOCAL_ENABLED=false` 和服务端环境变量 `PODCAST_CUTTER_AI_API_KEY` 配置在线 AI。

## 当前边界

这是本地优先的单用户版本。任务队列、自动清理、账号隔离和跨平台 FFmpeg 打包将在后续模块中加入。线上部署已提供基础 Docker/Gunicorn 配置，但仍更适合个人或小流量使用；视频文件和自动字幕识别默认只在服务端工作目录处理，不上传到第三方服务；AI 分析是否调用第三方模型由用户自行选择。
