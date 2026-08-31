"""
语音转文字模块

使用 ffmpeg 从视频中提取音轨，
用 OpenAI Whisper 模型进行语音转文字。

公共接口:
    Transcriber 类
        __init__(model_size, language, translate)
        extract_audio(video_path, temp_dir) -> str
        transcribe(audio_path) -> list[dict]
"""

import os
import subprocess
from typing import Optional, List, Dict

try:
    import config
except ImportError:
    config = type("config", (), {
        "AUDIO_SAMPLE_RATE": 16000,
        "AUDIO_CHANNELS": 1,
        "WHISPER_LANGUAGE": None,
        "WHISPER_TRANSLATE": False,
        "WHISPER_MODEL_PREFERRED": "medium",
        "GPU_DEVICE": 0,
    })()


class Transcriber:
    """
    Whisper 语音转文字器。

    封装 Whisper 模型加载、音频提取、转录功能。

    属性:
        model_size: Whisper 模型规格 ("tiny"/"base"/"small"/"medium"/"large-v3")
        language: 目标语言 (None 表示自动检测)
        translate: 是否翻译为英文
        _model: Whisper 模型实例（延迟加载）
    """

    def __init__(
        self,
        model_size: str = "medium",
        language: Optional[str] = None,
        translate: bool = False,
    ):
        """
        初始化转录器。

        模型不会在构造时加载，而是在首次调用 transcribe() 时延迟加载。

        Args:
            model_size: Whisper 模型规格
            language: 目标语言代码 (None=自动检测, "zh"=中文, "en"=英文)
            translate: 是否翻译为英文 (True 时输出英文翻译)
        """
        self.model_size = model_size
        self.language = language
        self.translate = translate
        self._model = None

    def _load_model(self):
        """
        延迟加载 Whisper 模型。

        首次调用时加载模型到内存/GPU，后续调用复用。
        自动检测 CUDA 可用性，有 GPU 时使用 GPU 加速。

        Raises:
            ImportError: whisper 未安装
            RuntimeError: 模型加载失败
        """
        if self._model is not None:
            return

        try:
            import whisper
        except ImportError:
            raise ImportError(
                "openai-whisper 未安装。请运行: pip install openai-whisper"
            )

        # 检测 CUDA 可用性
        try:
            import torch
            cuda_available = torch.cuda.is_available()
        except ImportError:
            cuda_available = False

        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
            print(f"    -> 加载 Whisper 模型: {self.model_size} (GPU: {gpu_name}) ...")
        else:
            print(f"    -> 加载 Whisper 模型: {self.model_size} (CPU 模式) ...")
            print("    -> [!] 未检测到 GPU 加速，转录速度较慢")
            print("    -> [!] 如需 GPU 加速，请安装 CUDA 版 PyTorch:")
            print("    ->     pip install torch --index-url https://download.pytorch.org/whl/cu126")

        self._model = whisper.load_model(self.model_size)
        print(f"    -> 模型加载完成")

    def extract_audio(self, video_path: str, temp_dir: str) -> str:
        """
        从视频中提取音轨为 WAV 文件。

        使用 ffmpeg 提取 16kHz 单声道 PCM WAV，
        这是 Whisper 推荐的音频格式。

        Args:
            video_path: 视频文件路径
            temp_dir: 临时文件目录

        Returns:
            str: 临时 WAV 文件路径

        Raises:
            RuntimeError: ffmpeg 提取失败
            FileNotFoundError: 视频文件不存在
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        os.makedirs(temp_dir, exist_ok=True)

        video_name = os.path.splitext(os.path.basename(video_path))[0]
        audio_path = os.path.join(temp_dir, f"{video_name}.wav")

        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-v", "quiet",
                    "-i", video_path,
                    "-vn",
                    "-acodec", "pcm_s16le",
                    "-ar", str(config.AUDIO_SAMPLE_RATE),
                    "-ac", str(config.AUDIO_CHANNELS),
                    "-y",
                    audio_path,
                ],
                capture_output=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"音频提取超时: {video_path}")

        if result.returncode != 0 or not os.path.exists(audio_path):
            raise RuntimeError(
                f"音频提取失败: {video_path}\n"
                f"ffmpeg 错误: {result.stderr.decode('utf-8', errors='replace')[:500]}"
            )

        return audio_path

    def transcribe(self, audio_path: str) -> List[Dict]:
        """
        使用 Whisper 转录音频文件。

        自动检测语言（除非指定），不做翻译（除非开启 translate）。
        输出为带时间戳的字幕条目列表。

        Args:
            audio_path: WAV 音频文件路径

        Returns:
            list[dict]: 字幕条目列表，每项格式:
                {"start": float, "end": float, "text": str}

        Raises:
            RuntimeError: 转录失败
            FileNotFoundError: 音频文件不存在
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 延迟加载模型
        self._load_model()

        # 执行转录
        try:
            result = self._model.transcribe(
                audio_path,
                language=self.language,
                task="translate" if self.translate else "transcribe",
                verbose=False,
            )
        except Exception as e:
            raise RuntimeError(f"Whisper 转录失败: {e}")

        # 提取字幕条目
        entries = []
        for segment in result.get("segments", []):
            text = segment.get("text", "").strip()
            if text:
                entries.append({
                    "start": float(segment.get("start", 0.0)),
                    "end": float(segment.get("end", 0.0)),
                    "text": text,
                })

        return entries
