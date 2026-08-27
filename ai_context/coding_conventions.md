# coding_conventions.md —— 编码规范

> 本规范是本项目的**强制编码标准**。所有新增与修改代码须遵循本文档。
> 规范基于 PEP 8，并结合项目实际（中文注释、配置驱动、多级回退）做了细化。
> AI 助手在生成代码前必须先阅读本文档；`check_ai_docs.py` 会校验接口文档与代码的一致性，但不校验风格，风格由人工与工具（如 `flake8`/`ruff`）把关。

---

## 一、总体原则

1. **PEP 8 为基线**：缩进 4 空格、行宽不超过 100 字符、每级缩进 4 个空格，禁用 Tab。
2. **Python 版本**：面向 Python 3.10+，可使用 `dataclass`、类型提示（`list[...]`、`Optional[...]`、`tuple` 解包）等新语法。
3. **中文友好**：注释、docstring、终端输出、错误提示一律使用**中文**；标识符（变量名、函数名、类名）一律使用**英文**。
4. **配置驱动**：可调参数放 `config.py`，业务代码不硬编码魔法值。
5. **稳健优先**：外部依赖（ffmpeg、GPU、模型）可能缺失，代码须优雅降级而非崩溃。

---

## 二、命名规范

### 2.1 命名风格总表

| 类别 | 风格 | 示例 | 说明 |
| :--- | :--- | :--- | :--- |
| 变量、函数、方法 | `snake_case` | `video_path`、`extract_embedded` | 全小写，下划线分词 |
| 类 | `PascalCase` | `EnvInfo`、`Transcriber` | 首字母大写 |
| 常量 / 配置项 | `UPPER_SNAKE_CASE` | `VIDEO_INPUT_DIR`、`SRT_ENCODING` | 全大写，下划线分词 |
| 私有函数 / 内部辅助 | `_leading_underscore` | `_check_python`、`_select_whisper_model` | 模块内部使用，不对外暴露 |
| 模块文件名 | `snake_case.py` | `env_check.py`、`file_utils.py` | 全小写 |
| 字典键 / 参数键 | `snake_case` | `{"start": ..., "end": ...}` | 与变量风格一致 |
| 布尔变量 / 返回布尔的方法 | `is_`/`has_`/`should_` 前缀 | `is_supported_video`、`has_gpu` | 表意明确 |

### 2.2 命名细则

- **函数名用动词开头**：`extract_embedded`、`scan_video_files`、`format_timestamp`、`save_srt`。
- **避免缩写**：除非是行业通用缩写（`OCR`、`SRT`、`WAV`、`GPU`、`VRAM`），否则写全称。`video_path` 优于 `vp`。
- **类型语义命名**：返回路径的变量以 `_path` 结尾（`video_path`、`audio_path`）；列表以复数结尾（`entries`、`video_files`）；布尔以 `ok`/`has_`/`is_` 表达（`ffmpeg_ok`、`has_gpu`）。
- **不使用中文拼音命名**，标识符必须英文。
- **单字母变量**仅限于循环索引（`i`、`j`）或数学上下文，其余禁用。

### 2.3 模块 / 接口契约命名

- 每个模块在文件顶部 docstring 声明其**公共接口**（见现有 `env_check.py`、`file_utils.py`）：
  ```python
  """
  环境检测模块

  公共接口:
      EnvInfo (dataclass)            - 环境信息
      check_environment() -> EnvInfo - 执行环境检测
  """
  ```
- 公共接口变更后须同步 `module_specs/<module>.md`，否则 `check_ai_docs.py` 报告不一致。

---

## 三、PEP 8 风格细则

### 3.1 排版

- **缩进**：4 个空格，禁用 Tab。
- **行宽**：不超过 100 字符。超长时在运算符后换行，续行缩进 4 空格或与首行括号对齐。
- **空行**：
  - 顶层函数 / 类定义之间空 **2 行**。
  - 类内方法之间空 **1 行**。
  - 方法内逻辑块之间视情况空 1 行。
- **导入**：顺序为「标准库 → 第三方库 → 本地模块」，每组之间空 1 行。优先 `import` 整个模块而非 `from x import *`。

```python
# 正确示例
import os
import shutil
import subprocess
from typing import List, Optional

import ffmpeg

import config
```

