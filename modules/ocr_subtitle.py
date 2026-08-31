"""
硬字幕 OCR 识别模块

截取视频画面底部区域，对帧进行灰度化+二值化预处理，
使用 PaddleOCR 识别烧录字幕，根据帧时间戳生成带时间轴的字幕条目。

针对白字黑描边样式字幕优化：通过二值化增强文字与背景对比度。

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
        "OCR_FRAME_INTERVAL": 0.5,
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


def _preprocess_frame(img_path: str, output_path: str) -> str:
    """
    对截取的帧图片进行预处理，增强字幕文字与背景的对比度。

    预处理流程:
        1. 灰度化（去除色彩干扰）
        2. 自适应二值化（白字变白，背景变黑）

    使用 OpenCV (cv2) 进行处理。如果 OpenCV 不可用，
    则返回原始图片路径（降级为不做预处理）。

    Args:
        img_path: 原始图片路径
        output_path: 预处理后图片保存路径

    Returns:
        str: 预处理后图片路径，OpenCV 不可用时返回原始路径
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return img_path

    try:
        img = cv2.imread(img_path)
        if img is None:
            return img_path

        # 1. 灰度化
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 2. 自适应阈值二值化
        #    THRESH_BINARY + 二值化：文字区域变白(255)，背景变黑(0)
        #    自适应阈值能应对画面亮度不均匀的情况
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=15,
            C=5,
        )

        # 3. 轻量去噪（3x3 开运算去除小噪点）
        kernel = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

        cv2.imwrite(output_path, binary)
        return output_path
    except Exception:
        return img_path


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
        tuple: ([(时间戳, 图片路径), ...], 临时目录路径)
        失败时返回 ([], 临时目录路径)
    """
    duration = _get_video_duration(video_path)
    if duration <= 0:
        return [], ""

    # 获取视频高度以计算裁剪区域
    crop_height = 100
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
                if height > 0:
                    crop_height = max(1, int(height * bottom_ratio))
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, json.JSONDecodeError):
        pass

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
                # 预处理帧图片
                preprocessed_path = os.path.join(temp_dir, f"frame_{i:06d}_bin.png")
                final_path = _preprocess_frame(img_path, preprocessed_path)
                frames.append((ts, final_path))
        except subprocess.TimeoutExpired:
            continue

    return frames, temp_dir


def _detect_paddleocr_version() -> int:
    """
    检测已安装的 PaddleOCR 主版本号。

    Returns:
        int: 主版本号（2 或 3），检测失败返回 3（按新 API 尝试）
    """
    try:
        import paddleocr
        version_str = getattr(paddleocr, "__version__", "3.0.0")
        return int(version_str.split(".")[0])
    except Exception:
        return 3


def _init_paddleocr_v3(language: str):
    """
    初始化 PaddleOCR 3.x 引擎。

    3.x 移除了 show_log、use_angle_cls 参数，
    新增 use_doc_orientation_classify 等参数。
    PP-OCRv5 默认支持中英日繁，无需指定 lang。

    Args:
        language: 识别语言（3.x 中 PP-OCRv5 原生支持中文，此参数仅用于兼容）

    Returns:
        PaddleOCR 实例
    """
    from paddleocr import PaddleOCR
    return PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def _init_paddleocr_v2(language: str):
    """
    初始化 PaddleOCR 2.x 引擎（向后兼容）。

    Args:
        language: 识别语言 ("ch" 或 "en")

    Returns:
        PaddleOCR 实例
    """
    from paddleocr import PaddleOCR
    return PaddleOCR(
        use_angle_cls=True,
        lang=language,
        show_log=False,
    )


def _extract_text_v3(result) -> str:
    """
    从 PaddleOCR 3.x predict() 结果中提取文字。

    3.x 结果为可迭代对象，每个元素含 .json 属性，
    json 中 rec_texts 字段为识别到的文字列表。

    Args:
        result: predict() 返回的结果对象

    Returns:
        str: 拼接后的文字，无文字返回空字符串
    """
    texts = []
    for res in result:
        # 方式1：通过 .json 属性访问
        if hasattr(res, "json"):
            json_data = res.json
            if isinstance(json_data, dict):
                rec_texts = json_data.get("rec_texts", [])
                for t in rec_texts:
                    t = t.strip() if t else ""
                    if t:
                        texts.append(t)
                if texts:
                    continue
            # 方式2：json 可能是字符串
            elif isinstance(json_data, str):
                import json as _json
                try:
                    data = _json.loads(json_data)
                    rec_texts = data.get("rec_texts", [])
                    for t in rec_texts:
                        t = t.strip() if t else ""
                        if t:
                            texts.append(t)
                except (_json.JSONDecodeError, AttributeError):
                    pass

        # 方式3：直接访问 res 的属性
        if not texts and hasattr(res, "rec_texts"):
            rec_texts = getattr(res, "rec_texts", [])
            for t in rec_texts:
                t = t.strip() if t else ""
                if t:
                    texts.append(t)

    return " ".join(texts)


def _extract_text_v2(result) -> str:
    """
    从 PaddleOCR 2.x ocr() 结果中提取文字。

    2.x 结果格式: [[box, (text, confidence)], ...]

    Args:
        result: ocr() 返回的结果

    Returns:
        str: 拼接后的文字，无文字返回空字符串
    """
    texts = []
    if result and result[0]:
        for line in result[0]:
            if line and len(line) >= 2:
                text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                text = text.strip() if text else ""
                if text:
                    texts.append(text)
    return " ".join(texts)


def _ocr_recognize(frame_paths: List[str], language: str = "ch") -> List[str]:
    """
    使用 PaddleOCR 识别图片中的文字。

    自动适配 PaddleOCR 2.x 和 3.x API。
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

    # 检测 PaddleOCR 版本，选择对应 API
    major_version = _detect_paddleocr_version()

    # 初始化 OCR 引擎
    try:
        if major_version >= 3:
            ocr = _init_paddleocr_v3(language)
        else:
            ocr = _init_paddleocr_v2(language)
    except Exception as e:
        print(f"[!] PaddleOCR 初始化失败: {e}")
        return [""] * len(frame_paths)

    results = []
    for img_path in frame_paths:
        try:
            if major_version >= 3:
                # PaddleOCR 3.x: 使用 predict()
                result = ocr.predict(input=img_path)
                text = _extract_text_v3(result)
            else:
                # PaddleOCR 2.x: 使用 ocr()
                result = ocr.ocr(img_path, cls=True)
                text = _extract_text_v2(result)
            results.append(text)
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
        2. 对每帧进行灰度化+二值化预处理
        3. 用 PaddleOCR 识别每帧文字
        4. 合并相邻相同的识别结果
        5. 生成带时间轴的字幕条目列表

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
    import shutil

    # 1. 截取底部帧（含预处理）
    frames_result = _extract_frames(
        video_path,
        interval=config.OCR_FRAME_INTERVAL,
        bottom_ratio=config.OCR_BOTTOM_REGION_RATIO,
    )

    if not frames_result:
        return None

    frames, temp_dir = frames_result

    if not frames:
        if temp_dir:
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
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # 4. 合并相同条目
    merged = _merge_subtitles(raw_entries, config.OCR_MERGE_THRESHOLD)

    if not merged:
        return None

    return merged
