# AI_GUIDE.md —— 视频字幕提取工具 AI 编程上下文主文档

> 本文档是 AI 编程助手理解本项目的**核心入口**。在修改、扩展本项目代码前，请务必先通读本文档。
> 文档与代码保持同步是项目硬性要求，模块接口变更后须同步更新 `ai_context/module_specs/` 下的对应规格文件，并运行 `python ai_context/check_ai_docs.py` 校验一致性。

---

## 一、项目概述

### 1.1 项目目标

本项目是一个**视频字幕提取工具**，能够从视频中自动提取字幕并生成标准 SRT 字幕文件。工具采用**三级回退策略（3-tier fallback strategy）**，按照从低成本到高成本的顺序逐级尝试，在保证可用性的前提下最大化提取质量：

| 优先级 | 方法 | 适用场景 | 输出文件 | 成本 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 内嵌软字幕提取（ffmpeg） | 视频自带软字幕流（如 SRT/ASS/PGS） | `xxx_embedded.srt` | 低 |
| 2 | 硬字幕 OCR 识别（PaddleOCR） | 视频画面烧录有硬字幕、无软字幕流 | `xxx_ocr.srt` | 中 |
| 3 | 语音转文字（Whisper） | 既无软字幕、OCR 也无法识别时，对音频转录 | `xxx_whisper.srt` | 高 |

> `xxx` 代表视频文件名（不含扩展名）。每种方法产出独立的字幕文件，便于人工对比与筛选。

### 1.2 设计理念

- **渐进回退**：优先使用无损、快速的软字幕提取；失败后回退到 OCR；OCR 再失败才使用最耗时的 Whisper 语音转录。任一级成功即停止，保证"总能得到一个结果"。
- **配置驱动**：所有可调参数集中在 `config.py`，修改行为无需改动业务代码。
- **模块解耦**：每个提取方式独立成模块，通过统一接口（返回 SRT 字符串或字幕条目列表）串联，便于单独测试与替换。
- **环境自适应**：启动时自动检测 Python 版本、ffmpeg/ffprobe、NVIDIA GPU，并根据显存自动选择 Whisper 模型规格（`medium` 或 `small`）。
- **可观测**：详细进度输出、错误日志（`error.log`）、临时文件自动清理，便于排障。

### 1.3 适用人群与场景

- 需要为视频批量生成字幕的创作者、翻译人员。
- 需要处理多种字幕来源（软字幕 / 硬字幕 / 纯语音）的自动化流水线。
- 需要二次开发、接入更多提取引擎的开发者（参考本文档与 `module_specs/`）。

---

## 二、系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                              │
│  (入口：环境检测 -> 扫描视频 -> 三级回退提取 -> 写入字幕)        │
└──────────────┬──────────────────────────────────────────────┘
               │
   ┌───────────┼───────────────────────────────────┐
   │           │                                   │
   ▼           ▼                                   ▼
┌─────────────────────────┐        ┌──────────────────────────┐
│  env_check.py           │        │  file_utils.py            │
│  环境检测 (Python/       │        │  文件扫描 / 路径管理 /      │
│  ffmpeg/GPU)             │        │  临时文件清理               │
└─────────────────────────┘        └──────────────────────────┘
               │
   ┌───────────┴────────────────────────────────────────────────┐
   │                    三级回退提取链                            │
   │                                                            │
   │  ① subtitle_extractor.py   软字幕提取 (ffprobe + ffmpeg)    │
   │        │ 成功? ─ 否 ─┐                                      │
   │        是           ▼                                       │
   │  ② ocr_subtitle.py        硬字幕 OCR (PaddleOCR)            │
   │        │ 成功? ─ 否 ─┐                                      │
   │        是           ▼                                       │
   │  ③ transcriber.py         语音转文字 (Whisper)               │
   │        │                                                   │
   │        是                                                   │
   ▼                                                           │
