"""
软字幕提取模块

使用 ffprobe 检测视频是否包含内嵌字幕轨道，
如有则用 ffmpeg 提取为 SRT 格式字符串。

公共接口:
    extract_embedded(video_path) -> Optional[str]  - 提取内嵌字幕
    get_subtitle_streams(video_path) -> list[dict]   - 获取字幕流信息
"""

import json
import subprocess
from typing import Optional, List, Dict


def get_subtitle_streams(video_path: str) -> List[Dict]:
    """
    使用 ffprobe 获取视频中的所有字幕流信息。

    Args:
        video_path: 视频文件路径

    Returns:
        list[dict]: 字幕流信息列表，每项包含 index、codec_name、
                    codec_type、language 等字段。无字幕流时返回空列表。
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-select_streams", "s",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        data = json.loads(result.stdout)
        return data.get("streams", [])
    except json.JSONDecodeError:
        return []


def _select_best_stream(streams: List[Dict]) -> Optional[Dict]:
    """
    从字幕流列表中选择最佳字幕流。

    优先级:
        1. subrip/srt 编码的字幕流
        2. 中文语言 (chi/zh) 的字幕流
        3. 英文语言 (eng/en) 的字幕流
        4. 第一个可用的字幕流

    Args:
        streams: 字幕流信息列表

    Returns:
        dict or None: 选中的字幕流信息，无可用流时返回 None
    """
    if not streams:
        return None

    # 优先选择 subrip/srt 编码
    for s in streams:
        codec = s.get("codec_name", "")
        if codec in ("subrip", "srt", "ass", "ssa", "mov_text"):
            return s

    # 优先选择中文字幕
    for s in streams:
        lang = s.get("tags", {}).get("language", "")
        if lang in ("chi", "zh", "chs", "cht"):
            return s

    # 其次选择英文字幕
    for s in streams:
        lang = s.get("tags", {}).get("language", "")
        if lang in ("eng", "en"):
            return s

    # 回退到第一个可用流
    return streams[0] if streams else None


def extract_embedded(video_path: str) -> Optional[str]:
    """
    从视频中提取内嵌软字幕。

    流程:
        1. 用 ffprobe 检测字幕流
        2. 选择最佳字幕流
        3. 用 ffmpeg 提取为 SRT 格式字符串

    Args:
        video_path: 视频文件路径

    Returns:
        str or None: SRT 格式字幕字符串，无字幕流时返回 None

    异常处理:
        - ffprobe/ffmpeg 不可用: 返回 None
        - 超时: 返回 None
        - 提取失败: 返回 None
        所有异常均静默处理并返回 None，由主程序触发回退策略。
    """
    # 1. 检测字幕流
    streams = get_subtitle_streams(video_path)
    if not streams:
        return None

    # 2. 选择最佳字幕流
    best = _select_best_stream(streams)
    if best is None:
        return None

    stream_index = best.get("index", 0)

    # 3. 用 ffmpeg 提取为 SRT
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-v", "quiet",
                "-i", video_path,
                "-map", f"0:{stream_index}",
                "-f", "srt",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0:
        return None

    srt_content = result.stdout.strip()
    if not srt_content:
        return None

    # 验证 SRT 格式基本有效性（至少包含时间轴箭头）
    if "-->" not in srt_content:
        return None

    return srt_content
