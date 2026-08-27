# SRT 格式化与写入模块规格说明（subtitle_writer）

## 1. 模块职责描述

本模块负责将各字幕来源（软字幕提取、OCR 识别、语音转写）产出的统一字幕条目转换为标准 SRT 格式文本，并写入磁盘文件。

具体职责包括：

- 将浮点秒数时间戳格式化为 SRT 标准 `HH:MM:SS,mmm` 时间码。
- 将字幕条目列表（`{"start","end","text"}`）组装为符合 SRT 规范的完整文本字符串。
- 将 SRT 文本以 UTF-8 编码写入指定路径文件。
- 提供整合上述步骤的便捷函数，支持根据视频路径与方法标签自动生成输出路径。

本模块是字幕生产链路的最后一环，输出可直接被播放器加载的字幕文件。

---

## 2. 公共函数/类签名

### 2.1 `format_timestamp(seconds: float) -> str`

```python
def format_timestamp(seconds: float) -> str
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `seconds` | `float` | 以秒为单位的浮点时间值 |

**返回值：** `str` —— 格式为 `HH:MM:SS,mmm` 的时间码字符串。

### 2.2 `entries_to_srt(entries: list[dict]) -> str`

```python
def entries_to_srt(entries: list[dict]) -> str
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `entries` | `list[dict]` | 字幕条目列表，每项含 `start`(float)、`end`(float)、`text`(str) |

**返回值：** `str` —— 完整 SRT 格式文本字符串。

### 2.3 `save_srt(srt_content: str, output_path: str) -> str`

```python
def save_srt(srt_content: str, output_path: str) -> str
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `srt_content` | `str` | SRT 格式文本 |
| `output_path` | `str` | 目标保存路径（含 `.srt` 扩展名） |

**返回值：** `str` —— 实际保存的文件路径。

### 2.4 `write_srt_from_entries(entries, video_path, output_dir, method) -> str`

```python
def write_srt_from_entries(
    entries: list[dict],
    video_path: str,
    output_dir: str,
    method: str
) -> str
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `entries` | `list[dict]` | 字幕条目列表 |
| `video_path` | `str` | 源视频路径，用于推导字幕文件名 |
| `output_dir` | `str` | 输出目录 |
| `method` | `str` | 字幕获取方法标签（如 `"embedded"`、`"ocr"`、`"whisper"`），用于文件名后缀 |

**返回值：** `str` —— 保存的 SRT 文件绝对路径。

**行为描述：** 整合 `entries_to_srt`、路径生成与 `save_srt` 三步的便捷函数。

---

## 3. 输入数据格式

### 3.1 字幕条目（`entries`）

统一字幕条目格式，适用于 `entries_to_srt` 与 `write_srt_from_entries`：

```python
[
    {"start": 0.0, "end": 2.5, "text": "第一句字幕"},
    {"start": 2.5, "end": 5.0, "text": "第二句字幕"}
]
```

| 键 | 类型 | 说明 |
|----|------|------|
| `start` | `float` | 开始时间（秒），非负 |
| `end` | `float` | 结束时间（秒），>= `start` |
| `text` | `str` | 字幕文本，可含换行 |

### 3.2 时间戳输入（`format_timestamp`）

浮点秒数，例如 `125.756` 表示 2 分 5 秒 756 毫秒。

---

## 4. 输出数据格式

### 4.1 SRT 文本格式（`entries_to_srt` / `save_srt`）

标准 SRT 格式，每条字幕为一个块，块间以空行分隔：

```
1
00:00:00,000 --> 00:00:02,500
第一句字幕

2
00:00:02,500 --> 00:00:05,000
第二句字幕
```

每块结构：

- 第 1 行：序号（从 1 递增）
- 第 2 行：`开始时间 --> 结束时间`，时间格式 `HH:MM:SS,mmm`
- 第 3 行及以后：字幕文本
- 块之间以一个空行分隔

### 4.2 `format_timestamp` 返回值

```
00:02:05,756
```

各部分固定宽度：`HH`（2 位）、`MM`（2 位）、`SS`（2 位）、`mmm`（3 位毫秒），时间分隔符为 `:`，毫秒分隔符为 `,`。

### 4.3 `save_srt` / `write_srt_from_entries` 返回值

保存的 SRT 文件绝对路径字符串，例如：

```
/workspace/output/video_name_whisper.srt
```

---

## 5. 关键算法说明

### 5.1 时间戳格式化算法

将浮点秒数转换为 `HH:MM:SS,mmm`：

```python
def format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis == 1000:  # 进位处理
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
```

关键点：

- 负数时间戳强制归零，避免非法输出。
- 毫秒取整使用四舍五入 `round`，保证 `0.9996` 这类边界正确进位为 1000 并向秒进位。
- 各字段零填充：小时 2 位、分钟 2 位、秒 2 位、毫秒 3 位。
- 小数部分 `(seconds - int(seconds))` 仅取小数部分，乘 1000 得毫秒。

### 5.2 SRT 组装算法

```python
def entries_to_srt(entries: list[dict]) -> str:
    blocks = []
    for idx, entry in enumerate(entries, start=1):
        start = format_timestamp(float(entry["start"]))
        end = format_timestamp(float(entry["end"]))
        text = str(entry["text"]).strip()
        blocks.append(f"{idx}\n{start} --> {end}\n{text}")
    return "\n\n".join(blocks) + "\n"
```

关键点：

- 序号使用 `enumerate(..., start=1)` 从 1 递增，忽略原始条目可能的不连续序号。
- 时间码调用 `format_timestamp` 统一格式化。
- 文本做 `strip` 处理，去除首尾空白与多余换行。
- 块之间以 `\n\n`（空行）连接，末尾追加换行符保证文件以换行结尾。

