# Math Question Bank - Document Object Model

> 本文档定义整个题库系统的统一数据结构。
> 任何 OCR/解析工具的输出都必须先转换为本 Schema，再进入后续流水线。
>
> Schema 版本: 1.0.0

---

## 设计原则

1. **不可变（Immutable）**：每一层产出新数据，永远不修改上一层的数据。
2. **与来源解耦**：Schema 不出现任何 OCR 工具名称。
3. **信息保留（Information Preserving）**：Raw → Normalization 不丢失任何信息。
4. **引用而非复制**：Question / LLM 层通过 block_id 引用 Block，不复制文本。
5. **标注而非修改**：Question Detection 和 LLM 只新增 Annotation，不改 Block。
6. **完整溯源**：每个对象都能追溯到产出者、版本、时间。

---

## 流水线数据流

```
Raw (原始产出，永久保存，不可变)
  ↓
NormalizedDocument (统一 DOM，不可变)
  ↓
AnnotatedDocument (新增标注，不修改 Block)
  ↓
QuestionSet (题目对象，引用 Block)
  ↓
Markdown / SQLite / RAG
```

每一步产出独立文件，互不覆盖。

---

## Provenance（溯源信息）

贯穿所有层的通用溯源结构，每个需要溯源的对象都包含此字段。

```python
Provenance:
  source_tool: str              # 产出工具名（如 "mineru", "mathpix", "marker"）
  source_version: str           # 工具版本号
  source_raw_id: str | None     # 工具原始输出中的对应 ID（用于回溯到 OCR 原始结果）
  source_page: int | None       # 工具原始页码
  component: str                # 产出者组件（如 "normalizer", "rule_engine", "llm"）
  component_version: str        # 组件版本号
  model: str | None             # LLM 模型名（如 "qwen3-14b"），非 LLM 产出为 None
  prompt_version: str | None    # Prompt 版本号，非 LLM 产出为 None
  created_at: str               # ISO 8601 时间戳
```

---

## 第一层：Raw（原始产出）

由 OCR 工具直接产出，原样保存，不修改。

```
raw/
  {document_id}/
    source.pdf                  # 原始 PDF（可选，存档用）
    tool_output/                # OCR 工具原始输出
      content_list.json
      content_list_v2.json
      model.json
      ...
    images/                     # 工具提取的图片
    metadata.json               # 工具版本、运行参数、时间戳
```

---

## 第二层：NormalizedDocument（统一 DOM）

### 顶层结构

```python
NormalizedDocument:
  schema_version: str           # Schema 版本号（如 "1.0.0"）
  pipeline_version: str         # 流水线版本号
  document_id: str              # 全局唯一 ID
  source_path: str              # 原始文件路径
  created_at: str               # ISO 8601 时间戳
  tool: str                     # 产出工具名（仅用于溯源，不影响后续逻辑）
  tool_version: str
  tool_raw_dir: str             # 指向 raw/ 目录
  pages: list[Page]
  images: list[ImageAsset]      # 全局图片资产
  metadata: dict                # 工具特定的额外信息（原样保留）
```

### Page

```python
Page:
  page_number: int              # 页码（从 1 开始）
  width: float                  # 页面宽度（pt）
  height: float                 # 页面高度（pt）
  blocks: list[Block]           # 本页所有 Block，按阅读顺序排列
```

### Block

```python
Block:
  id: str                       # 全局唯一 ID（格式: "{document_id}_b{序号}"）
  page: int                     # 所在页码
  type: BlockType               # 枚举，见下方
  bbox: BBox                    # [x1, y1, x2, y2]，单位 pt
  polygon: list[list[float]] | None  # 多边形顶点 [(x,y), ...]，None 表示使用 bbox
  reading_order: int            # 页内阅读顺序（从 0 开始）
  confidence: float | None      # 工具给出的置信度（0-1），None 表示工具未提供

  # ---- 溯源信息 ----
  source: Provenance            # 完整溯源信息

  # ---- 类型相关字段（按 type 取值不同，使用不同字段组）----

  # BlockType.title
  title_content: list[Inline] | None
  level: int | None             # 标题层级（1=一级标题, 2=二级标题, ...）

  # BlockType.paragraph / BlockType.list_item
  inline_content: list[Inline] | None

  # BlockType.formula_block / BlockType.equation_interline
  latex: str | None             # 原始 LaTeX 字符串（不修改）
  math_type: str | None         # "latex" | "mathml" | "image_only"
  image_ref: str | None         # 引用 images[] 中的 image_id（公式图片）

  # BlockType.figure / BlockType.table
  image_ref: str | None
  caption: list[Inline] | None  # 图片/表格的标题说明

  # BlockType.page_header / BlockType.page_footer
  text: str | None              # 页眉/页脚纯文本

  # BlockType.page_number
  text: str | None              # 页码文本
```

### BlockType（枚举）

