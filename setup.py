from setuptools import find_packages, setup

setup(
    name="podcast-cutter",
    version="0.3.0",
    description="本地优先的播客字幕分析与视频剪辑工具",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=["Flask>=3.1,<4"],
    extras_require={
        "dev": ["pytest>=8,<9", "ruff>=0.6,<1"],
        "speech": ["faster-whisper>=1.1,<2"],
    },
    entry_points={"console_scripts": ["podcast-cutter=podcast_cutter.cli:main"]},
)
