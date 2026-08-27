# 文件管理模块规格说明（file_utils）

## 1. 模块职责描述

本模块负责视频字幕提取工具中所有与文件路径、目录、临时文件相关的辅助操作，为各业务模块提供统一的文件管理基础设施。

具体职责包括：

- 递归扫描指定目录下的视频文件（按扩展名过滤）。
- 从视频路径提取不含扩展名的文件名。
- 根据视频路径、输出目录与字幕获取方法标签生成字幕文件输出路径。
- 确保目录存在（不存在则创建）。
- 生成临时音频文件路径（供 Whisper 转写使用）。
- 安全清理临时文件与临时目录。
- 判断文件是否为受支持的视频格式。

本模块为纯文件路径与 IO 工具集，不涉及字幕内容处理逻辑。

---

## 2. 公共函数/类签名

### 2.1 `scan_video_files(input_dir: str) -> list[str]`

```python
def scan_video_files(input_dir: str) -> list[str]
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `input_dir` | `str` | 待扫描的根目录路径 |

**返回值：** `list[str]` —— 受支持视频文件的绝对路径列表，按路径排序。

### 2.2 `get_video_name(video_path: str) -> str`

```python
def get_video_name(video_path: str) -> str
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `video_path` | `str` | 视频文件路径 |

**返回值：** `str` —— 不含扩展名的文件名（不含目录部分）。

### 2.3 `get_subtitle_path(video_path, output_dir, method) -> str`

```python
def get_subtitle_path(video_path: str, output_dir: str, method: str) -> str
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `video_path` | `str` | 源视频路径 |
| `output_dir` | `str` | 输出目录 |
| `method` | `str` | 字幕获取方法标签（如 `embedded`/`ocr`/`whisper`） |

**返回值：** `str` —— 字幕文件绝对路径，扩展名为 `.srt`。

### 2.4 `ensure_dir(path: str) -> None`

```python
def ensure_dir(path: str) -> None
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `path` | `str` | 目录路径 |

**返回值：** `None`

**行为描述：** 若目录不存在则递归创建，已存在时不报错。

### 2.5 `get_temp_audio_path(video_path, temp_dir) -> str`

```python
def get_temp_audio_path(video_path: str, temp_dir: str) -> str
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `video_path` | `str` | 视频路径 |
| `temp_dir` | `str` | 临时目录 |

**返回值：** `str` —— 临时 WAV 音频文件路径。

### 2.6 `cleanup_temp_files(*paths) -> None`

```python
def cleanup_temp_files(*paths) -> None
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `*paths` | `str`（可变参数） | 待删除的文件路径列表 |

**返回值：** `None`

### 2.7 `cleanup_temp_dir(temp_dir) -> None`

```python
def cleanup_temp_dir(temp_dir: str) -> None
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `temp_dir` | `str` | 临时目录路径 |

**返回值：** `None`

**行为描述：** 递归删除整个临时目录及其全部内容。

### 2.8 `is_supported_video(filepath: str) -> bool`

```python
def is_supported_video(filepath: str) -> bool
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `filepath` | `str` | 文件路径 |

**返回值：** `bool` —— 扩展名为受支持视频格式返回 `True`，否则 `False`。

---

## 3. 输入数据格式

### 3.1 路径输入

所有函数接收的路径均为字符串。路径可以是绝对或相对路径，但内部会通过 `os.path.abspath` 规范化为绝对路径以保证一致性。

### 3.2 受支持视频扩展名

`scan_video_files` 与 `is_supported_video` 共用同一扩展名集合：

| 扩展名 | 说明 |
|--------|------|
| `.mp4` | MPEG-4 容器 |
| `.mkv` | Matroska 容器 |
| `.avi` | AVI 容器 |
| `.mov` | QuickTime 容器 |

扩展名匹配不区分大小写（`.MP4` 与 `.mp4` 均匹配）。

### 3.3 方法标签（`method`）

`get_subtitle_path` 的 `method` 参数为字符串标签，用于在字幕文件名中区分来源。约定取值：

- `"embedded"`：软字幕提取
- `"ocr"`：硬字幕 OCR
- `"whisper"`：语音转写

---

## 4. 输出数据格式

### 4.1 `scan_video_files` 返回值

```python
[
    "/data/videos/movie1.mp4",
    "/data/videos/subdir/movie2.mkv",
    "/data/videos/clip.avi"
]
```

列表元素为绝对路径字符串，按字典序排序。

### 4.2 `get_video_name` 返回值

```python
# 输入 "/data/videos/movie.mp4"
# 返回 "movie"
```

### 4.3 `get_subtitle_path` 返回值

```python
# 输入 video_path="/data/videos/movie.mp4", output_dir="/output", method="whisper"
# 返回 "/output/movie_whisper.srt"
```

文件名格式：`{视频名}_{method}.srt`。

### 4.4 `get_temp_audio_path` 返回值