### 3.2 空格

- 逗号后加空格：`[1, 2, 3]` 而非 `[1,2,3]`。
- 运算符两侧加空格：`a = b + 1`。
- 括号内侧紧贴：`func(x)` 而非 `func( x )`。
- 默认参数等号两侧**不加空格**：`def f(a, b=1):`。

### 3.3 引号

- 统一使用**双引号**字符串：`"中文文本"`（与现有代码一致）。
- 文档字符串（docstring）使用三双引号 `"""..."""`。

### 3.4 文件结尾

- 文件以一个换行符结尾，不保留多余空行。

---

## 四、类型提示

- **公共函数必须标注类型**（参数与返回值），便于 `check_ai_docs.py` 提取与文档对比。
- 内部私有函数可省略，但建议标注。
- 使用 3.10+ 现代语法：`list[str]` 而非 `List[str]`（现有代码用 `List` 兼顾，新代码推荐小写内置泛型）。
- 可选返回用 `Optional[...]` 或 `... | None`。

```python
# 正确：公共接口带类型
def get_subtitle_path(video_path: str, output_dir: str, method: str) -> str:
    ...

def extract_embedded(video_path) -> Optional[str]:
    ...
```

---

## 五、注释与文档字符串格式

### 5.1 文件头 docstring

每个 `.py` 文件顶部必须有模块 docstring：简述模块职责，并列出公共接口签名。

```python
"""
环境检测模块

检测系统环境：Python 版本、ffmpeg、NVIDIA GPU。
根据 GPU 情况自动选择 Whisper 模型规格。

公共接口:
    EnvInfo (dataclass)        - 环境信息
    check_environment() -> EnvInfo - 执行环境检测
"""
```

### 5.2 函数 docstring

公共函数使用 Google 风格 docstring（中文），包含：一句话功能说明、`Args`、`Returns`，必要时加 `Raises`。

```python
def scan_video_files(input_dir: str) -> List[str]:
    """
    扫描指定目录下的所有支持格式的视频文件。

    不支持的格式会输出警告信息并跳过。
    递归扫描子目录。

    Args:
        input_dir: 视频输入目录路径

    Returns:
        list[str]: 视频文件路径列表（绝对路径），按文件名排序
    """
```

### 5.3 内联注释

- 注释与代码同语言：本项目注释用**中文**。
- 注释解释「为什么」而非「是什么」；代码本身能表意处不加冗余注释。
- 行内注释与代码间至少 2 空格：`x = x + 1  # 补偿偏移`。
- 分隔注释块用 `# === 标题 ===` 风格（见 `config.py` 分节）。

```python
# ============================================================
# Whisper 语音转文字配置
# ============================================================
```

### 5.4 TODO / FIXME

- 使用 `# TODO: ...` / `# FIXME: ...` 标记待办，须附简短说明。

---

## 六、错误处理模式

### 6.1 总则

- **不静默吞异常**：`except` 块必须至少记录日志或打印警告，禁止空 `except:` 或 `pass` 掩盖问题。
- **精确捕获**：捕获具体异常类型（`OSError`、`subprocess.TimeoutExpired`、`ValueError`），避免裸 `except Exception`。
- **降级而非崩溃**：外部依赖缺失时返回 `None` / 安全默认值，让上层回退链接管，而非抛异常终止。

### 6.2 回退链相关

三级回退要求前两级失败时返回 `None`：

```python
def extract_embedded(video_path) -> Optional[str]:
    try:
        ...  # 抽取逻辑
        return srt_string
    except FFmpegError:
        # 记录原因，返回 None 触发回退
        print(f"[!] 软字幕提取失败: {e}")
        return None
```

- 兜底层（Whisper）不返回 `None`，即使识别为空也产出（可能为空）SRT，保证流程终点确定。
- `env_check` 将致命问题放入 `EnvInfo.errors`，非致命放入 `warnings`，由 `main.py` 决定是否中止。

### 6.3 子进程与外部命令

- 调用 `subprocess` 时设置 `timeout`，避免永久挂起（见 `_check_gpu` 的 `timeout=10`）。
- 使用 `capture_output=True` 捕获输出，按 `returncode` 判定成功。

