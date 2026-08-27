# 环境检测模块规格说明（env_check）

## 1. 模块职责描述

本模块负责在程序启动时对运行环境进行全面检测，为后续字幕提取流程提供环境就绪状态判断与配置参数。

具体职责包括：

- 检测当前 Python 解释器版本是否满足最低要求（3.10+）。
- 检测系统是否安装了 `ffmpeg` 与 `ffprobe`，并获取其可执行路径。
- 通过 `nvidia-smi` 检测是否存在 NVIDIA GPU，并读取 GPU 名称与显存（VRAM）容量。
- 根据可用显存自动选择合适的 Whisper 模型规格（VRAM >= 6GB 选择 `medium`，否则选择 `small`）。
- 收集检测过程中产生的警告（warnings）与错误（errors），以列表形式汇总。
- 提供终端友好的检测结果打印功能，便于用户直观了解环境状态。

该模块不执行任何字幕提取逻辑，仅输出一个 `EnvInfo` 数据结构供上层调度使用。

---

## 2. 公共函数/类签名

### 2.1 数据类 `EnvInfo`

```python
@dataclass
class EnvInfo:
    python_version: str      # 当前 Python 版本字符串，例如 "3.11.5"
    python_ok: bool          # Python 版本是否 >= 3.10
    ffmpeg_path: str         # ffmpeg 可执行文件路径，未找到时为空字符串 ""
    ffmpeg_ok: bool          # ffmpeg 与 ffprobe 是否均可用
    gpu_name: str            # GPU 名称，无 GPU 时为空字符串 ""
    gpu_vram_gb: float       # GPU 显存容量（GB），无 GPU 时为 0.0
    has_gpu: bool            # 是否检测到 NVIDIA GPU
    whisper_model: str       # 自动选择的 Whisper 模型规格："medium" 或 "small"
    warnings: list           # 警告信息列表，元素为 str
    errors: list             # 错误信息列表，元素为 str
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `python_version` | `str` | 形如 `major.minor.patch` 的版本字符串 |
| `python_ok` | `bool` | `True` 表示版本满足 >= 3.10 |
| `ffmpeg_path` | `str` | ffmpeg 绝对路径或命令名；不可用时为 `""` |
| `ffmpeg_ok` | `bool` | `True` 表示 ffmpeg 与 ffprobe 均可调用 |
| `gpu_name` | `str` | 如 `NVIDIA GeForce RTX 3060`；无 GPU 为 `""` |
| `gpu_vram_gb` | `float` | 单位 GB，保留一位小数；无 GPU 为 `0.0` |
| `has_gpu` | `bool` | `True` 表示检测到可用 NVIDIA GPU |
| `whisper_model` | `str` | 取值 `medium` 或 `small` |
| `warnings` | `list[str]` | 非致命提示信息 |
| `errors` | `list[str]` | 致命错误信息，存在则流程不应继续 |

### 2.2 `check_environment() -> EnvInfo`

```python
def check_environment() -> EnvInfo
```

**参数：** 无

**返回值：** `EnvInfo` —— 包含全部环境检测结果的不可变数据对象。

**行为描述：**

1. 通过 `sys.version_info` 获取 Python 版本，判断是否 `>= (3, 10)`。
2. 使用 `shutil.which("ffmpeg")` 与 `shutil.which("ffprobe")` 检测可执行文件路径。
3. 调用 `ffmpeg -version` 验证其可正常运行。
4. 调用 `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader` 解析 GPU 名称与总显存。
5. 依据 `gpu_vram_gb` 选择 Whisper 模型：`>= 6.0` 选 `medium`，否则选 `small`。
6. 将过程中发现的非致命问题写入 `warnings`，致命问题写入 `errors`。

### 2.3 `print_env_info(info: EnvInfo) -> None`

```python
def print_env_info(info: EnvInfo) -> None
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `info` | `EnvInfo` | 由 `check_environment()` 返回的环境信息对象 |

**返回值：** `None`

**行为描述：**

以结构化文本输出到标准输出，包含以下内容：

- Python 版本与状态（OK / 不满足要求）
- ffmpeg/ffprobe 路径与状态
- GPU 名称、显存与状态
- 自动选择的 Whisper 模型规格
- 警告与错误信息列表（如有）

---

## 3. 输入数据格式

本模块为环境检测模块，不接收业务数据输入。

- `check_environment()` 无输入参数。
- `print_env_info(info)` 接收一个 `EnvInfo` 实例，该实例由 `check_environment()` 产生。

模块内部依赖的系统输入：