┌─────────────────────────┐                                    │
│  subtitle_writer.py     │   统一字幕格式化与写入                │
│  (SRT 格式化 / 保存)     │                                    │
└─────────────────────────┘                                    │
                                                               │
                      配置层: config.py                         │
```

### 2.2 三级回退策略详解

回退逻辑由 `main.py` 编排，每一级返回结果后由主流程判定是否继续回退：

```
对每个视频文件 V:
  step1 = subtitle_extractor.extract_embedded(V)
  if step1 is not None:
      写入 xxx_embedded.srt -> 结束（成功）
  else:
      step2 = ocr_subtitle.extract_ocr_subtitles(V)
      if step2 is not None:
          写入 xxx_ocr.srt -> 结束（成功）
      else:
          提取音频 -> transcriber.transcribe(audio) -> list[dict]
          写入 xxx_whisper.srt -> 结束（兜底，必有结果）
```

**关键约定**：

- 前两级（embedded / ocr）返回 `None` 表示"未提取到字幕"，触发回退；返回非空表示成功，立即停止。
- 第三级（whisper）是兜底手段，**不返回 None**，始终产出结果（即使识别为空也会生成空 SRT），确保流程有确定终点。
- `DEFAULT_METHOD` 配置为 `None` 时启用上述自动回退；若设为 `"embedded"` / `"ocr"` / `"whisper"`，则只执行指定方式，便于单独调试。

### 2.3 数据流

```
video/*.mp4
   │
   ├─(软字幕)─> ffprobe 探测流 ─> ffmpeg 抽取 ─> SRT 字符串 ──────────────┐
   │                                                                      │
   ├─(硬字幕)─> 截取底部帧 ─> PaddleOCR ─> [{start,end,text}] ────────────┤
   │                                                                      │
   └─(语音)──> ffmpeg 提取 WAV ─> Whisper 推理 ─> [{start,end,text}] ────┤
                                                                          ▼
                                          subtitle_writer.entries_to_srt / save_srt
                                                                          │
                                                                subtitles/<视频名>/<视频名>_<method>.srt
```

### 2.4 GPU 与模型选择

- 启动时 `env_check._check_gpu()` 通过 `nvidia-smi` 读取显卡型号与显存。
- 显存 >= `WHISPER_MODEL_VRAM_THRESHOLD`（默认 6GB）→ 使用 `WHISPER_MODEL_PREFERRED`（`medium`）。
- 显存不足或无 GPU → 使用 `WHISPER_MODEL_FALLBACK`（`small`）。
- OCR（PaddleOCR）在可用时优先使用 GPU（`GPU_DEVICE`），无 GPU 则回退 CPU。

---

## 三、目录结构

```
project_root/
├── video/                  # 输入视频目录（放入待处理视频，支持子目录递归扫描）
├── subtitles/              # 字幕输出根目录（英文名，不使用中文路径）
│   └── <视频名>/           # 每个视频一个子文件夹
│       └── <视频名>_<method>.srt   # 例：demo_embedded.srt
├── temp/                   # 临时文件目录（处理中间产物，运行后可自动清理）
├── modules/                # 业务模块包
│   ├── __init__.py         # 包初始化，声明模块结构
│   ├── env_check.py        # 环境检测（Python/ffmpeg/GPU）
│   ├── file_utils.py       # 文件扫描、路径管理、清理
│   ├── subtitle_extractor.py  # 软字幕提取（ffprobe + ffmpeg）
│   ├── ocr_subtitle.py     # 硬字幕 OCR（PaddleOCR）
│   ├── transcriber.py      # Whisper 语音转文字
│   └── subtitle_writer.py  # SRT 格式化与写入
├── ai_context/             # AI 编程上下文文档
│   ├── AI_GUIDE.md         # 本文件：项目主上下文文档
│   ├── module_specs/       # 各模块接口规格
│   │   ├── env_check.md
│   │   ├── subtitle_extractor.md
│   │   ├── ocr_subtitle.md
│   │   ├── transcriber.md
│   │   ├── subtitle_writer.md
│   │   └── file_utils.md
│   ├── coding_conventions.md   # 编码规范
│   └── check_ai_docs.py    # 文档与代码一致性校验脚本
├── .cursorrules            # Cursor 编辑器规则
├── CLAUDE.md               # Claude 代码助手规则
├── main.py                 # 程序入口
├── config.py               # 集中配置
├── requirements.txt        # Python 依赖清单
├── error.log               # 运行错误日志（运行时生成）
└── README.md               # 项目说明
```

**目录约定说明**：

- `video/`：输入目录。脚本递归扫描其中所有支持格式文件，非视频文件会被跳过并给出警告。
- `subtitles/`：输出目录。**使用英文名**以避免跨平台中文路径问题。每个视频对应一个同名子目录，字幕文件以 `<视频名>_<method>.srt` 命名。
- `temp/`：临时目录。存放提取的中间 WAV 音频等文件。`CLEANUP_TEMP_FILES=True` 时处理完成后自动清理。
- `ai_context/`：AI 助手专用文档区，**普通用户无需关心**，开发与修改代码时必读。

---

## 四、模块说明

每个模块的详细接口规格见 `ai_context/module_specs/<module>.md`。此处给出概览，AI 助手修改具体实现前应同时参阅对应规格文件与 `coding_conventions.md`。

### 4.1 config.py（配置中心）

集中管理所有可配置参数。模块在需要时通过 `import config` 读取，部分模块带有 fallback 默认值以支持单独运行调试。完整参数清单见本文档「六、配置参数」一节。

### 4.2 env_check.py（环境检测）

负责启动前环境自检：Python 版本（>= 3.10）、ffmpeg/ffprobe 可用性、NVIDIA GPU 型号与显存，并据此选择 Whisper 模型规格。

公共接口：
- `EnvInfo`（dataclass）：环境检测结果容器，含 `all_ok` 属性、`warnings`/`errors` 列表。
- `check_environment() -> EnvInfo`：执行完整检测。
- `print_env_info(info: EnvInfo) -> None`：格式化打印检测结果。

### 4.3 file_utils.py（文件管理）

负责文件扫描、路径计算、目录创建与临时文件清理。

公共接口：
- `scan_video_files(input_dir) -> list[str]`：递归扫描支持格式的视频，返回绝对路径列表（按名排序）。
- `get_subtitle_path(video_path, output_dir, method) -> str`：按 `output_dir/<视频名>/<视频名>_<method>.srt` 生成路径。
- `ensure_dir(path) -> None`：确保目录存在。
- `cleanup_temp_files(*paths) -> None`：安全删除指定临时文件（不存在则跳过）。
- `is_supported_video(filepath) -> bool`：判断是否为支持格式。
- `get_video_name(video_path) -> str`：取文件名（去扩展名）。
- `get_temp_audio_path(video_path, temp_dir) -> str`：生成临时 WAV 路径。
- `cleanup_temp_dir(temp_dir) -> None`：清理整个临时目录。

### 4.4 subtitle_extractor.py（软字幕提取，第 1 级）

使用 `ffprobe` 探测视频内嵌字幕流，若存在则用 `ffmpeg` 抽取并转换为 SRT。

公共接口：
- `extract_embedded(video_path) -> Optional[str]`：返回 SRT 字符串；无软字幕流或抽取失败返回 `None`（触发回退）。

> 依赖 ffprobe。若 ffprobe 缺失，`env_check` 会给出警告，本模块将直接返回 `None` 走回退。

### 4.5 ocr_subtitle.py（硬字幕 OCR，第 2 级）

使用 PaddleOCR 识别视频中**烧录在画面底部**的硬字幕。按 `OCR_FRAME_INTERVAL` 截帧，截取底部 `OCR_BOTTOM_REGION_RATIO` 比例区域，OCR 后按 `OCR_MERGE_THRESHOLD` 合并相邻相同文本。

公共接口：
- `extract_ocr_subtitles(video_path) -> Optional[list[dict]]`：返回字幕条目列表 `[{start, end, text}, ...]`；识别失败或无文本返回 `None`（触发回退）。

### 4.6 transcriber.py（语音转文字，第 3 级 / 兜底）

封装 OpenAI Whisper，将视频音频转录为带时间戳文本。模型规格由环境检测决定。

公共接口：
- `Transcriber` 类：
  - `__init__(model_size, language, translate)`：初始化 Whisper 模型。
  - `transcribe(audio_path) -> list[dict]`：转录音频，返回 `[{start, end, text}, ...]`。

> 调用前需先用 ffmpeg 从视频提取 16kHz 单声道 WAV（`AUDIO_SAMPLE_RATE` / `AUDIO_CHANNELS`），路径由 `file_utils.get_temp_audio_path` 生成。

### 4.7 subtitle_writer.py（字幕格式化与写入）

将各模块产出的字幕条目统一格式化为 SRT 并写入文件。

公共接口：
- `entries_to_srt(entries) -> str`：将 `[{start, end, text}, ...]` 转为 SRT 字符串。
- `save_srt(content, path) -> str`：将 SRT 内容写入指定路径，返回路径。
- `format_timestamp(seconds) -> str`：秒数转 SRT 时间戳 `HH:MM:SS,mmm`。

### 4.8 main.py（入口编排）

串联各模块完成端到端流程：

1. 调用 `env_check.check_environment()` 自检，失败则中止并提示。
2. 调用 `file_utils.scan_video_files()` 扫描 `video/`。
3. 逐个视频执行三级回退提取（见 2.2），写入 `subtitles/`。
4. 处理完成后清理 `temp/`（若配置开启），错误写入 `error.log`。

---

## 五、模块接口速查表

| 模块 | 函数/类 | 签名 | 返回说明 |
| :--- | :--- | :--- | :--- |
| env_check | EnvInfo | dataclass | 环境信息容器 |
| env_check | check_environment | `() -> EnvInfo` | 完整检测结果 |
| env_check | print_env_info | `(info: EnvInfo) -> None` | 打印结果 |
| file_utils | scan_video_files | `(input_dir: str) -> list[str]` | 视频绝对路径列表 |
| file_utils | get_subtitle_path | `(video_path, output_dir, method) -> str` | 字幕文件完整路径 |
| file_utils | ensure_dir | `(path: str) -> None` | 创建目录 |
| file_utils | cleanup_temp_files | `(*paths: str) -> None` | 删除临时文件 |
| file_utils | is_supported_video | `(filepath: str) -> bool` | 是否支持格式 |
| file_utils | get_video_name | `(video_path: str) -> str` | 文件名（无扩展名） |
| file_utils | get_temp_audio_path | `(video_path, temp_dir) -> str` | 临时 WAV 路径 |
| subtitle_extractor | extract_embedded | `(video_path) -> Optional[str]` | SRT 字符串或 None |
| ocr_subtitle | extract_ocr_subtitles | `(video_path) -> Optional[list[dict]]` | 条目列表或 None |
| transcriber | Transcriber.__init__ | `(model_size, language, translate)` | 初始化 |
| transcriber | Transcriber.transcribe | `(audio_path) -> list[dict]` | 条目列表 |
| subtitle_writer | entries_to_srt | `(entries) -> str` | SRT 字符串 |
| subtitle_writer | save_srt | `(content, path) -> str` | 写入路径 |
| subtitle_writer | format_timestamp | `(seconds) -> str` | `HH:MM:SS,mmm` |

> 字幕条目字典结构统一为 `{"start": float, "end": float, "text": str}`，`start`/`end` 单位为秒。

---

## 六、配置参数

所有参数定义于 `config.py`。修改这些参数即可调整程序行为，无需改动业务代码。

### 6.1 路径配置

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `VIDEO_INPUT_DIR` | `"video"` | 视频输入目录（相对项目根） |
| `SUBTITLE_OUTPUT_DIR` | `"subtitles"` | 字幕输出目录（英文名，相对项目根） |
| `TEMP_DIR` | `"temp"` | 临时文件目录 |
| `ERROR_LOG_FILE` | `"error.log"` | 错误日志文件路径 |

### 6.2 视频格式配置

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `SUPPORTED_VIDEO_EXTENSIONS` | `[".mp4", ".mkv", ".avi", ".mov"]` | 支持的视频扩展名 |

### 6.3 Whisper 语音转文字配置

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `WHISPER_MODEL_PREFERRED` | `"medium"` | 显存充足时使用的模型 |
| `WHISPER_MODEL_FALLBACK` | `"small"` | 显存不足/无 GPU 时使用的模型 |
| `WHISPER_MODEL_VRAM_THRESHOLD` | `6` | 显存阈值（GB），低于此值用 fallback |
| `WHISPER_LANGUAGE` | `None` | 目标语言，`None` 自动检测 |
| `WHISPER_TRANSLATE` | `False` | 是否翻译为英文 |
| `AUDIO_SAMPLE_RATE` | `16000` | 音频采样率（Hz），Whisper 推荐 16kHz |
| `AUDIO_CHANNELS` | `1` | 音频声道数（单声道） |

### 6.4 OCR 硬字幕识别配置

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `OCR_BOTTOM_REGION_RATIO` | `0.15` | 截取底部画面比例（15%） |
| `OCR_FRAME_INTERVAL` | `1.0` | 截帧间隔（秒） |
| `OCR_LANGUAGE` | `"ch"` | OCR 语言（`"ch"` 中文 / `"en"` 英文） |
| `OCR_MERGE_THRESHOLD` | `2.0` | 相邻相同文本合并阈值（秒） |

### 6.5 字幕输出配置

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `OUTPUT_FORMAT` | `"srt"` | 输出格式（目前仅支持 SRT） |
| `SRT_ENCODING` | `"utf-8"` | SRT 文件编码 |
| `SUBTITLE_SUFFIX` | `{"embedded": "_embedded", "ocr": "_ocr", "whisper": "_whisper"}` | 各方法输出后缀 |

### 6.6 运行配置

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `CLEANUP_TEMP_FILES` | `True` | 完成后清理临时文件 |
| `VERBOSE_OUTPUT` | `True` | 显示详细进度 |
| `GPU_DEVICE` | `0` | GPU 设备号（`-1` 表示 CPU） |
| `DEFAULT_METHOD` | `None` | 默认提取方式；`None` 走自动回退，否则指定单一方式 |

---

## 七、依赖清单

依赖定义于 `requirements.txt`，安装命令：

```bash
pip install -r requirements.txt --break-system-packages
```

| 依赖 | 版本要求 | 用途 |
| :--- | :--- | :--- |
| `openai-whisper` | `>=20231117` | 语音转文字（第 3 级） |
| `ffmpeg-python` | `>=0.2.0` | ffmpeg Python 封装（软字幕提取、音频抽取） |
| `paddleocr` | `>=2.7.0` | 硬字幕 OCR（第 2 级） |
| `paddlepaddle` | `>=2.6.0` | PaddleOCR 后端深度学习框架 |
| `pysrt` | `>=1.1.2` | SRT 字幕文件读写 |
| `argparse` | 标准库 | 命令行参数解析 |
| `logging` | 标准库 | 日志记录 |

**系统级依赖**（需单独安装，非 pip）：

- **ffmpeg**：视频解码、软字幕抽取、音频提取。安装见 https://ffmpeg.org/download.html
- **ffprobe**：随 ffmpeg 一同分发，用于探测内嵌字幕流。
- **NVIDIA 驱动 + CUDA**（可选）：启用 GPU 加速 Whisper / PaddleOCR，显著提升速度。无 GPU 时自动回退 CPU。

---

## 八、运行说明

### 8.1 环境准备

1. 安装 Python >= 3.10。
2. 安装 ffmpeg / ffprobe（确保在系统 PATH 中可被 `ffmpeg` / `ffprobe` 命令调用）。
3. （可选）安装 NVIDIA 驱动与 CUDA 以启用 GPU 加速。
4. 安装 Python 依赖：`pip install -r requirements.txt --break-system-packages`。

### 8.2 放入视频

将待处理视频放入 `video/` 目录（支持 `.mp4` / `.mkv` / `.avi` / `.mov`，支持子目录）。

### 8.3 运行

```bash
# 默认运行（三级自动回退）
python main.py

# 指定单一提取方式（调试用）
python main.py --method ocr        # 仅 OCR
python main.py --method embedded   # 仅软字幕
python main.py --method whisper    # 仅语音转文字

# 仅检测环境，不执行提取
python main.py --check-env
```

### 8.4 查看输出

字幕生成于 `subtitles/<视频名>/<视频名>_<method>.srt`。运行错误记录于 `error.log`。

### 8.5 文档一致性校验

修改代码或接口后，运行校验脚本确认 `module_specs/` 与代码同步：

```bash
python ai_context/check_ai_docs.py
```

脚本会提取 `modules/` 与 `config.py` 中的函数/类签名，与 `module_specs/*.md` 中记录的接口对比，输出不一致项（缺失文档、过期文档、签名不匹配）。退出码非 0 表示存在不一致。

---

## 九、字幕格式规范

### 9.1 SRT 格式

输出统一为 **SubRip（SRT）** 格式，UTF-8 编码。每条字幕由 4 部分组成：

```
1
00:00:01,000 --> 00:00:03,500
这是第一条字幕文本

2
00:00:04,000 --> 00:00:06,200
这是第二条字幕文本
```

- 第 1 行：序号（从 1 递增）。
- 第 2 行：时间轴 `开始 --> 结束`，格式 `HH:MM:SS,mmm`（注意毫秒前是**逗号**）。
- 第 3 行起：字幕文本（可多行）。
- 条目间用空行分隔。

### 9.2 时间戳格式

`format_timestamp(seconds)` 将浮点秒数转为 `HH:MM:SS,mmm`：

- `seconds = 3.5` → `00:00:03,500`
- `seconds = 3723.456` → `01:02:03,456`

### 9.3 字幕条目字典结构

各模块（ocr / transcriber）产出的条目统一为字典：

```python
{
    "start": 1.0,   # 开始时间（秒，float）
    "end":   3.5,   # 结束时间（秒，float）
    "text":  "字幕文本"
}
```

`subtitle_writer.entries_to_srt` 接收该结构的列表，输出标准 SRT。`extract_embedded` 直接返回已是 SRT 格式的字符串，跳过 `entries_to_srt`。

### 9.4 文件命名

```
subtitles/<视频名>/<视频名>_<method>.srt
```

- `<视频名>`：视频文件名去掉扩展名（如 `demo.mp4` → `demo`）。
- `<method>`：`embedded` / `ocr` / `whisper`，对应后缀 `_embedded` / `_ocr` / `_whisper`。

---

## 十、AI 助手工作指引

修改本项目代码时，AI 助手应遵循以下流程：

1. **先读本文档**：理解整体架构与三级回退策略，明确要改动的模块在流程中的位置。
2. **查阅模块规格**：修改某模块前，先读 `ai_context/module_specs/<module>.md`，确保改动符合既定接口契约。
3. **遵守编码规范**：参照 `ai_context/coding_conventions.md`（命名、PEP 8、注释、错误处理、日志）。
4. **改完同步文档**：若改动影响公共接口（函数签名、返回值、参数语义），同步更新对应 `module_specs`，并运行 `check_ai_docs.py` 校验。
5. **保持配置驱动**：新增可调参数加入 `config.py` 并在本文档「六、配置参数」补充说明，勿在业务代码硬编码。
6. **三级回退不可破坏**：任何改动都不得使回退链中断——前级失败必须返回 `None` 以触发下一级，末级（Whisper）必须保证产出。
