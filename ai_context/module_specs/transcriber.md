# Whisper 语音转文字模块规格说明（transcriber）

## 1. 模块职责描述

本模块负责将视频中的音频通过 OpenAI Whisper 模型转换为带时间戳的文本字幕条目，作为无字幕流视频的字幕来源之一。

具体职责包括：

- 加载指定规格的 Whisper 语音识别模型（如 `medium`、`small`）。
- 从视频文件中提取音频并转换为 16kHz 单声道 WAV 格式（Whisper 标准输入）。
- 对音频执行语音转写，产出带时间戳的文本片段。
- 将 Whisper 原始输出归一化为统一的字幕条目格式 `{"start": float, "end": float, "text": str}`。
- 支持指定源语言以及是否将非英文内容翻译为英文。

本模块与软字幕提取、硬字幕 OCR 三者互为补充，共同覆盖字幕获取的不同来源。

---

## 2. 公共函数/类签名

### 2.1 `Transcriber` 类

```python
class Transcriber:
    def __init__(
        self,
        model_size: str = "medium",
        language: Optional[str] = None,
        translate: bool = False
    )
```

**构造参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model_size` | `str` | `"medium"` | Whisper 模型规格，可选 `tiny`/`base`/`small`/`medium`/`large` |
| `language` | `Optional[str]` | `None` | 源语言代码（如 `"zh"`、`"en"`），`None` 表示自动检测 |
| `translate` | `bool` | `False` | `True` 时将转写结果翻译为英文 |

**实例属性：**

| 属性 | 类型 | 说明 |
|------|------|------|
| `model_size` | `str` | 保存构造传入的模型规格 |
| `language` | `Optional[str]` | 保存构造传入的语言 |
| `translate` | `bool` | 保存是否翻译 |
| `model` | 模型对象 | 懒加载的 Whisper 模型，初始为 `None` |

### 2.2 `transcribe(self, audio_path: str) -> list[dict]`

```python
def transcribe(self, audio_path: str) -> list[dict]
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `audio_path` | `str` | WAV 音频文件路径（建议 16kHz 单声道） |

**返回值：** `list[dict]` —— 字幕条目列表，每项为 `{"start": float, "end": float, "text": str}`。

**行为描述：**

1. 若模型未加载，调用 `_load_model()` 加载。
2. 调用 `whisper.transcribe()` 转写音频。
3. 遍历结果的 `segments`，提取每段的 `start`、`end`、`text`。
4. 返回归一化后的字幕条目列表。

### 2.3 `extract_audio(self, video_path: str, temp_dir: str) -> str`

```python
def extract_audio(self, video_path: str, temp_dir: str) -> str
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `video_path` | `str` | 视频文件路径 |
| `temp_dir` | `str` | 临时目录路径，用于存放提取的 WAV |

**返回值：** `str` —— 提取的 WAV 音频文件绝对路径。

**行为描述：**

使用 ffmpeg 从视频中提取音频，重采样为 16kHz、单声道、16-bit PCM WAV。

### 2.4 `_load_model(self)`

```python
def _load_model(self)
```

**参数：** 仅 `self`

**返回值：** 无（设置实例属性 `self.model`）

**行为描述：**

调用 `whisper.load_model(self.model_size)` 加载模型并赋值给 `self.model`，使其后续可复用。

---

## 3. 输入数据格式

### 3.1 视频文件输入（`extract_audio`）

`video_path` 指向含音频流的视频文件。ffmpeg 命令提取音频：

```bash
ffmpeg -v quiet -i <video_path> -ar 16000 -ac 1 -c:a pcm_s16le <output.wav>
```

参数说明：

- `-ar 16000`：采样率 16kHz（Whisper 要求）。
- `-ac 1`：单声道。
- `-c:a pcm_s16le`：16-bit PCM 编码。

### 3.2 音频文件输入（`transcribe`）

`audio_path` 指向 WAV 文件，格式要求：

- 采样率：16000 Hz
- 声道数：1（单声道）
- 编码：PCM 16-bit
- 容器：WAV

### 3.3 Whisper 原始输出（内部数据）

`whisper.transcribe()` 返回的字典结构示例：

```json
{
  "text": "完整拼接文本",
  "language": "zh",
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 2.5,
      "text": "这是第一句话"
    },
    {
      "id": 1,
      "start": 2.5,
      "end": 5.0,
      "text": "这是第二句话"
    }
  ]
}
```

---

## 4. 输出数据格式

### 4.1 `transcribe` 返回值

```python
[
    {"start": 0.0, "end": 2.5, "text": "这是第一句话"},
    {"start": 2.5, "end": 5.0, "text": "这是第二句话"}
]
```

| 键 | 类型 | 说明 |
|----|------|------|
| `start` | `float` | 片段开始时间（秒） |
| `end` | `float` | 片段结束时间（秒） |
| `text` | `str` | 转写文本，已去除首尾空白 |

### 4.2 `extract_audio` 返回值

返回 WAV 文件绝对路径字符串，形如：

```
/tmp/subtitle_tool/video_name_16k.wav
```

---

## 5. 关键算法说明

### 5.1 模型懒加载策略

模型在 `__init__` 中不立即加载，而是在首次调用 `transcribe()` 时通过 `_load_model()` 加载。优势：

- 避免构造对象即占用显存。
- 多次 `transcribe` 调用复用同一模型实例，无需重复加载。

```python
def _load_model(self):
    if self.model is None:
        import whisper
        self.model = whisper.load_model(self.model_size)
