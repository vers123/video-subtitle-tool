"""
视频字幕提取工具 - 模块包

模块结构:
    env_check          - 环境检测（Python/ffmpeg/GPU）
    file_utils          - 文件扫描、路径管理、清理
    subtitle_extractor  - 软字幕提取（ffprobe + ffmpeg）
    ocr_subtitle        - 硬字幕 OCR 识别（PaddleOCR）
    transcriber         - Whisper 语音转文字
    subtitle_writer     - SRT 格式化与写入
"""
