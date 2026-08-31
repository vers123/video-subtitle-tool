# 视频字幕提取工具

从视频中提取字幕并保存为标准 SRT 文件。支持三种提取方式，按优先级自动回退。

## 功能特点

- **三级回退策略**：自动按优先级尝试提取字幕
  1. ffmpeg 提取内嵌软字幕轨道
  2. PaddleOCR 识别画面底部烧录硬字幕
  3. Whisper 语音转文字
- **自动检测硬件**：根据 GPU 显存自动选择 Whisper 模型
- **批量处理**：扫描 video/ 文件夹下所有支持格式的视频
- **命令行参数**：支持指定单个视频、提取方式、输出路径
- **AI 编程辅助**：内置 AI 上下文文档，兼容 Cursor / Claude Code 等工具

## 环境要求

- Python 3.10+
- ffmpeg（含 ffprobe）
- NVIDIA GPU（可选，无 GPU 时自动降级为 small 模型）

## 安装

项目需要在 Python 虚拟环境中运行，避免污染系统环境。

```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活虚拟环境
#    Linux / macOS:
source venv/bin/activate
#    Windows:
venv\Scripts\activate

# 3. 安装 Python 依赖（在虚拟环境中）
pip install -r requirements.txt

# 4. 确认 ffmpeg 已安装
ffmpeg -version
ffprobe -version

# 5. 检测环境
python main.py --check-env
```

> 注意：所有后续命令（如 `python main.py`）都需要在虚拟环境激活后执行。

## 使用方法

### 批量处理

将视频文件放入 `video/` 文件夹，然后运行：

```bash
python main.py
```

字幕文件将保存到 `subtitles/视频文件名/视频文件名_提取方式.srt`。

### 处理单个视频

```bash
python main.py --input video/demo_video_01.mp4
```

### 指定提取方式

跳过自动回退，直接使用指定方式：

```bash
python main.py --input video/demo_video_01.mp4 --method whisper
```

可选方式：`embedded`（软字幕）、`ocr`（硬字幕 OCR）、`whisper`（语音转文字）

### 指定输出路径

```bash
python main.py --input video/demo_video_01.mp4 --output custom_subtitles/
```

### 仅检测环境

```bash
python main.py --check-env
```

## 支持的视频格式

- MP4
- MKV
- AVI
- MOV

不支持的格式会被跳过并输出警告。

## 目录结构

```
project_root/
├── video/              # 输入视频文件夹
├── subtitles/          # 输出字幕文件夹
│   └── 视频文件名/      # 按视频名命名的子文件夹
│       └── 视频文件名_提取方式.srt
├── modules/            # 功能模块
├── ai_context/         # AI 编程辅助文档
├── venv/               # Python 虚拟环境（不纳入版本控制）
├── .gitignore          # Git 忽略文件配置
├── main.py             # 主程序
├── config.py           # 配置文件
├── requirements.txt    # 依赖清单
└── error.log           # 运行错误日志
```

## 字幕文件命名规则

| 提取方式 | 后缀 | 示例 |
|---------|------|------|
| 软字幕提取 | `_embedded` | `demo_video_01_embedded.srt` |
| OCR 硬字幕 | `_ocr` | `demo_video_02_ocr.srt` |
| 语音转文字 | `_whisper` | `demo_video_03_whisper.srt` |

## 配置说明

修改 `config.py` 可调整以下参数：

- 视频输入/输出路径
- Whisper 模型规格和语言
- OCR 截取区域比例和截帧间隔
- 字幕输出格式和编码
- 临时文件清理策略

## AI 编程辅助

项目内置 AI 上下文文档，位于 `ai_context/` 目录：

- `AI_GUIDE.md` - 项目架构、模块说明、配置参数
- `module_specs/` - 各模块详细接口规格（含测试用例）
- `coding_conventions.md` - 编码规范
- `check_ai_docs.py` - 文档同步检查脚本

Cursor 自动读取 `.cursorrules`，Claude Code 自动读取 `CLAUDE.md`。

检查文档与代码是否同步：

```bash
python ai_context/check_ai_docs.py
```

## 常见问题

**Q: 提示 ffmpeg 未找到？**
A: 请安装 ffmpeg，下载地址：https://ffmpeg.org/download.html

**Q: Whisper 模型下载很慢？**
A: 首次运行需下载模型文件（medium ~1.5GB），后续运行使用本地缓存。可切换为 small 模型减小下载量。

**Q: OCR 识别效果不好？**
A: 可在 `config.py` 中调整 `OCR_BOTTOM_REGION_RATIO`（截取区域比例）和 `OCR_FRAME_INTERVAL`（截帧间隔）。

**Q: 没有 GPU 能用吗？**
A: 可以。程序会自动检测 GPU，无 GPU 时使用 small 模型在 CPU 上运行，速度较慢但功能完整。

**Q: 如何启用 GPU 加速 Whisper？**
A: 安装 CUDA 版 PyTorch（需 NVIDIA 显卡）：
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu126
```
安装后程序会自动检测并使用 GPU。
