"""
硬字幕 OCR 识别模块

截取视频画面底部区域，使用 PaddleOCR 识别烧录字幕，
根据帧时间戳生成带时间轴的字幕条目。

PaddleOCR 3.x (PP-OCRv6) 原生支持复杂背景，无需图片预处理。

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
        "VERBOSE_OUTPUT": True,
    })()


def _verbose(msg: str):
    """详细模式下的调试输出"""
    if getattr(config, "VERBOSE_OUTPUT", True):
        print(msg)


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


def _get_video_dimensions(video_path: str) -> Tuple[int, int]:
    """
    获取视频宽高。

    Args:
        video_path: 视频文件路径

    Returns:
        tuple: (width, height)，获取失败返回 (0, 0)
    """
    try:
        result = subprocess.run(
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
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            if streams:
                return (
                    int(streams[0].get("width", 0)),
                    int(streams[0].get("height", 0)),
                )
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, json.JSONDecodeError):
        pass
    return 0, 0


def _extract_frames(
    video_path: str,
    interval: float,
    bottom_ratio: float,
) -> Tuple[List[Tuple[float, str]], str]:
    """
    从视频底部区域按固定间隔截取帧。

    使用 ffmpeg 截取画面底部 bottom_ratio 比例的区域，
    每隔 interval 秒截取一帧，保存为临时图片文件。
    不做预处理，直接输出原始彩色帧（PaddleOCR 3.x 原生支持复杂背景）。

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
        _verbose("    -> [OCR] 无法获取视频时长")
        return [], ""

    _verbose(f"    -> [OCR] 视频时长: {duration:.1f}s, 截帧间隔: {interval}s")

    # 获取视频尺寸以计算裁剪区域
    width, height = _get_video_dimensions(video_path)
    crop_height = 100
    if height > 0:
        crop_height = max(1, int(height * bottom_ratio))
    _verbose(f"    -> [OCR] 视频尺寸: {width}x{height}, 裁剪高度: {crop_height}px (底部 {bottom_ratio:.0%})")

    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="ocr_frames_")
    frames = []

    # 按间隔截帧
    timestamps = []
    t = 0.0
    while t < duration:
        timestamps.append(t)
        t += interval

    _verbose(f"    -> [OCR] 计划截取 {len(timestamps)} 帧")

    success_count = 0
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
                success_count += 1
            else:
                # 截帧失败时打印 stderr 帮助诊断（仅前几帧）
                if i < 3:
                    stderr = result.stderr.decode("utf-8", errors="replace")[:200] if result.stderr else ""
                    _verbose(f"    -> [OCR] 第 {i} 帧截取失败: rc={result.returncode}, stderr={stderr}")
        except subprocess.TimeoutExpired:
            if i < 3:
                _verbose(f"    -> [OCR] 第 {i} 帧截取超时")
            continue

    _verbose(f"    -> [OCR] 成功截取 {success_count}/{len(timestamps)} 帧")
    return frames, temp_dir


def _detect_paddleocr_version() -> int:
    """
    检测已安装的 PaddleOCR 主版本号。

    Returns:
        int: 主版本号（2 或 3），检测失败返回 3
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

    3.x 移除了 show_log、use_angle_cls 参数。
    PP-OCRv6 默认支持中英日繁，无需指定 lang。

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

    3.x 结果为可迭代对象，每个元素可能是:
    - 含 .json 属性的对象，json 为 dict，含 rec_texts 字段
    - 直接为 dict
    - 含 rec_texts 属性的对象

    Args:
        result: predict() 返回的结果对象

    Returns:
        str: 拼接后的文字，无文字返回空字符串
    """
    texts = []

    for res in result:
        # 尝试多种方式获取文字
        rec_texts = None

        # 方式1: res.json 是 dict
        if hasattr(res, "json"):
            json_data = res.json
            if isinstance(json_data, dict):
                rec_texts = json_data.get("rec_texts")
            elif isinstance(json_data, str):
                import json as _json
                try:
                    data = _json.loads(json_data)
                    if isinstance(data, dict):
                        rec_texts = data.get("rec_texts")
                except (_json.JSONDecodeError, AttributeError):
                    pass

        # 方式2: res 本身是 dict
        if rec_texts is None and isinstance(res, dict):
            rec_texts = res.get("rec_texts")

        # 方式3: res 有 rec_texts 属性
        if rec_texts is None and hasattr(res, "rec_texts"):
            rec_texts = getattr(res, "rec_texts")

        # 方式4: 尝试从 res 的 dict() 转换获取
        if rec_texts is None:
            try:
                res_dict = dict(res) if not isinstance(res, dict) else res
                rec_texts = res_dict.get("rec_texts")
            except (TypeError, ValueError):
                pass

        if rec_texts:
            for t in rec_texts:
                t = t.strip() if t else ""
                if t:
                    texts.append(t)

    return " ".join(texts)


