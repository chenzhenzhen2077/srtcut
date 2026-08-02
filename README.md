# SRT Cutter

本地运行的播客字幕分析与视频剪辑工具。把这个 GitHub 仓库下载到自己的电脑上，就可以运行完整功能；视频、字幕、Whisper 识别和 FFmpeg 剪辑都在本机完成，不需要购买云服务器。

- 功能模拟演示：<https://chenzhenzhen2077.github.io/srtcut/>
- 完整本地版本：<https://github.com/chenzhenzhen2077/srtcut>

静态演示可以模拟字幕、智能剪辑方案和导出结果，但不会处理真实文件。真实转写、FFmpeg 剪辑和文件下载需要按照下面步骤在 Mac 本地运行。

## Mac 安装与启动

### 1. 安装 Python

需要 Python 3.10 或更高版本。没有安装时，请先打开下面地址下载 macOS 安装包：

<https://www.python.org/downloads/macos/>

安装后打开“终端”，执行下面命令检查版本：

```bash
python3 --version
```

看到 `Python 3.10`、`3.11`、`3.12` 或更高版本即可继续。

### 2. 下载项目

1. 打开 <https://github.com/chenzhenzhen2077/srtcut>。
2. 点击绿色的 **Code** 按钮。
3. 点击 **Download ZIP**。
4. 双击 ZIP 解压。默认文件夹通常是 `srtcut-main`。

### 3. 在终端启动

打开 Mac 的“终端”，复制下面整段代码。通常只需要修改第一行的项目文件夹位置：

```bash
# 只修改这一行：填写解压后的 srtcut-main 文件夹位置
PROJECT_DIR="$HOME/Downloads/srtcut-main"

cd "$PROJECT_DIR"
chmod +x start.command
./start.command
```

如果文件夹放在桌面，第一行改成：

```bash
PROJECT_DIR="$HOME/Desktop/srtcut-main"
```

如果不知道文件夹位置，可以在终端输入 `cd `（`cd` 后面保留一个空格），然后把 `srtcut-main` 文件夹从 Finder 拖进终端窗口，按回车，再执行：

```bash
chmod +x start.command
./start.command
```

第一次运行会自动完成以下操作：

1. 创建项目专用的 Python 环境 `.venv`。
2. 安装 Flask 和本地 Whisper 转写依赖。
3. 启动本地服务。
4. 自动打开 <http://127.0.0.1:8964>。

安装依赖可能需要几分钟，请不要关闭终端。看到“服务已启动”后即可使用。

### 4. FFmpeg 安装

通常不需要提前安装 FFmpeg。启动页面后，如果显示“视频处理功能不可用”，点击页面里的 **安装组件**，程序会把 FFmpeg 安装到项目自己的 `bin/` 文件夹。

已经安装 Homebrew 的用户，也可以在终端执行：

```bash
brew install ffmpeg
```

安装后可以这样检查：

```bash
ffmpeg -version
ffprobe -version
```

### 5. macOS 提示无法打开时

确认项目来自本仓库后，在项目目录执行：

```bash
xattr -dr com.apple.quarantine .
chmod +x start.command
./start.command
```

### 6. 下次启动和停止

以后可以直接双击 `start.command`，或者再次执行：

```bash
cd "$HOME/Downloads/srtcut-main"
./start.command
```

关闭运行 `start.command` 的终端窗口，或在终端按 `Control + C`，即可停止本地服务。

首次使用自动字幕会下载 Whisper 模型，首次安装和模型下载可能需要一些时间。视频处理需要 FFmpeg；页面会在本机缺少 FFmpeg 时提供安装按钮，安装文件保存到项目自己的 `bin/` 目录。关闭启动脚本打开的终端窗口即可停止服务。

默认单个上传文件上限为 2GB。超过上限时页面会立即提示先压缩或分段；本机磁盘空间充足的高级用户可以在 `.env` 中设置 `PODCAST_CUTTER_MAX_UPLOAD_MB` 调高限制。

在线 AI 不共用开发者的 Key。用户生成字幕后，在页面的“在线 AI”设置里填写自己的服务地址、模型和 API Key；Key 只保留在当前本地服务内存中。也可以在本机启动 Ollama，使用自己的本地模型。

## 功能

- 导入 SRT 字幕并生成时间轴
- 首页可直接选择“已有 SRT 字幕”，跳过语音转写，并使用 AI 生成 2–3 个可核对的内容方案
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

## 手动本地运行

需要 Python 3.10 或更高版本。项目会优先使用 `bin/` 下的本地二进制，其次使用系统 PATH；macOS 用户也可以直接使用页面里的 FFmpeg 安装按钮。

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

## 可选：线上部署

仓库保留了 `Dockerfile`、`Procfile` 和 Render Blueprint 示例 `render.yaml`，用于未来需要云端部署时参考。当前种子用户版本不要求配置 Render，也不建议为了小规模试用产生云端实例费用。

```bash
docker build -t podcast-cutter .
docker run --rm -p 8964:8964 -v podcast-cutter-data:/data podcast-cutter
```

详细配置见 `DEPLOYMENT.md`。线上环境建议设置 `PODCAST_CUTTER_WORK_DIR=/data/work`，并使用 `PODCAST_CUTTER_AI_PROVIDER=api`、`PODCAST_CUTTER_AI_LOCAL_ENABLED=false` 和服务端环境变量 `PODCAST_CUTTER_AI_API_KEY` 配置在线 AI。

## 当前边界

这是本地优先的单用户版本。任务队列、自动清理、账号隔离和跨平台 FFmpeg 打包将在后续模块中加入。线上部署已提供基础 Docker/Gunicorn 配置，但仍更适合个人或小流量使用；视频文件和自动字幕识别默认只在服务端工作目录处理，不上传到第三方服务；AI 分析是否调用第三方模型由用户自行选择。
