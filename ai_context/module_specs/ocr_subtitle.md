# 硬字幕 OCR 模块规格说明（ocr_subtitle）

## 1. 模块职责描述

本模块负责对烧录在视频画面中的硬字幕进行 OCR 识别，将图像形式的字幕转换为带时间轴的文本字幕条目。

具体职责包括：

- 按固定时间间隔从视频画面底部区域（默认底部 15% 高度）抽取帧图像。
- 使用 PaddleOCR 对每帧底部字幕区域进行文本识别。
- 将连续多帧中识别出的相同文本进行合并，生成带开始/结束时间戳的字幕条目。
- 返回符合统一字幕条目格式 `{"start": float, "end": float, "text": str}` 的列表。

本模块处理硬字幕（已烧录到画面的字幕），与软字幕提取模块（`subtitle_extractor`）互补，适用于无内嵌字幕流但画面含字幕的视频。

---

## 2. 公共函数/类签名

### 2.1 `extract_ocr_subtitles(video_path: str) -> Optional[list[dict]]`

```python
def extract_ocr_subtitles(video_path: str) -> Optional[list[dict]]
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `video_path` | `str` | 视频文件路径 |

**返回值：** `Optional[list[dict]]`

- 识别到字幕时：返回字幕条目列表，每项为 `{"start": float, "end": float, "text": str}`。
- 视频无效或全程未识别到任何文本时：返回 `None`。

**行为描述：**

协调内部三个步骤完成完整流程：
1. 调用 `_extract_frames` 抽取底部区域帧。
2. 调用 `_ocr_recognize` 识别帧文本。
3. 调用 `_merge_subtitles` 合并连续相同条目。

### 2.2 `_extract_frames(video_path, interval, ratio) -> list[tuple]`

```python
def _extract_frames(
    video_path: str,
    interval: float = 1.0,
    ratio: float = 0.15
) -> list[tuple]
```

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `video_path` | `str` | - | 视频文件路径 |
| `interval` | `float` | `1.0` | 抽帧间隔（秒） |
| `ratio` | `float` | `0.15` | 从底部截取的画面高度比例 |

**返回值：** `list[tuple]` —— 每个元组为 `(timestamp: float, frame_path: str)`，`timestamp` 为该帧对应的时间点（秒），`frame_path` 为临时帧图像文件路径。

### 2.3 `_ocr_recognize(frame_paths) -> list[str]`

```python
def _ocr_recognize(frame_paths: list[str]) -> list[str]
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `frame_paths` | `list[str]` | 帧图像文件路径列表 |

**返回值：** `list[str]` —— 与输入顺序对应的识别文本列表，每帧一个字符串；未识别到文本时对应位置为空字符串 `""`。

### 2.4 `_merge_subtitles(entries, threshold) -> list[dict]`

```python
def _merge_subtitles(
    entries: list[tuple],
    threshold: float = 0.5
) -> list[dict]
```

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `entries` | `list[tuple]` | - | 形如 `[(timestamp, text), ...]` 的原始识别条目 |
| `threshold` | `float` | `0.5` | 连续两帧时间间隔超过此值则断开，形成新条目 |

**返回值：** `list[dict]` —— 合并后的字幕条目，每项为 `{"start": float, "end": float, "text": str}`。

---

## 3. 输入数据格式

### 3.1 视频输入

`video_path` 为字符串路径，指向含硬字幕的视频文件。视频需能被 ffmpeg 解码，画面底部区域应包含字幕文本。

### 3.2 内部抽帧输出（`_extract_frames` 产物）

抽帧产生的临时图像为 PNG 格式，命名形如 `frame_000123.png`，存放在临时目录。每帧仅包含视频底部 `ratio` 比例的画面区域（裁剪后图像）。

ffmpeg 抽帧命令示例：

```bash
ffmpeg -v quiet -i <video_path> -vf "crop=iw:ih*0.15:0:ih*0.85,fps=1" -f image2 frame_%06d.png
```

- `crop=iw:ih*0.15:0:ih*0.85`：宽度不变，高度取底部 15%，纵向偏移为画面高度的 85%。
- `fps=1`：每秒抽取 1 帧。

### 3.3 OCR 输入帧图像

PNG 图像，仅含字幕文本行区域，分辨率与视频宽度一致、高度为视频高度的 15%。

---

## 4. 输出数据格式

### 4.1 `extract_ocr_subtitles` 返回值

成功识别示例：

```python
[
    {"start": 1.0, "end": 4.0, "text": "你好世界"},
    {"start": 5.0, "end": 8.0, "text": "这是第二句字幕"},
    {"start": 10.0, "end": 13.0, "text": "谢谢观看"}
]
```