```python
class BlockType(str, Enum):
    # 语义类型
    title = "title"
    paragraph = "paragraph"
    list_item = "list_item"
    table = "table"
    figure = "figure"
    caption = "caption"

    # 公式类型
    formula_block = "formula_block"
    equation_interline = "equation_interline"

    # 页面结构
    page_header = "page_header"
    page_footer = "page_footer"
    page_number = "page_number"

    # 扩展（预留）
    aside = "aside"
    code_block = "code_block"
    unknown = "unknown"
```

### BBox

```python
BBox = list[float]  # [x1, y1, x2, y2]，左上角 + 右下角，单位 pt
```

### Inline（内联元素）

出现在 `paragraph.inline_content` 或 `title.title_content` 中。

```python
Inline:
  type: InlineType             # 枚举，见下方
  content: str                 # 文本内容或 LaTeX 字符串
  confidence: float | None     # 置信度
```

### InlineType（枚举）

```python
class InlineType(str, Enum):
    text = "text"
    formula = "formula"
    image = "image"
    unknown = "unknown"
```

### ImageAsset（全局图片资产）

```python
ImageAsset:
  image_id: str                # 全局唯一 ID（格式: "{document_id}_img{序号}"）
  path: str                    # 相对于 raw/ 目录的路径
  width: int | None            # 像素宽度
  height: int | None           # 像素高度
  mime_type: str               # "image/png" | "image/jpeg" | ...
  ocr_text: str | None         # 对图片内容的 OCR 文本（如有）
  source: Provenance           # 溯源信息
```

---

## 第三层：AnnotatedDocument（标注层）

Question Detection 和后续步骤在此层添加标注，不修改 Block。

```python
AnnotatedDocument:
  schema_version: str
  pipeline_version: str
  document_id: str             # 引用 NormalizedDocument
  normalized_version: str      # 引用的 NormalizedDocument 版本/时间戳
  created_at: str
  annotations: list[Annotation]
```

### Annotation（标注）

```python
Annotation:
  annotation_id: str           # 全局唯一 ID
  type: str                    # 标注类型（见下方）
  block_ids: list[str]         # 关联的 Block ID 列表（一个标注可跨多个 Block）
  score: float | None          # 置信度（0-1）
  provenance: Provenance       # 完整溯源信息
  metadata: dict               # 任意附加信息
```

### Annotation Type（预定义）

```python
# Question Detection 阶段产生的标注
"question_candidate"           # 可能是题目起始位置
"question_boundary"            # 题目边界（起止 Block）
"noise"                        # 确认为噪声（难度、笔记区等）
"question_number"              # 检测到的题号
"question_type_hint"           # 题型初步判断（选择/填空/解答）

# LLM 阶段产生的标注
"question_confirmed"           # LLM 确认的题目
"question_type"                # LLM 判断的精确题型
"cross_page_join"              # 跨页题目合并
"sub_question_split"           # 一题多问的子题分割
```

---

## 第四层：QuestionSet（题目对象）

LLM 产出的最终结构化题目，全部通过 block_ids 引用 Block。

### QuestionSet

```python
QuestionSet:
  schema_version: str
  pipeline_version: str
  set_id: str                  # 全局唯一 ID
  document_id: str             # 引用 NormalizedDocument
  source_pdf: str              # 原始 PDF 路径
  created_at: str
  questions: list[Question]
  provenance: Provenance       # 完整溯源信息
```

### Question

```python
Question:
  question_id: str             # 全局唯一 ID
  number: str | None           # 题号（如 "1", "18", "例2"）
  type: QuestionType           # 题型枚举
  stem_block_ids: list[str]    # 题干引用的 Block ID（按阅读顺序）
  answer_block_ids: list[str]  # 答案区引用的 Block ID（如有）
  sub_questions: list[SubQuestion] | None  # 一题多问
  source_annotation_id: str    # 引用 AnnotatedDocument 中的标注 ID
  provenance: Provenance       # 完整溯源信息
  metadata: dict               # 任意附加信息
```

### SubQuestion

```python
SubQuestion:
  sub_id: str
  label: str                   # "(1)" / "(a)" / "I." 等
  block_ids: list[str]         # 引用的 Block ID
```

### QuestionType（枚举）

```python
class QuestionType(str, Enum):
    choice = "choice"
    fill_blank = "fill_blank"
    true_false = "true_false"
    short_answer = "short_answer"
    calculation = "calculation"
    proof = "proof"
    comprehensive = "comprehensive"
    unknown = "unknown"
```

---

## Markdown 再生成规范

从 NormalizedDocument 重新生成 Markdown 的规则：

```
Block.type == title            →  "#" × level + " " + render(inline_content)
Block.type == paragraph        →  render(inline_content)
Block.type == formula_block    →  "$$" + latex + "$$"
Block.type == equation_interline → "$$" + latex + "$$" + "\n" + "![formula](image_ref)"
Block.type == figure           → "![caption](image_ref)"
Block.type == table            → "[表格内容]"
Block.type == page_header      → "---\n" + text + "\n---"
Block.type == page_number      → 忽略（或注释）
Block.type == aside            → "> " + text

Inline.type == text    →  content
Inline.type == formula →  "$" + content + "$"
Inline.type == image   →  "![inline](image_ref)"
```

