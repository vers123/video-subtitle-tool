# 软字幕提取模块规格说明（subtitle_extractor）

## 1. 模块职责描述

本模块负责从视频文件中提取内嵌（软）字幕流。软字幕是指与视频流封装在同一容器文件（如 MKV、MP4）中、但未烧录到画面上的字幕数据。

具体职责包括：

- 使用 `ffprobe` 检测视频文件中是否存在字幕流（subtitle stream）。
- 列出视频文件中所有字幕流的元信息（编码格式、语言、流索引等）。
- 若存在字幕流，使用 `ffmpeg` 将其转换提取为 SRT 格式文本字符串。
- 若不存在任何字幕流，返回 `None` 以便上层调度切换至其他字幕获取方式（如 OCR 或语音转写）。

本模块仅处理软字幕提取，不负责硬字幕 OCR 或音频语音识别。

---

## 2. 公共函数/类签名

### 2.1 `get_subtitle_streams(video_path: str) -> list[dict]`

```python
def get_subtitle_streams(video_path: str) -> list[dict]
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `video_path` | `str` | 视频文件的绝对或相对路径 |

**返回值：** `list[dict]` —— 字幕流元信息字典列表，每个字典描述一个字幕流。

**行为描述：**

调用 `ffprobe` 以 JSON 格式输出视频的所有流信息，过滤出 `codec_type == "subtitle"` 的流，返回其完整元数据。

### 2.2 `extract_embedded(video_path: str) -> Optional[str]`

```python
def extract_embedded(video_path: str) -> Optional[str]
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `video_path` | `str` | 视频文件路径 |

**返回值：** `Optional[str]`

- 存在字幕流时：返回 SRT 格式的字幕文本字符串。
- 不存在字幕流时：返回 `None`。

**行为描述：**

1. 调用 `get_subtitle_streams(video_path)` 获取字幕流列表。
2. 若列表为空，返回 `None`。
3. 选取第一个字幕流（优先选取编码为 `subrip`/`srt` 或语言为中文/英文的流）。
4. 使用 `ffmpeg` 将该流提取并转换为 SRT 格式文本。
5. 将输出捕获为字符串返回。

---

## 3. 输入数据格式

### 3.1 视频文件输入

`video_path` 为字符串路径，指向本地视频文件。支持的视频容器格式（由 ffmpeg/ffprobe 决定）包括但不限于：

- `.mkv`（Matroska，最常携带软字幕）
- `.mp4`
- `.mov`
- `.avi`

### 3.2 ffprobe 命令输出（内部使用）

模块内部调用以下命令获取流信息：

```bash
ffprobe -v quiet -print_format json -show_streams -select_streams s <video_path>
```

输出的 JSON 结构示例：

```json
{
  "streams": [
    {
      "index": 2,
      "codec_name": "subrip",
      "codec_type": "subtitle",
      "codec_long_name": "SubRip subtitle",
      "tags": {
        "language": "chi",
        "title": "简体中文"
      }
    },
    {
      "index": 3,
      "codec_name": "ass",
      "codec_type": "subtitle",
      "tags": {
        "language": "eng"
      }
    }
  ]
}
```

---

## 4. 输出数据格式

### 4.1 `get_subtitle_streams` 返回值

```python
[
    {
        "index": 2,
        "codec_name": "subrip",
        "codec_type": "subtitle",
        "codec_long_name": "SubRip subtitle",
        "tags": {"language": "chi", "title": "简体中文"}
    },
    {
        "index": 3,
        "codec_name": "ass",
        "codec_type": "subtitle",
        "tags": {"language": "eng"}
    }
]
```

每个字典至少包含以下键：

| 键 | 类型 | 说明 |
|----|------|------|
| `index` | `int` | 流索引，用于 ffmpeg 提取指定流 |
| `codec_name` | `str` | 编码名称，如 `subrip`、`ass`、`mov_text` |
| `codec_type` | `str` | 固定为 `"subtitle"` |
| `tags` | `dict` | 可能包含 `language`、`title` 等元数据 |

