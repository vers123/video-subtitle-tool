"""
硬字幕 OCR 识别模块

截取视频画面底部区域，使用 PaddleOCR 识别烧录字幕，
根据帧时间戳生成带时间轴的字幕条目。

公共接口:
    extract_ocr_subtitles(video_path) -> Optional[list[dict]]
"""

import os
import subprocess
import tempfile
from typing import Optional, List, Dict, Tuple

try:
    import config
except ImportError:
    config = type("config", (), {
        "OCR_BOTTOM_REGION_RATIO": 0.15,
        "OCR_FRAME_INTERVAL": 1.0,
        "OCR_LANGUAGE": "ch",
        "OCR_MERGE_THRESHOLD": 2.0,
    })()


def _get_video_duration(video_path: str) -> float:
    """
    使用 ffprobe 获取视频时长（秒）。

    Args:
        video_path: 视频文件路径

    Returns:
        float: 视频时长（秒），获取失败返回 0.0
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                video_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, json.JSONDecodeError):
        pass
    return 0.0


def _extract_frames(
    video_path: str,
    interval: float,
    bottom_ratio: float
) -> Tuple[List[Tuple[float, str]], str]:
    """
    从视频底部区域按固定间隔截取帧。

    使用 ffmpeg 截取画面底部 bottom_ratio 比例的区域，
    每隔 interval 秒截取一帧，保存为临时图片文件。

    Args:
        video_path: 视频文件路径
        interval: 截帧间隔（秒）
        bottom_ratio: 底部截取比例（0.0-1.0）

    Returns:
        list[tuple]: [(时间戳, 图片路径), ...]
        失败时返回空列表。
    """
    duration = _get_video_duration(video_path)
    if duration <= 0:
        return []

    # 计算裁剪高度（像素），需要先获取视频高度
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-select_streams", "v:0",
                video_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if probe.returncode == 0:
            import json
            data = json.loads(probe.stdout)
            streams = data.get("streams", [])
            if streams:
                height = int(streams[0].get("height", 0))
                width = int(streams[0].get("width", 0))
                if height > 0:
                    crop_height = max(1, int(height * bottom_ratio))
                else:
                    crop_height = 100
            else:
                crop_height = 100
        else:
            crop_height = 100
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, json.JSONDecodeError):
        crop_height = 100

    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="ocr_frames_")
    frames = []

    # 按间隔截帧
    timestamps = []
    t = 0.0
    while t < duration:
        timestamps.append(t)
        t += interval

    for i, ts in enumerate(timestamps):
        img_path = os.path.join(temp_dir, f"frame_{i:06d}.png")
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-v", "quiet",
                    "-ss", f"{ts:.3f}",
                    "-i", video_path,
                    "-vframes", "1",
                    "-vf", f"crop=iw:{crop_height}:0:ih-{crop_height}",
                    "-y",
                    img_path,
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0 and os.path.exists(img_path):
                frames.append((ts, img_path))
        except subprocess.TimeoutExpired:
            continue

    return frames, temp_dir


def _ocr_recognize(frame_paths: List[str], language: str = "ch") -> List[str]:
    """
    使用 PaddleOCR 识别图片中的文字。

    延迟导入 PaddleOCR，避免未安装时影响其他模块。

    Args:
        frame_paths: 图片路径列表
        language: 识别语言 ("ch" 或 "en")

    Returns:
        list[str]: 每张图片识别到的文字列表，识别失败为空字符串
    """
    if not frame_paths:
        return []

    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print("[!] PaddleOCR 未安装，OCR 功能不可用")
        return [""] * len(frame_paths)

    # 初始化 OCR 引擎（使用中文模型）
    try:
        ocr = PaddleOCR(
            use_angle_cls=True,
            lang=language,
            show_log=False,
        )
    except Exception as e:
        print(f"[!] PaddleOCR 初始化失败: {e}")
        return [""] * len(frame_paths)

    results = []
    for img_path in frame_paths:
        try:
            result = ocr.ocr(img_path, cls=True)
            if result and result[0]:
                # 提取所有识别到的文字行，拼接为一条
                texts = []
                for line in result[0]:
                    if line and len(line) >= 2:
                        text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                        texts.append(text.strip())
                results.append(" ".join(texts))
            else:
                results.append("")
        except Exception:
            results.append("")

    return results


def _merge_subtitles(
    entries: List[Dict],
    threshold: float
) -> List[Dict]:
    """
    合并相邻相同的字幕条目。

    如果两条相邻条目文本相同且时间间隔小于 threshold 秒，
    则合并为一条（保留第一条的 start 和第二条的 end）。

    Args:
        entries: 字幕条目列表 [{"start": float, "end": float, "text": str}]
        threshold: 合并阈值（秒）

    Returns:
        list[dict]: 合并后的字幕条目列表
    """
    if not entries:
        return []

    merged = [entries[0].copy()]

    for entry in entries[1:]:
        prev = merged[-1]
        if (
            entry["text"] == prev["text"]
            and entry["start"] - prev["end"] <= threshold
        ):
            # 合并：延长上一条的结束时间
            prev["end"] = entry["end"]
        else:
            merged.append(entry.copy())

    # 过滤空文本
    return [e for e in merged if e["text"].strip()]


def extract_ocr_subtitles(video_path: str) -> Optional[List[Dict]]:
    """
    从视频中通过 OCR 识别硬字幕。

    完整流程:
        1. 按固定间隔截取视频底部画面帧
        2. 用 PaddleOCR 识别每帧文字
        3. 合并相邻相同的识别结果
        4. 生成带时间轴的字幕条目列表

    Args:
        video_path: 视频文件路径

    Returns:
        list[dict] or None: 字幕条目列表 [{"start": float, "end": float, "text": str}]
        识别失败或无字幕时返回 None

    异常处理:
        - ffmpeg 不可用: 返回 None
        - PaddleOCR 未安装: 返回 None
        - 截帧失败: 返回 None
        - 识别结果全部为空: 返回 None
    """
    # 1. 截取底部帧
    frames_result = _extract_frames(
        video_path,
        interval=config.OCR_FRAME_INTERVAL,
        bottom_ratio=config.OCR_BOTTOM_REGION_RATIO,
    )

    if not frames_result or not frames_result[0]:
        return None

    frames, temp_dir = frames_result

    if not frames:
        # 清理临时目录
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    # 2. OCR 识别
    img_paths = [f[1] for f in frames]
    texts = _ocr_recognize(img_paths, language=config.OCR_LANGUAGE)

    # 3. 构建字幕条目
    raw_entries = []
    for i, (ts, _) in enumerate(frames):
        text = texts[i] if i < len(texts) else ""
        if text:
            end_ts = ts + config.OCR_FRAME_INTERVAL
            raw_entries.append({
                "start": ts,
                "end": end_ts,
                "text": text,
            })

    # 清理临时文件
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)

    # 4. 合并相同条目
    merged = _merge_subtitles(raw_entries, config.OCR_MERGE_THRESHOLD)

    if not merged:
        return None

    return merged