- `sys.version_info`：Python 解释器内置版本信息。
- `shutil.which()` 返回的可执行路径查询结果。
- `nvidia-smi` 命令的标准输出，格式为 CSV：
  ```
  NVIDIA GeForce RTX 3060, 12288 MiB
  ```

---

## 4. 输出数据格式

### 4.1 `EnvInfo` 数据结构示例

```python
EnvInfo(
    python_version="3.11.5",
    python_ok=True,
    ffmpeg_path="/usr/bin/ffmpeg",
    ffmpeg_ok=True,
    gpu_name="NVIDIA GeForce RTX 3060",
    gpu_vram_gb=12.0,
    has_gpu=True,
    whisper_model="medium",
    warnings=["未检测到 ffprobe，将使用 ffmpeg 替代"],  # 仅示例
    errors=[]
)
```

无 GPU 环境下的示例：

```python
EnvInfo(
    python_version="3.10.8",
    python_ok=True,
    ffmpeg_path="/usr/bin/ffmpeg",
    ffmpeg_ok=True,
    gpu_name="",
    gpu_vram_gb=0.0,
    has_gpu=False,
    whisper_model="small",
    warnings=["未检测到 NVIDIA GPU，将使用 CPU 模式运行，速度较慢"],
    errors=[]
)
```

### 4.2 `print_env_info` 终端输出格式示例

```
========== 环境检测报告 ==========
Python 版本   : 3.11.5                 [OK]
ffmpeg 路径   : /usr/bin/ffmpeg         [OK]
ffprobe       : 可用                    [OK]
GPU 名称      : NVIDIA GeForce RTX 3060 [OK]
GPU 显存      : 12.0 GB
Whisper 模型  : medium
----------------------------------
警告 (1):
  - 未检测到 ffprobe，将使用 ffmpeg 替代
错误 (0)
==================================
```

---

## 5. 关键算法说明

### 5.1 Python 版本检测

利用 `sys.version_info` 命名元组进行版本比较：

```python
import sys
version_ok = sys.version_info >= (3, 10)
```

版本元组比较天然支持 `major.minor.micro` 层级，无需字符串解析。

### 5.2 ffmpeg / ffprobe 路径检测

使用标准库 `shutil.which(command)` 在 `PATH` 中查找可执行文件，返回绝对路径或 `None`。随后调用 `subprocess.run([path, "-version"], capture_output=True)` 验证可执行性，避免仅有文件存在但无法运行的情况。

### 5.3 NVIDIA GPU 检测

调用以下命令并解析输出：

```bash
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
```

输出示例：

```
NVIDIA GeForce RTX 3060, 12288 MiB
```

解析算法：

1. 若命令返回码非 0 或输出为空，则 `has_gpu = False`。
2. 取第一行，按逗号分割，第一段为 GPU 名称。
3. 第二段形如 `12288 MiB`，提取数字部分，除以 1024 转换为 GB。
4. `gpu_vram_gb = 12288 / 1024 = 12.0`。

### 5.4 Whisper 模型自动选择

选择策略为基于显存的阈值判断：

```python
if gpu_vram_gb >= 6.0:
    whisper_model = "medium"
else:
    whisper_model = "small"
```

选择依据：

- `medium` 模型约需 5GB 显存，6GB 为安全阈值。
- `small` 模型约需 2GB 显存，适用于低显存或 CPU 场景。
- 无 GPU 时回退到 `small`，Whisper 会自动使用 CPU 推理。

---

## 6. 异常处理策略

| 异常场景 | 处理策略 | 归属字段 |
|----------|----------|----------|
| Python 版本 < 3.10 | 不抛出异常，设置 `python_ok=False`，记入 `errors` | `errors` |
| `shutil.which("ffmpeg")` 返回 `None` | 设置 `ffmpeg_path=""`、`ffmpeg_ok=False`，记入 `errors` | `errors` |
| `shutil.which("ffprobe")` 返回 `None` | 设置 `ffmpeg_ok` 视情况，记入 `warnings` | `warnings` |
| `ffmpeg -version` 调用超时或失败 | 设置 `ffmpeg_ok=False`，记入 `errors` | `errors` |
| `nvidia-smi` 命令不存在 | 视为无 GPU，设置 `has_gpu=False`，记入 `warnings` | `warnings` |
| `nvidia-smi` 输出无法解析 | `gpu_name=""`、`gpu_vram_gb=0.0`、`has_gpu=False`，记入 `warnings` | `warnings` |
| `subprocess` 抛出 `FileNotFoundError` | 捕获并降级为对应字段为空/false，不中断检测 | `warnings`/`errors` |
| `print_env_info` 接收 `None` | 抛出 `TypeError`，由调用方处理 | - |