| 键 | 类型 | 说明 |
|----|------|------|
| `start` | `float` | 字幕开始时间（秒） |
| `end` | `float` | 字幕结束时间（秒） |
| `text` | `str` | 识别出的字幕文本 |

无识别结果时返回：

```python
None
```

### 4.2 `_ocr_recognize` 返回值

```python
["你好世界", "你好世界", "", "这是第二句字幕"]
```

与 `frame_paths` 一一对应，未识别到文本的位置为空字符串。

---

## 5. 关键算法说明

### 5.1 底部区域抽帧算法

使用 ffmpeg 的 `crop` 滤镜截取画面底部区域，再用 `fps` 滤镜控制抽帧速率：

- 默认 `ratio=0.15`：字幕通常位于画面底部 15% 区域。
- 默认 `interval=1.0`：每秒一帧，兼顾覆盖度与性能。

抽帧时记录每帧的时间戳。由于 ffmpeg `image2` 输出按序号命名，时间戳通过 `序号 * interval` 计算得到，从而与图像一一对应。

### 5.2 PaddleOCR 识别算法

使用 PaddleOCR 的检测+识别管线对每帧图像处理：

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_angle_cls=False, lang="ch")  # 中文模型
result = ocr.ocr(frame_path, cls=False)
```

对返回结果的处理：

- `result[0]` 为检测到的文本行列表，每项含 `[box, (text, confidence)]`。
- 取所有文本行的 `text`，按从上到下、从左到右拼接为单帧字符串。
- 若无检测结果（`result` 为空或 `None`），该帧文本记为 `""`。

文本拼接时使用空格分隔多行，并去除首尾空白。

### 5.3 连续相同文本合并算法

合并逻辑基于"相同文本且时间连续"的判断：

```python
def _merge_subtitles(entries, threshold=0.5):
    merged = []
    current = None
    for ts, text in entries:
        text = text.strip()
        if not text:
            # 空文本：结束当前条目
            if current:
                current["end"] = ts
                merged.append(current)
                current = None
            continue
        if current and text == current["text"] and (ts - last_ts) <= threshold:
            # 文本相同且时间连续：延长结束时间
            current["end"] = ts
            last_ts = ts
        else:
            # 新文本或时间断开：收尾并新建
            if current:
                current["end"] = ts
                merged.append(current)
            current = {"start": ts, "end": ts, "text": text}
            last_ts = ts
    if current:
        merged.append(current)
    return merged