### 6.4 文件操作

- 删除 / 清理使用安全模式：先判断存在再删，删除失败仅警告不抛（见 `cleanup_temp_files`）。
- 目录创建使用 `os.makedirs(path, exist_ok=True)` 幂等。

### 6.5 配置 fallback

- 模块在 `import config` 失败（单独运行调试）时提供本地 fallback 默认对象，保证模块可独立运行（见 `file_utils.py` 顶部）。

---

## 七、日志与终端输出格式

本项目使用**标准库 `print` + 前缀标记**作为主要输出方式（轻量、无依赖），关键错误同时写入 `error.log`。

### 7.1 前缀标记规范

| 前缀 | 含义 | 示例 |
| :--- | :--- | :--- |
| `[OK]` | 成功 / 通过 | `[OK] ffmpeg: /usr/bin/ffmpeg` |
| `[!]` | 警告（非致命，可继续） | `[!] 不支持的文件格式，已跳过: data.bin` |
| `[X]` | 错误（致命或需关注） | `[X] Python 版本过低: 3.8.0` |
| `[--]` | 不适用 / 未检测到 | `[--] GPU: 未检测到 NVIDIA GPU` |
| `    ->` | 次级信息 / 进度细节 | `    -> 已清理临时文件: demo.wav` |

### 7.2 输出规则

- **进度信息**：受 `config.VERBOSE_OUTPUT` 控制，仅在该值为 `True` 时打印详细中间过程；关键状态（成功/失败/回退）始终打印。
- **错误日志**：写入 `config.ERROR_LOG_FILE`（`error.log`），格式：`[时间] [级别] 消息`。
- **不污染输出**：调试用的长文本应截断或写入文件，避免刷屏。
- **结构化区块**：用 `=== 标题 ===` 包裹分段输出（见 `print_env_info` 的 `=== 环境检测 ===`）。

### 7.3 error.log 格式

```
[2026-08-27 14:30:01] [ERROR] 软字幕提取失败 demo.mp4: ffprobe 返回非零
[2026-08-27 14:30:05] [WARN]  GPU 不可用，回退 CPU 推理
```

- 时间：`YYYY-MM-DD HH:MM:SS`。
- 级别：`ERROR` / `WARN` / `INFO`。
- 消息：中文，含涉及的文件名 / 模块定位信息。

### 7.4 使用 logging 的建议

如改用标准库 `logging`，统一配置：

```python
import logging
logging.basicConfig(
    filename=config.ERROR_LOG_FILE,
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)
```

但当前代码基线以 `print` 为主，新增模块保持一致即可。

---

## 八、模块组织约定

1. **单一职责**：一个 `.py` 文件只负责一个功能域（检测 / 文件 / 提取 / OCR / 转录 / 写入）。
2. **公共接口集中**：模块对外暴露的函数 / 类在顶部 docstring 列明；私有辅助以 `_` 前缀。
3. **延迟导入重依赖**：`paddleocr`、`whisper` 等重型库在函数内部导入，避免模块导入时即触发初始化、拖慢启动。
4. **避免循环依赖**：模块依赖 `config` 时使用延迟导入或 fallback 对象（见 `env_check._select_whisper_model`、`file_utils` 顶部）。
5. **可测试性**：纯函数优先；副作用（文件 IO、子进程）集中到独立函数便于 mock。

---

## 九、Git 提交约定（建议）

- 提交信息使用中文或英文均可，但需清晰描述变更。
- 接口变更提交须包含对应的 `module_specs` 更新。
- 提交前运行 `python ai_context/check_ai_docs.py` 确保文档同步。

---

## 十、检查清单（提交前自检）

- [ ] 标识符全英文，注释 / 提示全中文。
- [ ] 公共函数有类型提示与 docstring（Args / Returns）。
- [ ] 无裸 `except`、无静默 `pass`；异常降级返回 `None` 走回退。
- [ ] 新参数已加入 `config.py` 并在 `AI_GUIDE.md` 补表。
- [ ] 接口变更已同步 `module_specs/<module>.md`。
- [ ] `python ai_context/check_ai_docs.py` 通过（退出码 0）。
- [ ] 行宽 <= 100，缩进 4 空格，无 Tab。