### 5.3 文件写入算法

```python
def save_srt(srt_content: str, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    return output_path
```

关键点：

- 编码固定为 UTF-8，兼容中文字符且为字幕播放器通用标准。
- 自动创建父目录（`exist_ok=True` 避免目录已存在报错）。
- 返回传入的 `output_path`，便于链式调用。

### 5.4 便捷函数流程

`write_srt_from_entries` 整合三步：

1. 调用 `entries_to_srt(entries)` 生成 SRT 文本。
2. 由视频文件名 + method 标签生成输出路径（依赖 `file_utils.get_subtitle_path`）。
3. 调用 `save_srt(srt_content, output_path)` 写入并返回路径。

---

## 6. 异常处理策略

| 异常场景 | 处理策略 |
|----------|----------|
| `entries` 为空列表 | `entries_to_srt` 返回空字符串 `""`，不抛异常 |
| 条目缺少 `start`/`end`/`text` 键 | 抛出 `KeyError`，提示缺失字段 |
| `start` 或 `end` 为非数值类型 | 抛出 `TypeError`/`ValueError`，提示时间戳非法 |
| `start > end` | 输出中仍写入（开始晚于结束），但记入警告；或交换两者保证合法（按实现选择） |
| `seconds` 为负数 | `format_timestamp` 内部归零，不抛异常 |
| `output_path` 父目录不存在 | 自动创建，不抛异常 |
| `output_path` 不可写（权限不足） | 抛出 `PermissionError` |
| `output_path` 为空字符串 | 抛出 `ValueError`，提示路径无效 |
| 磁盘空间不足 | 抛出 `OSError`，由调用方处理 |
| `text` 为非字符串类型 | 强制 `str()` 转换，不抛异常 |

**核心原则：**

- 格式化阶段对边界值（负数、非法类型）做防御性处理，优先保证输出可用。
- IO 阶段（写文件）的错误（权限、空间）如实抛出，因属环境问题需调用方感知。
- 空条目列表为合法输入，输出空文件。

---

## 7. 测试用例及验收标准

### 测试用例 TC-WRITE-01：格式化标准时间戳

**前置条件：** 无

**操作步骤：** 调用 `format_timestamp(125.756)`

**预期结果：**

- 返回 `"00:02:05,756"`

**验收标准：** 通过

---

### 测试用例 TC-WRITE-02：格式化零时间

**前置条件：** 无

**操作步骤：** 调用 `format_timestamp(0.0)`

**预期结果：**

- 返回 `"00:00:00,000"`

**验收标准：** 通过

---

### 测试用例 TC-WRITE-03：格式化超过 1 小时

**前置条件：** 无

**操作步骤：** 调用 `format_timestamp(3723.5)`

**预期结果：**

- 返回 `"01:02:03,500"`

**验收标准：** 通过

---

### 测试用例 TC-WRITE-04：毫秒进位处理

**前置条件：** 无

**操作步骤：** 调用 `format_timestamp(1.9996)`

**预期结果：**

- 返回 `"00:00:02,000"`（毫秒进位后秒数进位）

**验收标准：** 通过

---

### 测试用例 TC-WRITE-05：负数时间戳归零

**前置条件：** 无

**操作步骤：** 调用 `format_timestamp(-5.0)`

**预期结果：**

- 返回 `"00:00:00,000"`
- 不抛出异常

**验收标准：** 通过

---

### 测试用例 TC-WRITE-06：条目列表转 SRT

**前置条件：** 

```python
entries = [
    {"start": 0.0, "end": 2.5, "text": "第一句"},
    {"start": 2.5, "end": 5.0, "text": "第二句"}
]
```

**操作步骤：** 调用 `entries_to_srt(entries)`

**预期结果：**

- 字符串以 `"1\n"` 开头
- 包含 `"00:00:00,000 --> 00:00:02,500"`
- 包含 `"第一句"`
- 两个字幕块之间有空行
- 序号分别为 1、2

**验收标准：** 通过

---

### 测试用例 TC-WRITE-07：空条目列表

**前置条件：** `entries = []`

**操作步骤：** 调用 `entries_to_srt(entries)`

**预期结果：**

- 返回 `""`（空字符串）
- 不抛出异常

**验收标准：** 通过

---

### 测试用例 TC-WRITE-08：保存 SRT 文件

**前置条件：** 准备 SRT 文本内容，输出目录不存在

**操作步骤：** 调用 `save_srt(srt_content, "/tmp/new_dir/sub.srt")`

**预期结果：**

- 返回路径与入参一致
- 文件真实存在
- 目录 `/tmp/new_dir` 被自动创建
- 文件以 UTF-8 编码，可正确读回中文

**验收标准：** 通过

---

### 测试用例 TC-WRITE-09：便捷函数完整流程

**前置条件：** 准备条目列表、视频路径 `/path/video.mp4`、输出目录、`method="whisper"`

**操作步骤：** 调用 `write_srt_from_entries(entries, video_path, output_dir, "whisper")`

**预期结果：**

- 返回的路径以 `.srt` 结尾
- 文件名包含视频名（不含扩展名）与 method 标签
- 文件内容为合法 SRT 格式
- 文件以 UTF-8 编码

**验收标准：** 通过

---

### 测试用例 TC-WRITE-10：条目缺少字段

**前置条件：** `entries = [{"start": 0.0, "end": 1.0}]`（缺 `text`）

**操作步骤：** 调用 `entries_to_srt(entries)`

**预期结果：**

- 抛出 `KeyError`
- 异常信息提示缺少 `text` 字段

**验收标准：** 通过