```

关键点：

- **相同文本判定**：去除首尾空白后完全相等。
- **时间连续判定**：相邻两帧时间差 `<= threshold`（默认 0.5 秒，因抽帧间隔 1 秒，故连续帧差为 1.0 > 0.5 时会被视为断开——此处 threshold 用于容忍抽帧抖动，实际连续帧差应 <= interval + threshold）。
- **空文本处理**：遇到未识别帧（空字符串）时，结束当前正在累积的条目，形成时间断点。
- **结束时间**：取该条目最后一次出现相同文本的帧时间戳。

> 说明：`threshold` 语义为"允许的时间间隔容差"。因 `interval=1.0`，连续两帧理想间隔为 1.0 秒。设 `threshold=0.5` 时，实际判定条件 `ts - last_ts <= interval + threshold` 用于合并，确保抽帧抖动下仍能正确合并。

---

## 6. 异常处理策略

| 异常场景 | 处理策略 |
|----------|----------|
| `video_path` 文件不存在 | 抛出 `FileNotFoundError` |
| `video_path` 为空字符串 | 抛出 `ValueError` |
| ffmpeg 抽帧失败（视频损坏） | 抛出 `RuntimeError`，含 stderr 信息 |
| ffmpeg 未安装 | 抛出 `RuntimeError`，提示需安装 ffmpeg |
| 抽帧数为 0 | `extract_ocr_subtitles` 返回 `None` |
| PaddleOCR 初始化失败（模型缺失） | 抛出 `RuntimeError`，提示模型未正确安装 |
| 单帧 OCR 调用异常 | 捕获并记该帧文本为 `""`，不中断整体流程 |
| 临时帧文件写入失败 | 抛出 `IOError`，含路径信息 |
| 识别结果全部为空 | `extract_ocr_subtitles` 返回 `None` |
| 临时文件清理失败 | 记录警告但不抛出异常（使用 `try/except` 包裹清理） |

**核心原则：**

- OCR 识别是容错密集型操作，单帧失败不应中断整体流程。
- 临时帧文件在流程结束后应清理，清理失败不影响返回结果。
- "无字幕识别结果"为合法业务结果，返回 `None` 而非异常。

---

## 7. 测试用例及验收标准

### 测试用例 TC-OCR-01：识别底部硬字幕

**前置条件：** 准备一段含中文字幕的视频，字幕位于底部 15% 区域，字幕文本为 "测试字幕内容"

**操作步骤：** 调用 `extract_ocr_subtitles(video_path)`

**预期结果：**

- 返回值不为 `None`
- 列表中至少包含一个 `text` 含 "测试字幕内容" 的条目
- 每个条目含 `start`、`end`、`text` 三个键
- `start < end` 对所有条目成立

**验收标准：** 通过

---

### 测试用例 TC-OCR-02：合并连续相同字幕

**前置条件：** 准备视频，同一句字幕 "你好" 持续显示 3 秒（对应 3 帧）

**操作步骤：** 调用 `extract_ocr_subtitles(video_path)`

**预期结果：**

- "你好" 仅作为一条条目出现
- 该条目 `end - start` 约等于 2.0 秒（3 帧跨度，首帧到末帧）

**验收标准：** 通过

---

### 测试用例 TC-OCR-03：字幕切换断开

**前置条件：** 准备视频，1-3 秒显示 "第一句"，5-7 秒显示 "第二句"（中间有 1 秒空白）

**操作步骤：** 调用 `extract_ocr_subtitles(video_path)`

**预期结果：**

- 返回两条条目
- 第一条 `text` 含 "第一句"，第二条 `text` 含 "第二句"
- 第一条 `end` < 第二条 `start`

**验收标准：** 通过

---

### 测试用例 TC-OCR-04：无字幕视频

**前置条件：** 准备一段画面底部无任何文本的视频

**操作步骤：** 调用 `extract_ocr_subtitles(video_path)`

**预期结果：**

- 返回值为 `None`
- 不抛出异常

**验收标准：** 通过

---

### 测试用例 TC-OCR-05：底部区域裁剪正确性

**前置条件：** 视频分辨率 1920x1080，字幕位于底部

**操作步骤：** 调用 `_extract_frames(video_path, interval=1.0, ratio=0.15)`

**预期结果：**

- 返回列表非空
- 每个元组第二项指向真实存在的 PNG 文件
- 抽取的帧图像高度约为 162 像素（1080 * 0.15）
- 帧图像宽度为 1920

**验收标准：** 通过

---

### 测试用例 TC-OCR-06：OCR 识别空帧

**前置条件：** 准备一帧纯背景无文本的图像

**操作步骤：** 调用 `_ocr_recognize([frame_path])`

**预期结果：**

- 返回 `[""]`（长度为 1 的列表，元素为空字符串）
- 不抛出异常

**验收标准：** 通过

---

### 测试用例 TC-OCR-07：合并阈值行为

**前置条件：** 构造 entries = `[(1.0, "A"), (2.0, "A"), (5.0, "A")]`，threshold=0.5

**操作步骤：** 调用 `_merge_subtitles(entries, threshold=0.5)`

**预期结果：**

- 返回 2 条条目
- 第一条 `{start:1.0, end:2.0, text:"A"}`（1.0 与 2.0 间隔 1.0 在合并容差内连续）
- 第二条 `{start:5.0, end:5.0, text:"A"}`（2.0 到 5.0 间隔 3.0 超过容差断开）

**验收标准：** 通过

---

### 测试用例 TC-OCR-08：文件不存在

**前置条件：** `video_path = "/nonexistent/video.mp4"`

**操作步骤：** 调用 `extract_ocr_subtitles(video_path)`

**预期结果：**

- 抛出 `FileNotFoundError`

**验收标准：** 通过

---

### 测试用例 TC-OCR-09：单帧 OCR 异常容错

**前置条件：** mock PaddleOCR 对某帧抛出异常

**操作步骤：** 调用 `_ocr_recognize([frame1, bad_frame, frame3])`

**预期结果：**

- 返回列表长度为 3
- 异常帧对应位置为 `""`
- 其他帧正常返回文本
- 不抛出异常

**验收标准：** 通过

---

### 测试用例 TC-OCR-10：临时文件清理

**前置条件：** 正常执行一次完整 OCR 提取

**操作步骤：** 调用 `extract_ocr_subtitles(video_path)` 后检查临时目录

**预期结果：**

- 临时抽帧 PNG 文件已被清理
- 返回结果不受清理影响

**验收标准：** 通过