```python
# 输入 video_path="/data/videos/movie.mp4", temp_dir="/tmp/sub_tool"
# 返回 "/tmp/sub_tool/movie_16k.wav"
```

文件名格式：`{视频名}_16k.wav`。

---

## 5. 关键算法说明

### 5.1 递归扫描视频文件算法

使用 `os.walk` 递归遍历目录树，对每个文件用 `is_supported_video` 过滤：

```python
SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}

def scan_video_files(input_dir):
    result = []
    for root, _, files in os.walk(input_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            if is_supported_video(fpath):
                result.append(os.path.abspath(fpath))
    return sorted(result)
```

关键点：

- `os.walk` 天然支持递归子目录遍历。
- 使用 `os.path.abspath` 统一为绝对路径。
- `sorted` 保证输出顺序确定，便于测试与日志。

### 5.2 扩展名校验算法

```python
def is_supported_video(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    return ext in SUPPORTED_EXTENSIONS
```

关键点：

- `os.path.splitext` 仅取最后一个 `.` 之后的扩展名。
- `.lower()` 实现大小写不敏感匹配。
- 使用集合 `in` 判断，O(1) 复杂度。

### 5.3 文件名提取算法

```python
def get_video_name(video_path):
    basename = os.path.basename(video_path)
    name, _ = os.path.splitext(basename)
    return name
```

`os.path.basename` 去除目录部分，`os.path.splitext` 去除扩展名，仅保留纯文件名。

### 5.4 字幕路径生成算法

```python
def get_subtitle_path(video_path, output_dir, method):
    name = get_video_name(video_path)
    filename = f"{name}_{method}.srt"
    return os.path.join(output_dir, filename)
```

通过视频名 + 方法标签拼接，保证不同来源的字幕互不覆盖。

### 5.5 临时音频路径生成算法

```python
def get_temp_audio_path(video_path, temp_dir):
    name = get_video_name(video_path)
    return os.path.join(temp_dir, f"{name}_16k.wav")
```

固定后缀 `_16k.wav` 标识 16kHz 采样率，与 `transcriber.extract_audio` 输出对应。

### 5.6 安全清理算法

```python
def cleanup_temp_files(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass  # 清理失败静默忽略

def cleanup_temp_dir(temp_dir):
    try:
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)
    except OSError:
        pass
```

关键点：

- 使用 `try/except OSError` 捕获所有文件系统错误（权限、文件被占用等）。
- 清理失败静默忽略，因临时文件清理不应影响主流程结果。
- 删除前检查存在性，避免 `FileNotFoundError`。
- `cleanup_temp_dir` 使用 `shutil.rmtree` 递归删除。

### 5.7 目录确保算法

```python
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
```

`exist_ok=True` 使目录已存在时不报错，实现幂等创建。

---

## 6. 异常处理策略

| 异常场景 | 处理策略 |
|----------|----------|
| `input_dir` 不存在 | `scan_video_files` 抛出 `FileNotFoundError` |
| `input_dir` 为空字符串 | `scan_video_files` 抛出 `ValueError` |
| `input_dir` 是文件而非目录 | `os.walk` 返回空，`scan_video_files` 返回空列表 |
| `video_path` 为空 | `get_video_name` 返回 `""`，不抛异常 |
| `output_dir` 不存在 | `get_subtitle_path` 仅返回路径不创建目录；实际创建由调用方或 `save_srt` 处理 |
| `temp_dir` 不存在 | `get_temp_audio_path` 仅返回路径不创建目录 |
| 临时文件不存在 | `cleanup_temp_files` 静默跳过，不抛异常 |
| 临时文件被占用无法删除 | `cleanup_temp_files` 捕获 `OSError` 静默忽略 |
| `temp_dir` 不存在 | `cleanup_temp_dir` 静默跳过，不抛异常 |
| `ensure_dir` 路径存在但无权限 | 抛出 `PermissionError`，由调用方处理 |
| `is_supported_video` 路径为空 | `os.path.splitext("")` 返回 `("", "")`，扩展名 `""` 不在集合中，返回 `False` |

**核心原则：**

- 路径生成类函数（`get_subtitle_path` 等）为纯计算函数，不执行 IO，不因目录不存在而报错。
- 清理类函数必须"安全失败"：任何异常都应被吞没，绝不影响主流程。
- 目录创建类函数对"已存在"幂等，但对"权限不足"如实抛出。

---

## 7. 测试用例及验收标准

### 测试用例 TC-FILE-01：扫描含视频文件的目录

**前置条件：** 目录结构如下：

```
/data/test_videos/
  movie1.mp4
  movie2.mkv
  subdir/
    clip.avi
  readme.txt
```

**操作步骤：** 调用 `scan_video_files("/data/test_videos")`

**预期结果：**

- 返回列表长度为 3
- 包含 `movie1.mp4`、`movie2.mkv`、`subdir/clip.avi` 的绝对路径
- 不包含 `readme.txt`
- 列表已排序

**验收标准：** 通过

---