### 4.2 `extract_embedded` 返回值

成功时返回标准 SRT 文本字符串：

```
1
00:00:01,000 --> 00:00:04,000
这是第一句字幕

2
00:00:05,000 --> 00:00:08,000
这是第二句字幕
```

无字幕流时返回：

```python
None
```

---

## 5. 关键算法说明

### 5.1 字幕流检测算法

使用 `ffprobe` 的 `-select_streams s` 参数直接筛选字幕流，避免解析全部流后手动过滤，提升效率。输出采用 JSON 格式以便结构化解析：

```bash
ffprobe -v quiet -print_format json -show_streams -select_streams s <video_path>
```

通过 `json.loads()` 解析输出，取 `streams` 字段即为字幕流列表。

### 5.2 字幕流选择策略

当存在多个字幕流时，按以下优先级选取目标流：

1. 优先选择编码为 `subrip` 或 `srt` 的流（无需转码，质量最高）。
2. 其次选择 `tags.language` 为 `chi` 或 `zho` 的中文流。
3. 再次选择 `tags.language` 为 `eng` 的英文流。
4. 以上均不满足时，回退到列表中的第一个字幕流。

伪代码：

```python
def _select_stream(streams):
    for codec in ("subrip", "srt"):
        for s in streams:
            if s.get("codec_name") == codec:
                return s
    for lang in ("chi", "zho", "eng"):
        for s in streams:
            if s.get("tags", {}).get("language") == lang:
                return s
    return streams[0]
```

### 5.3 SRT 格式转换算法

使用 `ffmpeg` 将选定的字幕流映射输出为 SRT：

```bash
ffmpeg -v quiet -i <video_path> -map 0:<index> -c:s srt -f srt pipe:1
```

关键参数说明：

- `-map 0:<index>`：选择输入文件的第 `<index>` 个流。
- `-c:s srt`：将字幕编码转换为 SubRip（SRT）格式。
- `-f srt pipe:1`：以 SRT 格式输出到标准输出管道。

通过 `subprocess.run(..., capture_output=True)` 捕获 stdout 并解码为 UTF-8 字符串。

---

## 6. 异常处理策略

| 异常场景 | 处理策略 |
|----------|----------|
| `video_path` 指向的文件不存在 | 抛出 `FileNotFoundError`，附带路径信息 |
| `video_path` 为空字符串 | 抛出 `ValueError`，提示路径无效 |
| `ffprobe` 命令不存在 | 抛出 `RuntimeError`，提示需安装 ffprobe |
| `ffprobe` 调用返回非 0 退出码 | 抛出 `RuntimeError`，包含 stderr 内容 |
| `ffprobe` 输出 JSON 解析失败 | 抛出 `RuntimeError`，提示输出格式异常 |
| 无字幕流（streams 为空） | `get_subtitle_streams` 返回空列表 `[]`；`extract_embedded` 返回 `None` |
| `ffmpeg` 转换失败（编码不支持） | 抛出 `RuntimeError`，包含 ffmpeg 错误输出 |
| `ffmpeg` 标准输出解码失败 | 抛出 `UnicodeDecodeError`，尝试回退 latin-1 解码 |
| `subprocess` 超时 | 抛出 `subprocess.TimeoutExpired`，默认超时 120 秒 |

**核心原则：**

- 文件级错误（路径无效）立即抛出，因属调用方责任。
- 工具级错误（ffprobe/ffmpeg 不可用或执行失败）抛出含明确信息的 `RuntimeError`。
- 业务级"无字幕流"为合法结果，返回 `None` / 空列表而非异常，由上层决定后续流程。

---

## 7. 测试用例及验收标准

### 测试用例 TC-EXTRACT-01：提取内嵌 SRT 字幕流

**前置条件：** 准备一个包含 `subrip` 编码字幕流的 MKV 文件