```

### 5.2 音频提取算法

调用 ffmpeg 将任意视频音频流重采样为 Whisper 标准格式。16kHz 单声道 PCM 是 Whisper 模型的最佳输入格式，能保证识别质量与速度。

通过 `subprocess.run()` 执行 ffmpeg，输出路径基于视频名拼接，确保唯一性。

### 5.3 转写与翻译控制

```python
result = self.model.transcribe(
    audio_path,
    language=self.language,   # None 表示自动检测
    task="translate" if self.translate else "transcribe"
)
```

- `language` 为 `None` 时 Whisper 自动检测源语言。
- `translate=True` 时 `task` 设为 `"translate"`，输出英文；否则 `task="transcribe"` 保持源语言。

### 5.4 段落归一化算法

Whisper 返回的 `segments` 每段含 `start`、`end`、`text`，直接映射为统一条目：

```python
def transcribe(self, audio_path):
    self._load_model()
    result = self.model.transcribe(
        audio_path,
        language=self.language,
        task="translate" if self.translate else "transcribe"
    )
    entries = []
    for seg in result.get("segments", []):
        entries.append({
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "text": seg["text"].strip()
        })
    return entries
```

归一化要点：

- `start`、`end` 强制转为 `float`，避免 numpy 标量类型。
- `text` 去除首尾空白字符。
- `segments` 缺失时返回空列表而非异常。

---

## 6. 异常处理策略

| 异常场景 | 处理策略 |
|----------|----------|
| `video_path` 不存在 | `extract_audio` 抛出 `FileNotFoundError` |
| 视频无音频流 | ffmpeg 退出码非 0，抛出 `RuntimeError`，提示无音频流 |
| ffmpeg 未安装 | 抛出 `RuntimeError`，提示需安装 ffmpeg |
| `temp_dir` 不存在 | 抛出 `FileNotFoundError` 或自动创建（由 `ensure_dir` 配合） |
| `model_size` 非法值 | `whisper.load_model` 抛出异常，透传给调用方 |
| 模型下载失败（网络问题） | 抛出 `RuntimeError`，提示检查网络或使用本地缓存 |
| 音频文件损坏 | `transcribe` 抛出异常，由调用方处理 |
| GPU 显存不足（CUDA OOM） | 抛出 `RuntimeError`，提示降低模型规格或使用 CPU |
| `segments` 为空 | 返回空列表 `[]`，不抛异常 |
| `text` 含非法字符 | 保留原始文本，仅做 strip 处理 |

**核心原则：**

- 模型加载失败属于环境级错误，应抛出明确异常。
- 转写结果为空是合法结果，返回空列表。
- 音频提取失败多为视频问题，抛出含 ffmpeg 错误信息的异常。

---

## 7. 测试用例及验收标准

### 测试用例 TC-TRANS-01：转写中文音频

**前置条件：** 准备一段含中文语音的 WAV 文件（16kHz 单声道），内容为 "你好，这是一段测试语音"

**操作步骤：**

```python
t = Transcriber(model_size="small", language="zh")
result = t.transcribe(audio_path)
```

**预期结果：**

- 返回列表非空
- 拼接所有 `text` 含 "你好"、"测试" 等关键词
- 每个条目 `start < end`
- 时间戳为非负浮点数

**验收标准：** 通过

---

### 测试用例 TC-TRANS-02：自动检测语言

**前置条件：** 准备英文音频，`language=None`

**操作步骤：**

```python
t = Transcriber(model_size="small", language=None)
result = t.transcribe(audio_path)
```

**预期结果：**

- 成功返回字幕条目
- 转写文本为英文

**验收标准：** 通过

---

### 测试用例 TC-TRANS-03：翻译为英文

**前置条件：** 准备中文音频，`translate=True`

**操作步骤：**

```python
t = Transcriber(model_size="small", language="zh", translate=True)
result = t.transcribe(audio_path)
```

**预期结果：**

- 返回条目文本为英文
- 时间戳保留源语言片段对应的时间

**验收标准：** 通过

---

### 测试用例 TC-TRANS-04：提取音频

**前置条件：** 准备含音频流的视频文件

**操作步骤：** 调用 `extract_audio(video_path, temp_dir)`

**预期结果：**

- 返回的路径指向真实存在的 WAV 文件
- 文件大小 > 0
- WAV 采样率为 16000Hz，单声道

**验收标准：** 通过

---

### 测试用例 TC-TRANS-05：模型懒加载

**前置条件：** 新建 `Transcriber` 实例但尚未调用 `transcribe`

**操作步骤：**

```python
t = Transcriber(model_size="small")
assert t.model is None
t.transcribe(audio_path)
assert t.model is not None
```

**预期结果：**

- 构造后 `t.model` 为 `None`
- 首次 `transcribe` 后 `t.model` 非 `None`
- 再次 `transcribe` 不重复加载（可 mock 验证 `load_model` 仅调用一次）

**验收标准：** 通过

---

### 测试用例 TC-TRANS-06：模型复用

**前置条件：** 已加载模型的 `Transcriber` 实例

**操作步骤：** 连续两次调用 `transcribe(audio_path)`

**预期结果：**

- 两次均返回有效结果
- 模型仅加载一次（`_load_model` 第二次不触发实际加载）

**验收标准：** 通过

---

### 测试用例 TC-TRANS-07：无音频流的视频

**前置条件：** 准备一个纯视频无音频流的文件

**操作步骤：** 调用 `extract_audio(video_path, temp_dir)`

**预期结果：**

- 抛出 `RuntimeError`
- 异常信息提示无音频流或 ffmpeg 错误

**验收标准：** 通过

---

### 测试用例 TC-TRANS-08：视频文件不存在

**前置条件：** `video_path = "/nonexistent/video.mp4"`

**操作步骤：** 调用 `extract_audio(video_path, temp_dir)`

**预期结果：**

- 抛出 `FileNotFoundError`

**验收标准：** 通过

---

### 测试用例 TC-TRANS-09：空 segments 返回空列表

**前置条件：** mock Whisper 返回 `{"segments": []}`

**操作步骤：** 调用 `transcribe(audio_path)`

**预期结果：**

- 返回 `[]`（空列表）
- 不抛出异常

**验收标准：** 通过

---

### 测试用例 TC-TRANS-10：非法模型规格

**前置条件：** `model_size = "nonexistent"`

**操作步骤：** 调用 `transcribe(audio_path)` 触发 `_load_model()`

**预期结果：**

- 抛出异常（Whisper 层面）
- 异常信息可辨识为模型规格非法

**验收标准：** 通过
