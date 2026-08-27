"""
环境检测模块

检测系统环境：Python 版本、ffmpeg、NVIDIA GPU。
根据 GPU 情况自动选择 Whisper 模型规格。

公共接口:
    EnvInfo (dataclass)        - 环境信息
    check_environment() -> EnvInfo - 执行环境检测
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EnvInfo:
    """环境检测结果"""
    python_version: str = ""
    python_ok: bool = False
    ffmpeg_path: str = ""
    ffmpeg_ok: bool = False
    gpu_name: str = ""
    gpu_vram_gb: float = 0.0
    has_gpu: bool = False
    whisper_model: str = "small"
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        """环境是否完全就绪"""
        return self.python_ok and self.ffmpeg_ok


def _check_python() -> tuple:
    """检测 Python 版本"""
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 10)
    return version, ok


def _check_ffmpeg() -> tuple:
    """检测 ffmpeg 是否可用"""
    path = shutil.which("ffmpeg")
    if path:
        return path, True
    return "", False


def _check_ffprobe() -> bool:
    """检测 ffprobe 是否可用"""
    path = shutil.which("ffprobe")
    return path is not None


def _check_gpu() -> tuple:
    """
    检测 NVIDIA GPU 型号和显存。
    使用 nvidia-smi 命令获取信息。

    Returns:
        (gpu_name, vram_gb, has_gpu)
    """
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return "", 0.0, False

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(", ")
            gpu_name = parts[0].strip()
            vram_mb = float(parts[1].strip())
            vram_gb = vram_mb / 1024.0
            return gpu_name, round(vram_gb, 1), True
    except (subprocess.TimeoutExpired, ValueError, IndexError):
        pass

    return "", 0.0, False


def _select_whisper_model(vram_gb: float, has_gpu: bool) -> str:
    """
    根据 GPU 显存自动选择 Whisper 模型。

    规则:
        - 有 GPU 且显存 >= 6GB -> medium
        - 有 GPU 但显存不足   -> small
        - 无 GPU               -> small
    """
    if not has_gpu:
        return "small"

    # 延迟导入配置，避免循环依赖
    try:
        import config
        threshold = config.WHISPER_MODEL_VRAM_THRESHOLD
        preferred = config.WHISPER_MODEL_PREFERRED
        fallback = config.WHISPER_MODEL_FALLBACK
    except ImportError:
        threshold = 6
        preferred = "medium"
        fallback = "small"

    if vram_gb >= threshold:
        return preferred
    return fallback


def check_environment() -> EnvInfo:
    """
    执行完整环境检测。

    检测内容:
        1. Python 版本 (>= 3.10)
        2. ffmpeg 是否安装且可用
        3. ffprobe 是否可用（软字幕提取依赖）
        4. NVIDIA GPU 型号和显存
        5. 根据 GPU 自动选择 Whisper 模型

    Returns:
        EnvInfo: 环境检测结果
    """
    info = EnvInfo()

    # 1. 检测 Python
    info.python_version, info.python_ok = _check_python()
    if not info.python_ok:
        info.errors.append(
            f"Python 版本过低: {info.python_version}，需要 3.10+。"
            f"请从 https://www.python.org/downloads/ 下载安装。"
        )

    # 2. 检测 ffmpeg
    info.ffmpeg_path, info.ffmpeg_ok = _check_ffmpeg()
    if not info.ffmpeg_ok:
        info.errors.append(
            "未找到 ffmpeg，请安装: https://ffmpeg.org/download.html"
        )

    # 3. 检测 ffprobe
    ffprobe_ok = _check_ffprobe()
    if not ffprobe_ok:
        info.warnings.append(
            "未找到 ffprobe，软字幕提取功能将不可用（会自动回退到 OCR 或 Whisper）。"
        )

    # 4. 检测 GPU
    info.gpu_name, info.gpu_vram_gb, info.has_gpu = _check_gpu()

    # 5. 选择 Whisper 模型
    info.whisper_model = _select_whisper_model(info.gpu_vram_gb, info.has_gpu)

    return info


def print_env_info(info: EnvInfo) -> None:
    """打印环境检测结果到终端"""
    print("\n=== 环境检测 ===")

    # Python
    status = "OK" if info.python_ok else "FAIL"
    print(f"[{status}] Python {info.python_version}")

    # ffmpeg
    status = "OK" if info.ffmpeg_ok else "FAIL"
    if info.ffmpeg_path:
        print(f"[{status}] ffmpeg: {info.ffmpeg_path}")
    else:
        print(f"[{status}] ffmpeg: 未找到")

    # GPU
    if info.has_gpu:
        print(
            f"[OK] GPU: {info.gpu_name} "
            f"({info.gpu_vram_gb}GB) -> 模型: {info.whisper_model}"
        )
    else:
        print(f"[--] GPU: 未检测到 NVIDIA GPU -> 模型: {info.whisper_model}")

    # 警告
    for w in info.warnings:
        print(f"[!] {w}")

    # 错误
    for e in info.errors:
        print(f"[X] {e}")

    print()
