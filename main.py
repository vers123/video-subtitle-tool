#!/usr/bin/env python3
"""
视频字幕提取工具 - 主程序

从 video/ 文件夹读取视频，按优先级回退策略提取字幕，
输出标准 SRT 文件到 subtitles/ 文件夹。

用法:
    # 批量处理 video/ 下所有视频
    python main.py

    # 处理单个视频
    python main.py --input video/demo_video_01.mp4

    # 指定提取方式（跳过自动回退）
    python main.py --input video/demo_video_01.mp4 --method whisper

    # 指定输出路径
    python main.py --input video/demo_video_01.mp4 --output custom_subtitles/

    # 仅检测环境
    python main.py --check-env
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from modules.env_check import check_environment, print_env_info, EnvInfo
from modules.file_utils import (
    scan_video_files,
    get_subtitle_path,
    ensure_dir,
    get_temp_audio_path,
    cleanup_temp_files,
    cleanup_temp_dir,
    get_video_name,
)
from modules.subtitle_extractor import extract_embedded
from modules.subtitle_writer import (
    entries_to_srt,
    save_srt,
    write_srt_from_entries,
    write_srt_from_string,
)


def setup_logging(log_file: str) -> logging.Logger:
    """
    配置日志记录器。

    同时输出到文件和终端。

    Args:
        log_file: 日志文件路径

    Returns:
        logging.Logger: 配置好的日志记录器
    """
    logger = logging.getLogger("subtitle_tool")
    logger.setLevel(logging.DEBUG)

    # 文件处理器
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    return logger


def process_video(
    video_path: str,
    output_dir: str,
    method: str,
    env_info: EnvInfo,
    logger: logging.Logger,
) -> str:
    """
    处理单个视频文件，提取字幕。

    按三级回退策略:
        1. 软字幕提取 (embedded)
        2. OCR 硬字幕识别 (ocr)
        3. Whisper 语音转文字 (whisper)

    如果通过 --method 指定了方式，则跳过回退直接使用指定方式。

    Args:
        video_path: 视频文件路径
        output_dir: 字幕输出根目录
        method: 指定的提取方式 (None=自动回退, "embedded"/"ocr"/"whisper")
        env_info: 环境信息
        logger: 日志记录器

    Returns:
        str: 提取方式 ("embedded"/"ocr"/"whisper")，失败返回空字符串
    """
    video_name = get_video_name(video_path)

    # 指定方式处理
    if method == "embedded":
        if _try_embedded(video_path, output_dir, logger):
            return "embedded"
        return ""

    if method == "ocr":
        if _try_ocr(video_path, output_dir, logger):
            return "ocr"
        return ""

    if method == "whisper":
        if _try_whisper(video_path, output_dir, env_info, logger):
            return "whisper"
        return ""

    # 自动回退策略
    # 1. 尝试软字幕
    if _try_embedded(video_path, output_dir, logger):
        return "embedded"

    # 2. 尝试 OCR
    if _try_ocr(video_path, output_dir, logger):
        return "ocr"

    # 3. 尝试 Whisper
    if _try_whisper(video_path, output_dir, env_info, logger):
        return "whisper"

    return ""


def _try_embedded(video_path, output_dir, logger) -> bool:
    """尝试软字幕提取"""
    print("  -> 尝试提取内嵌字幕... ", end="", flush=True)
    try:
        srt_content = extract_embedded(video_path)
        if srt_content:
            output_path = write_srt_from_string(
                srt_content, video_path, output_dir, "embedded"
            )
            print("找到软字幕轨道")
            print(f"  -> 提取完成，保存为 {os.path.basename(output_path)}")
            return True
        else:
            print("无软字幕轨道")
            return False
    except Exception as e:
        print(f"提取失败: {e}")
        logger.error(f"软字幕提取失败 {video_path}: {e}")
        return False


def _try_ocr(video_path, output_dir, logger) -> bool:
    """尝试 OCR 硬字幕识别"""
    print("  -> 尝试 OCR 识别画面硬字幕... ", end="", flush=True)
    try:
        from modules.ocr_subtitle import extract_ocr_subtitles
        entries = extract_ocr_subtitles(video_path)
        if entries:
            output_path = write_srt_from_entries(
                entries, video_path, output_dir, "ocr"
            )
            print("识别成功")
            print(f"  -> 保存为 {os.path.basename(output_path)}")
            return True
        else:
            print("未检测到硬字幕")
            return False
    except ImportError:
        print("PaddleOCR 未安装")
        return False
    except Exception as e:
        print(f"OCR 失败: {e}")
        logger.error(f"OCR 识别失败 {video_path}: {e}")
        return False


def _try_whisper(video_path, output_dir, env_info, logger) -> bool:
    """尝试 Whisper 语音转文字"""
    print("  -> 回退到 Whisper 语音转文字... ", end="", flush=True)
    try:
        from modules.transcriber import Transcriber

        transcriber = Transcriber(
            model_size=env_info.whisper_model,
            language=config.WHISPER_LANGUAGE,
            translate=config.WHISPER_TRANSLATE,
        )

        # 提取音频
        temp_dir = os.path.join(os.path.dirname(video_path), "..", config.TEMP_DIR)
        audio_path = transcriber.extract_audio(video_path, temp_dir)

        # 转录
        entries = transcriber.transcribe(audio_path)
        print("转录完成", flush=True)

        # 保存字幕
        output_path = write_srt_from_entries(
            entries, video_path, output_dir, "whisper"
        )
        print(f"  -> 保存为 {os.path.basename(output_path)}")

        # 清理临时音频
        if config.CLEANUP_TEMP_FILES:
            cleanup_temp_files(audio_path)
            cleanup_temp_dir(os.path.dirname(audio_path))

        return True

    except ImportError:
        print("openai-whisper 未安装")
        return False
    except Exception as e:
        print(f"转录失败: {e}")
        logger.error(f"Whisper 转录失败 {video_path}: {e}")
        # 清理临时文件
        try:
            temp_dir = os.path.join(os.path.dirname(video_path), "..", config.TEMP_DIR)
            cleanup_temp_dir(temp_dir)
        except Exception:
            pass
        return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="视频字幕提取工具 - 从视频中提取字幕并保存为 SRT 文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                                    批量处理 video/ 下所有视频
  python main.py --input video/demo.mp4            处理单个视频
  python main.py --input video/demo.mp4 --method whisper   指定提取方式
  python main.py --output custom_subtitles/        指定输出路径
  python main.py --check-env                       仅检测环境
        """,
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=None,
        help="指定单个视频文件路径（不指定则批量处理 video/ 文件夹）",
    )
    parser.add_argument(
        "--method", "-m",
        type=str,
        default=None,
        choices=["embedded", "ocr", "whisper"],
        help="指定提取方式，跳过自动回退（embedded/ocr/whisper）",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="指定字幕输出路径（默认: subtitles/）",
    )
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="仅检测环境，不执行字幕提取",
    )

    args = parser.parse_args()

    # 项目根目录
    project_root = os.path.dirname(os.path.abspath(__file__))

    # 设置日志
    log_path = os.path.join(project_root, config.ERROR_LOG_FILE)
    logger = setup_logging(log_path)
    logger.info(f"程序启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 环境检测
    print("=== 视频字幕提取工具 ===")
    env_info = check_environment()
    print_env_info(env_info)

    if args.check_env:
        print("环境检测完成。")
        return

    if not env_info.all_ok:
        print("[X] 环境检测未通过，请修复上述错误后重试。")
        logger.error("环境检测未通过")
        return

    # 2. 确定输入和输出路径
    if args.input:
        # 单个视频
        video_path = os.path.abspath(args.input)
        if not os.path.exists(video_path):
            print(f"[X] 视频文件不存在: {video_path}")
            return
        video_files = [video_path]
    else:
        # 批量扫描
        input_dir = os.path.join(project_root, config.VIDEO_INPUT_DIR)
        video_files = scan_video_files(input_dir)

    output_dir = args.output or os.path.join(project_root, config.SUBTITLE_OUTPUT_DIR)

    if not video_files:
        print("[!] 未找到任何视频文件。")
        print(f"    请将视频文件放入 {config.VIDEO_INPUT_DIR}/ 文件夹。")
        print(f"    支持的格式: {', '.join(config.SUPPORTED_VIDEO_EXTENSIONS)}")
        return

    # 3. 扫描结果
    print(f"找到 {len(video_files)} 个视频文件:")
    for i, vf in enumerate(video_files, 1):
        ext = os.path.splitext(vf)[1].upper().lstrip(".")
        print(f"  {i}. {os.path.basename(vf)} ({ext})")
    print()

    # 4. 逐个处理
    success_count = 0
    fail_count = 0

    for i, video_path in enumerate(video_files, 1):
        video_name = get_video_name(video_path)
        print(f"[{i}/{len(video_files)}] {os.path.basename(video_path)}")

        try:
            result_method = process_video(
                video_path=video_path,
                output_dir=output_dir,
                method=args.method,
                env_info=env_info,
                logger=logger,
            )

            if result_method:
                success_count += 1
                logger.info(f"成功: {video_path} (方法: {result_method})")
            else:
                fail_count += 1
                print(f"  -> [X] 所有提取方式均失败")
                logger.error(f"失败: {video_path} - 所有提取方式均失败")
        except Exception as e:
            fail_count += 1
            print(f"  -> [X] 处理异常: {e}")
            logger.error(f"异常: {video_path} - {e}")

        print()

    # 5. 汇总
    print("=== 处理完成 ===")
    print(f"成功: {success_count} / 失败: {fail_count}")
    if success_count > 0:
        print(f"字幕文件已保存至: {output_dir}")
    if fail_count > 0:
        print(f"失败详情请查看: {config.ERROR_LOG_FILE}")

    logger.info(f"处理完成 - 成功: {success_count}, 失败: {fail_count}")


if __name__ == "__main__":
    main()
