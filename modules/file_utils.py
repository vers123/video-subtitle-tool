"""
文件管理模块

负责文件扫描、路径管理、临时文件清理。

公共接口:
    scan_video_files(input_dir) -> list[str]
    get_subtitle_path(video_path, output_dir, method) -> str
    ensure_dir(path) -> None
    cleanup_temp_files(*paths) -> None
    is_supported_video(filepath) -> bool
"""

import os
import shutil
from typing import List

try:
    import config
except ImportError:
    # 直接运行时的 fallback
    config = type("config", (), {
        "SUPPORTED_VIDEO_EXTENSIONS": [".mp4", ".mkv", ".avi", ".mov"],
        "SUBTITLE_OUTPUT_DIR": "subtitles",
        "SUBTITLE_SUFFIX": {
            "embedded": "_embedded",
            "ocr": "_ocr",
            "whisper": "_whisper",
        },
        "OUTPUT_FORMAT": "srt",
        "CLEANUP_TEMP_FILES": True,
        "TEMP_DIR": "temp",
    })()


def is_supported_video(filepath: str) -> bool:
    """
    判断文件是否为支持的视频格式。

    Args:
        filepath: 文件路径

    Returns:
        bool: 是否为支持的视频格式
    """
    ext = os.path.splitext(filepath)[1].lower()
    return ext in config.SUPPORTED_VIDEO_EXTENSIONS


def scan_video_files(input_dir: str) -> List[str]:
    """
    扫描指定目录下的所有支持格式的视频文件。

    不支持的格式会输出警告信息并跳过。
    递归扫描子目录。

    Args:
        input_dir: 视频输入目录路径

    Returns:
        list[str]: 视频文件路径列表（绝对路径），按文件名排序
    """
    if not os.path.isdir(input_dir):
        print(f"[!] 视频目录不存在: {input_dir}")
        return []

    video_files = []
    unsupported_files = []

    for root, dirs, files in os.walk(input_dir):
        for filename in sorted(files):
            filepath = os.path.join(root, filename)
            if is_supported_video(filepath):
                video_files.append(os.path.abspath(filepath))
            else:
                # 跳过非视频文件和隐藏文件
                if not filename.startswith(".") and not filename.startswith("."):
                    ext = os.path.splitext(filename)[1].lower()
                    if ext and ext not in [".srt", ".txt", ".md", ".log"]:
                        unsupported_files.append(filename)

    # 输出不支持文件警告
    for f in unsupported_files:
        print(f"[!] 不支持的文件格式，已跳过: {f}")

    video_files.sort()
    return video_files


def get_video_name(video_path: str) -> str:
    """
    获取视频文件名（不含扩展名）。

    Args:
        video_path: 视频文件路径

    Returns:
        str: 文件名（不含扩展名）
    """
    return os.path.splitext(os.path.basename(video_path))[0]


def get_subtitle_path(
    video_path: str,
    output_dir: str,
    method: str
) -> str:
    """
    根据视频文件名和提取方式，生成字幕文件的完整路径。

    路径结构: output_dir/视频文件名/视频文件名_提取方式.srt

    Args:
        video_path: 视频文件路径
        output_dir: 字幕输出根目录
        method: 提取方式 ("embedded" / "ocr" / "whisper")

    Returns:
        str: 字幕文件的完整路径
    """
    video_name = get_video_name(video_path)
    suffix = config.SUBTITLE_SUFFIX.get(method, f"_{method}")
    ext = config.OUTPUT_FORMAT
    filename = f"{video_name}{suffix}.{ext}"
    return os.path.join(output_dir, video_name, filename)


def ensure_dir(path: str) -> None:
    """
    确保目录存在，不存在则创建。

    Args:
        path: 目录路径
    """
    os.makedirs(path, exist_ok=True)


def get_temp_audio_path(video_path: str, temp_dir: str) -> str:
    """
    生成临时音频文件路径。

    Args:
        video_path: 视频文件路径
        temp_dir: 临时文件目录

    Returns:
        str: 临时 WAV 文件路径
    """
    video_name = get_video_name(video_path)
    return os.path.join(temp_dir, f"{video_name}.wav")


def cleanup_temp_files(*paths: str) -> None:
    """
    清理临时文件。

    安全删除：文件不存在时静默跳过。

    Args:
        *paths: 要删除的文件路径列表
    """
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
                if config.VERBOSE_OUTPUT:
                    print(f"    -> 已清理临时文件: {os.path.basename(path)}")
            except OSError as e:
                print(f"[!] 清理文件失败 {path}: {e}")


def cleanup_temp_dir(temp_dir: str) -> None:
    """
    清理整个临时目录。

    Args:
        temp_dir: 临时目录路径
    """
    if os.path.isdir(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except OSError as e:
            print(f"[!] 清理临时目录失败: {e}")
