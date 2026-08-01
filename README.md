# SRT Cutter

本地优先的播客字幕分析与视频剪辑工具。当前版本支持：

- 导入 SRT 字幕并生成时间轴
- 上传视频或音频，使用本地 Whisper 自动生成 SRT
- 检测口癖、重复词和静默
- 手动或 AI 标记剪辑段
- 使用 FFmpeg 生成初版剪辑视频

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

## 检查与测试

```bash
pytest
```

健康检查地址为 `/health`，会同时报告 FFmpeg 和 FFprobe 状态。

## 当前边界

这是本地单用户版本。任务队列、自动清理、账号隔离、在线部署和跨平台 FFmpeg 打包将在后续模块中加入。视频文件和自动字幕识别默认只在本机工作目录处理，不上传到第三方服务；AI 分析是否调用第三方模型由用户自行选择。