由于所有 Block 和 Inline 都完整保留，Markdown 可以从 NormalizedDocument **任意时刻重新生成**。

---

## ID 生成规范

| 对象 | 格式 | 示例 |
|---|---|---|
| document_id | `{source_stem}_{hash8}` | `1-3_a3f2b1c8` |
| block_id | `{document_id}_b{0-padded-5}` | `1-3_a3f2b1c8_b00012` |
| image_id | `{document_id}_img{0-padded-4}` | `1-3_a3f2b1c8_img0003` |
| annotation_id | `{document_id}_ann{0-padded-5}` | `1-3_a3f2b1c8_ann00001` |
| question_id | `{document_id}_q{0-padded-4}` | `1-3_a3f2b1c8_q0001` |
| set_id | `{document_id}_qs{0-padded-3}` | `1-3_a3f2b1c8_qs001` |

hash8 取 source 文件名 + 文件大小的 MD5 前 8 位，确保同一文件不同运行产出相同 ID。

---

## 1-3.pdf 示例（节选第 0 页）

```json
{
  "schema_version": "1.0.0",
  "pipeline_version": "0.1.0",
  "document_id": "1-3_a3f2b1c8",
  "pages": [
    {
      "page_number": 1,
      "width": 595.0,
      "height": 841.0,
      "blocks": [
        {
          "id": "1-3_a3f2b1c8_b00001",
          "page": 1,
          "type": "title",
          "bbox": [352, 92, 559, 139],
          "polygon": null,
          "reading_order": 0,
          "confidence": null,
          "source": {
            "source_tool": "mineru",
            "source_version": "3.4.2",
            "source_raw_id": null,
            "source_page": 0,
            "component": "normalizer",
            "component_version": "0.1.0",
            "model": null,
            "prompt_version": null,
            "created_at": "2026-07-05T19:00:00Z"
          },
          "title_content": [
            {"type": "text", "content": "填空", "confidence": null}
          ],
          "level": 2
        },
        {
          "id": "1-3_a3f2b1c8_b00003",
          "page": 1,
          "type": "paragraph",
          "bbox": [154, 174, 744, 215],
          "polygon": null,
          "reading_order": 2,
          "confidence": null,
          "source": {
            "source_tool": "mineru",
            "source_version": "3.4.2",
            "source_raw_id": null,
            "source_page": 0,
            "component": "normalizer",
            "component_version": "0.1.0",
            "model": null,
            "prompt_version": null,
            "created_at": "2026-07-05T19:00:00Z"
          },
          "inline_content": [
            {"type": "text", "content": "设 ", "confidence": null},
            {"type": "formula", "content": "\\cdot \\operatorname*{lim}_{x \\to 0}...", "confidence": null},
            {"type": "text", "content": "，则 ", "confidence": null},
            {"type": "formula", "content": "\\operatorname*{lim}_{x \\to 0}...", "confidence": null}
          ]
        }
      ]
    }
  ]
}
```

---

## 信息保留验证清单

| Raw 中的信息 | NormalizedDocument 中 | 说明 |
|---|---|---|
| 文本内容 | Block.text 或 Inline(content) | 完整保留 |
| LaTeX 公式 | Inline(content) type=formula | 原始 LaTeX，不修改 |
| bbox 坐标 | Block.bbox | 原样保留 |
| 多边形坐标 | Block.polygon | 预留，None 表示使用 bbox |
| 页面维度 | Page.width, Page.height | 原样保留 |
| 置信度 | Block.confidence, Inline.confidence | 原样保留 |
| 文本层级 | Block.level（title） | 保留 |
| 图片文件 | ImageAsset.path | 原样引用 |
| 图片 bbox | Block.bbox（figure 类型） | 保留 |
| 表格 | Block.type=table | 预留结构 |
| 工具原始 ID | Block.source.source_raw_id | 保留用于回溯 |
| 工具版本 | Block.source.source_version | 保留 |
| 页码 | Block.source.source_page | 保留 |
| 页眉/侧边栏 | Block.type=page_header/aside | 保留 |

---

## 扩展预留

| 场景 | 扩展方式 |
|---|---|
| 几何图形 | ImageAsset + Block.type=figure + ocr_text |
| SVG | ImageAsset.mime_type="image/svg+xml" |
| 手写公式 | Inline.type=formula + confidence 较低 + 可选 ocr_text |
| 扫描件倾斜 | Block.polygon 记录实际四边形 |
| 多栏排版 | Block.bbox 的 x 坐标 + reading_order 综合判断 |
| 跨页 Block | Block.page 为 list（如 [3, 4]）或拆分 + annotation cross_page_join |
| 新 OCR 工具 | 实现一个 converter，输出 NormalizedDocument 即可 |
| 新题型 | 扩展 QuestionType 枚举 |
| Schema 升级 | schema_version 字段 + metadata 存储兼容信息 |