**核心原则：** 检测过程不应因任何单项失败而中断，所有异常均被捕获并记录到 `warnings` 或 `errors`，保证最终返回完整的 `EnvInfo` 对象。

---

## 7. 测试用例及验收标准

### 测试用例 TC-ENV-01：Python 版本满足要求

**前置条件：** 测试环境 Python 版本为 3.11.5

**操作步骤：** 调用 `check_environment()`

**预期结果：**

- `info.python_version == "3.11.5"`
- `info.python_ok is True`
- `errors` 中不存在版本相关条目

**验收标准：** 通过

---

### 测试用例 TC-ENV-02：Python 版本不满足要求

**前置条件：** 模拟 Python 版本为 3.9.x（通过 mock `sys.version_info`）

**操作步骤：** 调用 `check_environment()`

**预期结果：**

- `info.python_ok is False`
- `info.errors` 中包含提示 Python 版本过低的字符串

**验收标准：** 通过

---

### 测试用例 TC-ENV-03：ffmpeg 与 ffprobe 均可用

**前置条件：** 系统已安装 ffmpeg 与 ffprobe 并在 PATH 中

**操作步骤：** 调用 `check_environment()`

**预期结果：**

- `info.ffmpeg_path` 为非空字符串
- `info.ffmpeg_ok is True`
- `errors` 与 `warnings` 中不存在 ffmpeg 相关条目

**验收标准：** 通过

---

### 测试用例 TC-ENV-04：ffmpeg 不可用

**前置条件：** 临时修改 PATH 使 ffmpeg 不可被找到

**操作步骤：** 调用 `check_environment()`

**预期结果：**

- `info.ffmpeg_path == ""`
- `info.ffmpeg_ok is False`
- `info.errors` 中包含未找到 ffmpeg 的错误描述

**验收标准：** 通过

---

### 测试用例 TC-ENV-05：检测到 NVIDIA GPU 且显存 >= 6GB

**前置条件：** 测试机器配有 RTX 3060（12GB 显存），`nvidia-smi` 可用

**操作步骤：** 调用 `check_environment()`

**预期结果：**

- `info.has_gpu is True`
- `info.gpu_name` 包含 "RTX 3060"
- `info.gpu_vram_gb == 12.0`
- `info.whisper_model == "medium"`

**验收标准：** 通过

---

### 测试用例 TC-ENV-06：检测到 NVIDIA GPU 但显存 < 6GB

**前置条件：** 模拟 GPU 显存为 4GB

**操作步骤：** 调用 `check_environment()`

**预期结果：**

- `info.has_gpu is True`
- `info.gpu_vram_gb < 6.0`
- `info.whisper_model == "small"`

**验收标准：** 通过

---

### 测试用例 TC-ENV-07：无 NVIDIA GPU

**前置条件：** 测试机器无 NVIDIA GPU 或 `nvidia-smi` 不可用

**操作步骤：** 调用 `check_environment()`

**预期结果：**

- `info.has_gpu is False`
- `info.gpu_name == ""`
- `info.gpu_vram_gb == 0.0`
- `info.whisper_model == "small"`
- `info.warnings` 中包含无 GPU 的提示

**验收标准：** 通过

---

### 测试用例 TC-ENV-08：print_env_info 输出完整性

**前置条件：** 拥有一个有效的 `EnvInfo` 对象

**操作步骤：** 调用 `print_env_info(info)` 并捕获 stdout

**预期结果：**

- 输出包含 "环境检测报告" 标题行
- 输出包含 Python 版本、ffmpeg 路径、GPU 信息、Whisper 模型
- `warnings` 非空时输出包含每条警告
- `errors` 非空时输出包含每条错误
- 函数返回 `None`

**验收标准：** 通过

---

### 测试用例 TC-ENV-09：nvidia-smi 输出格式异常

**前置条件：** mock `nvidia-smi` 返回无法解析的输出（如空字符串或乱码）

**操作步骤：** 调用 `check_environment()`

**预期结果：**

- `info.has_gpu is False`
- `info.gpu_name == ""`
- `info.gpu_vram_gb == 0.0`
- `info.warnings` 中包含解析失败的提示
- 函数不抛出异常

**验收标准：** 通过

---

### 测试用例 TC-ENV-10：综合环境全部正常

**前置条件：** Python 3.11+、ffmpeg/ffprobe 已安装、NVIDIA GPU 可用且显存 >= 6GB

**操作步骤：** 调用 `check_environment()` 后调用 `print_env_info(info)`

**预期结果：**

- `info.errors == []`
- `info.warnings == []` 或仅含非致命提示
- 所有状态字段为 `True`
- `whisper_model == "medium"`
- 终端输出完整且无报错

**验收标准：** 通过