### 测试用例 TC-FILE-02：空目录扫描

**前置条件：** 目录为空

**操作步骤：** 调用 `scan_video_files(empty_dir)`

**预期结果：**

- 返回空列表 `[]`
- 不抛出异常

**验收标准：** 通过

---

### 测试用例 TC-FILE-03：目录不存在

**前置条件：** `input_dir = "/nonexistent/dir"`

**操作步骤：** 调用 `scan_video_files(input_dir)`

**预期结果：**

- 抛出 `FileNotFoundError`

**验收标准：** 通过

---

### 测试用例 TC-FILE-04：提取视频名

**前置条件：** `video_path = "/data/videos/movie.mp4"`

**操作步骤：** 调用 `get_video_name(video_path)`

**预期结果：**

- 返回 `"movie"`

**验收标准：** 通过

---

### 测试用例 TC-FILE-05：提取多层路径视频名

**前置条件：** `video_path = "/a/b/c/test.video.mkv"`

**操作步骤：** 调用 `get_video_name(video_path)`

**预期结果：**

- 返回 `"test.video"`（仅去除最后一个扩展名）

**验收标准：** 通过

---

### 测试用例 TC-FILE-06：生成字幕路径

**前置条件：** `video_path = "/data/videos/movie.mp4"`，`output_dir = "/output"`，`method = "whisper"`

**操作步骤：** 调用 `get_subtitle_path(video_path, output_dir, method)`

**预期结果：**

- 返回 `"/output/movie_whisper.srt"`

**验收标准：** 通过

---

### 测试用例 TC-FILE-07：确保目录创建

**前置条件：** `/tmp/test_ensure/a/b` 不存在

**操作步骤：** 调用 `ensure_dir("/tmp/test_ensure/a/b")`

**预期结果：**

- 目录被递归创建
- 函数返回 `None`
- 再次调用不报错（幂等）

**验收标准：** 通过

---

### 测试用例 TC-FILE-08：生成临时音频路径

**前置条件：** `video_path = "/data/videos/movie.mp4"`，`temp_dir = "/tmp/sub"`

**操作步骤：** 调用 `get_temp_audio_path(video_path, temp_dir)`

**预期结果：**

- 返回 `"/tmp/sub/movie_16k.wav"`

**验收标准：** 通过

---

### 测试用例 TC-FILE-09：清理存在的临时文件

**前置条件：** 创建两个临时文件 file1.txt、file2.txt

**操作步骤：** 调用 `cleanup_temp_files(path1, path2)`

**预期结果：**

- 两个文件均被删除
- 函数返回 `None`
- 不抛出异常

**验收标准：** 通过

---

### 测试用例 TC-FILE-10：清理不存在的文件（安全失败）

**前置条件：** `path = "/tmp/nonexistent_file.txt"`

**操作步骤：** 调用 `cleanup_temp_files(path)`

**预期结果：**

- 不抛出异常
- 函数返回 `None`

**验收标准：** 通过

---

### 测试用例 TC-FILE-11：清理临时目录

**前置条件：** 创建临时目录 `/tmp/test_cleanup/`，内含若干文件与子目录

**操作步骤：** 调用 `cleanup_temp_dir("/tmp/test_cleanup")`

**预期结果：**

- 目录及其全部内容被递归删除
- 函数返回 `None`
- 不抛出异常

**验收标准：** 通过

---

### 测试用例 TC-FILE-12：清理不存在的目录（安全失败）

**前置条件：** `temp_dir = "/tmp/nonexistent_dir"`

**操作步骤：** 调用 `cleanup_temp_dir(temp_dir)`

**预期结果：**

- 不抛出异常
- 函数返回 `None`

**验收标准：** 通过

---

### 测试用例 TC-FILE-13：判断受支持视频格式

**前置条件：** 无

**操作步骤：** 分别调用 `is_supported_video`

**预期结果：**

- `is_supported_video("a.mp4")` 返回 `True`
- `is_supported_video("a.MKV")` 返回 `True`（大小写不敏感）
- `is_supported_video("a.mov")` 返回 `True`
- `is_supported_video("a.avi")` 返回 `True`
- `is_supported_video("a.txt")` 返回 `False`
- `is_supported_video("a.mp4.bak")` 返回 `False`

**验收标准：** 通过

---

### 测试用例 TC-FILE-14：清理被占用的文件（安全失败）

**前置条件：** 创建文件并 mock `os.remove` 抛出 `PermissionError`

**操作步骤：** 调用 `cleanup_temp_files(path)`

**预期结果：**

- 不抛出异常
- 函数返回 `None`

**验收标准：** 通过

---

### 测试用例 TC-FILE-15：空路径输入

**前置条件：** 无

**操作步骤：**

- `scan_video_files("")` 抛出 `ValueError`
- `is_supported_video("")` 返回 `False`
- `get_video_name("")` 返回 `""`
- `cleanup_temp_files("")` 不抛异常

**验收标准：** 通过