**操作步骤：** 调用 `extract_embedded(video_path)`

**预期结果：**

- 返回值不为 `None`
- 返回字符串以 `1\n` 开头
- 包含形如 `00:00:0X,XXX --> 00:00:0X,XXX` 的时间轴行

**验收标准：** 通过

---

### 测试用例 TC-EXTRACT-02：无字幕流的视频

**前置条件：** 准备一个不含任何字幕流的 MP4 文件（纯视频+音频）

**操作步骤：** 调用 `extract_embedded(video_path)`

**预期结果：**

- 返回值为 `None`
- 不抛出异常

**验收标准：** 通过

---

### 测试用例 TC-EXTRACT-03：获取字幕流列表

**前置条件：** 准备一个含 2 条字幕流（中文 subrip + 英文 ass）的 MKV 文件

**操作步骤：** 调用 `get_subtitle_streams(video_path)`

**预期结果：**

- 返回列表长度为 2
- 每个元素含 `index`、`codec_name`、`codec_type` 键
- `codec_type` 均为 `"subtitle"`

**验收标准：** 通过

---

### 测试用例 TC-EXTRACT-04：多字幕流优先选择 SRT 编码

**前置条件：** 准备含 ass 字幕流（index=2）和 subrip 字幕流（index=3）的文件

**操作步骤：** 调用 `extract_embedded(video_path)` 并验证提取的流索引

**预期结果：**

- 优先提取 index=3 的 subrip 流
- 返回的 SRT 内容与该流对应

**验收标准：** 通过

---

### 测试用例 TC-EXTRACT-05：ASS 字幕转 SRT

**前置条件：** 准备仅含 ASS 编码字幕流的视频

**操作步骤：** 调用 `extract_embedded(video_path)`

**预期结果：**

- 返回有效的 SRT 格式字符串
- ASS 样式标签（如 `{\an8}`）被去除
- 时间轴格式为 `HH:MM:SS,mmm`

**验收标准：** 通过

---

### 测试用例 TC-EXTRACT-06：文件不存在

**前置条件：** `video_path = "/nonexistent/video.mkv"`

**操作步骤：** 调用 `extract_embedded(video_path)`

**预期结果：**

- 抛出 `FileNotFoundError`
- 异常信息包含路径字符串

**验收标准：** 通过

---

### 测试用例 TC-EXTRACT-07：空路径输入

**前置条件：** `video_path = ""`

**操作步骤：** 调用 `get_subtitle_streams(video_path)`

**预期结果：**

- 抛出 `ValueError`
- 异常信息提示路径无效

**验收标准：** 通过

---

### 测试用例 TC-EXTRACT-08：ffprobe 不可用

**前置条件：** mock `shutil.which("ffprobe")` 返回 `None`

**操作步骤：** 调用 `get_subtitle_streams(video_path)`

**预期结果：**

- 抛出 `RuntimeError`
- 异常信息提示需安装 ffprobe

**验收标准：** 通过

---

### 测试用例 TC-EXTRACT-09：ffmpeg 转换失败

**前置条件：** 准备一个字幕流编码无法转换为 SRT 的异常视频（mock ffmpeg 返回非 0 退出码）

**操作步骤：** 调用 `extract_embedded(video_path)`

**预期结果：**

- 抛出 `RuntimeError`
- 异常信息包含 ffmpeg 的 stderr 输出

**验收标准：** 通过

---

### 测试用例 TC-EXTRACT-10：输出 SRT 格式正确性

**前置条件：** 已知一个含字幕的视频，其首句字幕为 "测试字幕"

**操作步骤：** 调用 `extract_embedded(video_path)`，解析返回字符串

**预期结果：**

- SRT 序号从 1 开始递增
- 每条字幕包含序号行、时间轴行、文本行，块间以空行分隔
- 时间轴格式严格匹配 `HH:MM:SS,mmm --> HH:MM:SS,mmm`

**验收标准：** 通过
