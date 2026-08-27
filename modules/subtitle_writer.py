"""
字幕写入模块

将各来源（软字幕提取/OCR/Whisper）的字幕数据
统一格式化为标准 SRT 文件并保存。

公共接口:
    format_timestamp(seconds) -> str          - 秒数转 SRT 时间轴
    entries_to_srt(entries) -> str            - 字幕条目列表转 SRT 字符串
    save_srt(srt_content, output_path) -> str - 保存 SRT 文件
    write_srt_from_entries(entries, video_path, output_dir, method) -> str
"""

import os
from typing import List, Dict

try:
    import config
except ImportError:
    config = type("config", (), {
        "SRT_ENCODING": "utf-8",
        "SUBTITLE_SUFFIX": {
            "embedded": "_embedded",
            "ocr": "_ocr",
            "whisper": "_whisper",
        },
        "OUTPUT_FORMAT": "srt",
    })()


def format_timestamp(seconds: float) -> str:
    """
    将秒数转换为 SRT 时间轴格式。

    格式: HH:MM:SS,mmm
    例如: 1.5 -> "00:00:01,500"

    Args:
        seconds: 秒数（浮点数）

    Returns:
        str: SRT 时间轴格式字符串
    """
    if seconds < 0:
        seconds = 0.0

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def entries_to_srt(entries: List[Dict]) -> str:
    """
    将字幕条目列表转换为标准 SRT 格式字符串。

    每个条目格式: {"start": float, "end": float, "text": str}

    SRT 结构（每条三行）:
        序号
        开始时间 --> 结束时间
        字幕文本

    Args:
        entries: 字幕条目列表

    Returns:
        str: SRT 格式字符串
    """
    if not entries:
        return ""

    srt_lines = []
    for i, entry in enumerate(entries, start=1):
        start = format_timestamp(entry.get("start", 0.0))
        end = format_timestamp(entry.get("end", 0.0))
        text = entry.get("text", "").strip()

        if not text:
            continue

        srt_lines.append(str(i))
        srt_lines.append(f"{start} --> {end}")
        srt_lines.append(text)
        srt_lines.append("")  # 空行分隔

    return "\n".join(srt_lines)


def save_srt(srt_content: str, output_path: str) -> str:
    """
    保存 SRT 字幕文件。

    使用 UTF-8 编码写入文件。
    自动创建父目录。

    Args:
        srt_content: SRT 格式字符串
        output_path: 输出文件路径

    Returns:
        str: 保存的文件路径

    Raises:
        IOError: 文件写入失败
    """
    # 确保父目录存在
    parent_dir = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(output_path, "w", encoding=config.SRT_ENCODING) as f:
        f.write(srt_content)

    return output_path


def write_srt_from_entries(
    entries: List[Dict],
    video_path: str,
    output_dir: str,
    method: str
) -> str:
    """
    便捷函数：将字幕条目列表直接保存为 SRT 文件。

    整合 entries_to_srt + save_srt + 路径生成。

    Args:
        entries: 字幕条目列表 [{"start": float, "end": float, "text": str}]
        video_path: 视频文件路径（用于生成输出文件名）
        output_dir: 字幕输出根目录
        method: 提取方式 ("embedded" / "ocr" / "whisper")

    Returns:
        str: 保存的 SRT 文件路径

    Raises:
        IOError: 文件写入失败
    """
    from modules.file_utils import get_subtitle_path, get_video_name

    # 生成 SRT 内容
    srt_content = entries_to_srt(entries)

    # 生成输出路径
    output_path = get_subtitle_path(video_path, output_dir, method)

    # 保存文件
    return save_srt(srt_content, output_path)


def write_srt_from_string(
    srt_content: str,
    video_path: str,
    output_dir: str,
    method: str
) -> str:
    """
    便捷函数：将已有的 SRT 字符串直接保存为文件。

    用于软字幕提取场景（ffmpeg 已输出 SRT 格式）。

    Args:
        srt_content: SRT 格式字符串
        video_path: 视频文件路径（用于生成输出文件名）
        output_dir: 字幕输出根目录
        method: 提取方式 ("embedded" / "ocr" / "whisper")

    Returns:
        str: 保存的 SRT 文件路径
    """
    from modules.file_utils import get_subtitle_path

    output_path = get_subtitle_path(video_path, output_dir, method)
    return save_srt(srt_content, output_path)
