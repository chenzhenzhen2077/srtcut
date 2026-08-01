"""Command-line entry point."""


from . import create_app
from .config import Config
from .media import find_binary


def main():
    app = create_app()
    ffmpeg = find_binary("ffmpeg", Config.BIN_DIR)
    ffprobe = find_binary("ffprobe", Config.BIN_DIR)
    print("SRT Cutter - 播客剪辑辅助工具")
    print(f"FFmpeg: {'就绪' if ffmpeg else '未安装'}")
    print(f"FFprobe: {'就绪' if ffprobe else '未安装'}")
    print(f"http://{Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=False)