def _extract_text_v2(result) -> str:
    """
    从 PaddleOCR 2.x ocr() 结果中提取文字。

    2.x 结果格式: [[box, (text, confidence)], ...]

    Returns:
        str: 拼接后的文字
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


def _debug_result_structure(result, max_items: int = 1):
    """
    打印 PaddleOCR 结果的结构信息（仅调试用）。

    Args:
        result: predict()/ocr() 返回的结果
        max_items: 最多打印多少个结果项
    """
    try:
        result_list = list(result) if result else []
        _verbose(f"    -> [OCR] 结果类型: {type(result).__name__}, 数量: {len(result_list)}")
        for i, res in enumerate(result_list[:max_items]):
            res_type = type(res).__name__
            attrs = [a for a in dir(res) if not a.startswith("_") and not callable(getattr(res, a, None))]
            _verbose(f"    -> [OCR]   项[{i}] 类型={res_type}, 属性={attrs}")
            if hasattr(res, "json"):
                json_val = res.json
                if isinstance(json_val, dict):
                    _verbose(f"    -> [OCR]   项[{i}] .json keys={list(json_val.keys())}")
                    rec_texts = json_val.get("rec_texts", [])
                    _verbose(f"    -> [OCR]   项[{i}] rec_texts={rec_texts[:3]}...")
    except Exception as e:
        _verbose(f"    -> [OCR] 调试输出异常: {e}")


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

    # 检测 PaddleOCR 版本
    major_version = _detect_paddleocr_version()
    _verbose(f"    -> [OCR] PaddleOCR 版本: {major_version}.x")

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
    recognized_count = 0

    for idx, img_path in enumerate(frame_paths):
        try:
            if major_version >= 3:
                # PaddleOCR 3.x: 使用 predict()
                result = ocr.predict(input=img_path)

                # 第一帧打印调试信息
                if idx == 0:
                    _debug_result_structure(result)

                text = _extract_text_v3(result)
            else:
                # PaddleOCR 2.x: 使用 ocr()
                result = ocr.ocr(img_path, cls=True)
                text = _extract_text_v2(result)

            if text:
                recognized_count += 1

            # 前 5 帧打印识别结果
            if idx < 5:
                preview = text[:50] + "..." if len(text) > 50 else text
                display = '"' + preview + '"' if text else "(空)"
                _verbose(f"    -> [OCR] 帧 {idx}: {display}")

            results.append(text)
        except Exception as e:
            if idx < 5:
                _verbose(f"    -> [OCR] 帧 {idx} 识别异常: {e}")
            results.append("")

    _verbose(f"    -> [OCR] 识别完成: {recognized_count}/{len(frame_paths)} 帧有文字")
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
        1. 按固定间隔截取视频底部画面帧（原始彩色，不预处理）
        2. 用 PaddleOCR 识别每帧文字
        3. 合并相邻相同的识别结果
        4. 生成带时间轴的字幕条目列表

    如果底部区域未识别到文字，会尝试用完整画面再识别一次。

    Args:
        video_path: 视频文件路径

    Returns:
        list[dict] or None: 字幕条目列表 [{"start": float, "end": float, "text": str}]
        识别失败或无字幕时返回 None
    """
    import shutil

    # 1. 截取底部帧
    _verbose("    -> [OCR] 开始截取底部帧...")
    frames_result = _extract_frames(
        video_path,
        interval=config.OCR_FRAME_INTERVAL,
        bottom_ratio=config.OCR_BOTTOM_REGION_RATIO,
    )

    if not frames_result:
        return None

    frames, temp_dir = frames_result

    if not frames:
        _verbose("    -> [OCR] 未截取到任何帧")
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    # 2. OCR 识别
    _verbose(f"    -> [OCR] 开始识别 {len(frames)} 帧...")
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

    if merged:
        _verbose(f"    -> [OCR] 识别到 {len(merged)} 条字幕")
        return merged

    # 5. 底部区域无结果，尝试完整画面（全帧扫描）
    _verbose("    -> [OCR] 底部区域未识别到文字，尝试全帧扫描...")
    return _ocr_full_frame_fallback(video_path)


def _ocr_full_frame_fallback(video_path: str) -> Optional[List[Dict]]:
    """
    全帧扫描回退：截取完整画面帧进行 OCR 识别。

    当底部区域裁剪未识别到文字时，使用完整画面重试。
    为控制性能，截帧间隔加倍。

    Args:
        video_path: 视频文件路径

    Returns:
        list[dict] or None
    """
    import shutil

    duration = _get_video_duration(video_path)
    if duration <= 0:
        return None

    temp_dir = tempfile.mkdtemp(prefix="ocr_full_")
    interval = config.OCR_FRAME_INTERVAL * 2  # 全帧扫描间隔加倍
    frames = []

    timestamps = []
    t = 0.0
    while t < duration:
        timestamps.append(t)
        t += interval

    _verbose(f"    -> [OCR] 全帧扫描: {len(timestamps)} 帧, 间隔 {interval}s")

    for i, ts in enumerate(timestamps):
        img_path = os.path.join(temp_dir, f"full_{i:06d}.png")
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-v", "quiet",
                    "-ss", f"{ts:.3f}",
                    "-i", video_path,
                    "-vframes", "1",
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

    if not frames:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    img_paths = [f[1] for f in frames]
    texts = _ocr_recognize(img_paths, language=config.OCR_LANGUAGE)

    raw_entries = []
    for i, (ts, _) in enumerate(frames):
        text = texts[i] if i < len(texts) else ""
        if text:
            end_ts = ts + interval
            raw_entries.append({
                "start": ts,
                "end": end_ts,
                "text": text,
            })

    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)

    merged = _merge_subtitles(raw_entries, config.OCR_MERGE_THRESHOLD)

    if merged:
        _verbose(f"    -> [OCR] 全帧扫描识别到 {len(merged)} 条字幕")
        return merged

    _verbose("    -> [OCR] 全帧扫描也未识别到文字")
    return None
