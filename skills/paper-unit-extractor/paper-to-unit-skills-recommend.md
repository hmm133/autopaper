我们重新梳理了要素抽取的目标：为理解一篇论文提供结构化的完整画像，作为后续关系推理（宏观/微观图谱）的输入。基于之前的讨论，我整理出以下**最终推荐版要素类型及定义**。

------

## 一、顶层元数据（论文级别）

每个输出文件应包含一个顶层对象，包含论文级别的元数据：

json

```
{
  "paper_metadata": {
    "title": "论文标题",
    "authors": ["作者1", "作者2"],
    "affiliations": ["机构1", "机构2"],
    "year": 2024,
    "venue": "会议/期刊名 (或 arXiv)",
    "arxiv_id": "xxx",
    "doi": "xxx"
  },
  "units": [ ... ]
}
```



------

## 二、核心要素类型（共 8 种）

以下类型按**学术论证的自然逻辑顺序**排列，便于后续使用。

### 1. `research_question`

- **定义**：论文明确要解决的研究问题或具体任务。通常以问句或目标陈述形式出现。
- **示例**：“How to adapt a pre-trained model to new domains without retraining?”；“本文目标是提升长文本处理的效率。”
- **抽取规则**：如果论文没有明确写出研究问题，可以从引言中归纳出一句最核心的问题。允许为空数组。

### 2. `core_claim`

- **定义**：论文针对研究问题给出的**核心论点**。这是论文最原创、需要被论证的陈述。
- **示例**：“通过稀疏注意力机制，可以在长文本任务中同时提高速度和准确率。”
- **抽取规则**：通常出现在摘要、引言末尾、结论开头。允许多个（如论文有多个并列贡献）。优先级高于 `research_question` 和 `formal_conclusion`。

### 3. `formal_conclusion`

- **定义**：经过验证后**确认成立**的具体发现。通常带有实证结果或数据支撑。
- **示例**：“实验表明，在 8k 上下文下，本文方法比 Transformer 快 3 倍，准确率下降不到 1%。”
- **抽取规则**：通常出现在实验部分或结论段。如果与 `core_claim` 高度重合（如理论论文），可以省略，但建议保留以区分论点与验证结果。允许为空数组。

### 4. `method`

- **定义**：论文提出的方法、框架、算法、系统设计、建模策略或程序化解决方案。
- **示例**：“本文采用稀疏注意力机制，仅计算每个 token 与固定窗口内 token 的注意力。”
- **抽取规则**：允许多个（例如多个模块）。避免摘录实现细节（如“学习率为 0.001”），除非对比较重要。

### 5. `evidence`

- **定义**：支撑 `core_claim` 或 `formal_conclusion` 的具体依据。包括实验验证、仿真结果、理论证明、案例分析、用户调研等。
- **示例**：“在 LongBench 基准上，本文方法在 8 个任务中的 6 个上超过了基线模型。”；“定理 1 证明了模型收敛性。”
- **抽取规则**：每个 `evidence` 应明确说明支撑哪个 `core_claim` 或 `formal_conclusion`（可通过 ID 引用）。允许多个。可以区分类型：`experimental`、`theoretical`、`simulation`、`case_study` 等。

### 6. `limitation`

- **定义**：作者明确承认的局限性、边界条件、未覆盖情况或权衡。
- **示例**：“本文方法在处理极长文本（>32k token）时内存占用仍然较高。”；“实验仅在英文数据上进行，对其他语言的泛化性未知。”
- **抽取规则**：只抽取作者自己指出的局限，不要替作者“发现”局限。允许多个。

### 7. `assumption`

- **定义**：方法或结论成立所依赖的前提条件。如果违反，则结论不成立或方法失效。
- **示例**：“假设输入序列长度不超过 2048”；“假设数据服从 i.i.d. 分布”；“假设用户反馈真实无偏”。
- **抽取规则**：通常出现在方法论或理论分析部分。允许多个。如果某论文没有明确假设，可以省略。

### 8. `scope` (或 `context`)

- **定义**：论文工作的应用场景、任务类型、数据域、环境等背景信息。用于后续过滤或分组。
- **示例**：“任务：图像分类；领域：自然图像；数据集：ImageNet”；“场景：自动驾驶仿真；传感器：激光雷达”。
- **抽取规则**：输出为键值对或结构化字符串。允许多个（如论文研究多个设置）。不作为独立节点，仅作为过滤元数据。

### 9. `resource` (可选但推荐)

- **定义**：与论文相关的可复用资产，区分**产出** (`produced`) 和**使用** (`used`)。
- **子类型**：dataset, code, model, benchmark, software, etc.
- **示例**：
  - 产出：`{ "type": "dataset", "name": "CIFAR-10-N", "role": "produced" }`
  - 使用：`{ "type": "dataset", "name": "ImageNet", "role": "used" }`
- **抽取规则**：允许多个。如果论文没有提及任何资源，可以为空数组。

------

## 三、输出格式规范（统一结构）

每个 `unit` 应遵循以下结构：

json

```
{
  "id": "paperXXX_unitY",   // 唯一标识，便于后续引用
  "type": "core_claim",     // 上述类型之一
  "subtype": null,          // 可选，如 claim 可细分 "problem" / "claim" / "conclusion"
  "text": "具体内容",        // 完整的自然语言描述
  "evidence_refs": ["evidence_id_1"], // 仅当 type 为 claim/conclusion 时可选
  "source": {
    "section": "3.2",
    "quote": "原文字句",
    "page": 12,
    "char_range": [1200, 1450]  // 可选，精确定位
  }
}
```



对于 `evidence` 类型，额外增加：

json

```
{
  "type": "evidence",
  "supports": ["claim_id_1", "conclusion_id_2"], // 引用的 claim/conclusion ID
  "evidence_type": "experimental", // experimental / theoretical / simulation / case_study
  "text": "...",
  "source": { ... }
}
```



对于 `resource` 类型，额外增加：

json

```
{
  "type": "resource",
  "subtype": "dataset",   // dataset, code, model, benchmark, software
  "name": "CIFAR-10",
  "role": "used",         // used / produced
  "source": { ... }
}
```



对于 `scope` 类型，输出为键值对：

json

```
{
  "type": "scope",
  "attributes": {
    "task": "image classification",
    "domain": "natural images",
    "dataset": "CIFAR-10"
  },
  "source": { ... }
}
```



------

## 四、与原始设计的差异说明

| 原始类型                     | 调整后                | 原因                                     |
| :--------------------------- | :-------------------- | :--------------------------------------- |
| `research_problem`           | → `research_question` | 名称更通用，便于区分于 problem-solving。 |
| `core_claim`                 | 保留                  | 核心论点。                               |
| `formal_conclusion`          | 保留                  | 验证后的具体发现。                       |
| `method`                     | 保留                  | 方法描述。                               |
| `validation_logic`           | → `evidence`          | 更通用，支持多种证据类型。               |
| `figure_backed_assertion`    | 合并入 `evidence`     | 作为证据的一种来源，不再单独成类型。     |
| `assumption_or_prerequisite` | → `assumption`        | 简化名称。                               |
| `scope_or_setting`           | → `scope`             | 简化名称，输出结构化属性。               |
| `limitation`                 | 保留                  | 局限性。                                 |
| (新增) `resource`            | 新增                  | 区分产出/使用的资源。                    |
| (新增) 元数据                | 新增                  | 论文级别的作者、年份等。                 |

------

## 五、给 LLM 的执行提示（精简版）

在 `SKILL.md` 中应强调：

1. **中粒度**：每个 unit 应表达一个完整的学术观点（通常 10-50 词），避免单句碎片化，也避免段落式总结。
2. **允许多个**：每种类型都可以有 0~N 个实例，不要假定只有 1 个。
3. **必须提供来源**：每个 unit 必须包含 `source` 字段（section, quote）。
4. **证据引用**：`evidence` 必须通过 `supports` 字段关联到具体的 claim 或 conclusion。
5. **空值处理**：如果某类型没有找到，输出空数组 `[]`，不要省略。

------



## Source 字段的潜在价值

1. **可追溯性**：当用户对某个关系产生疑问（例如“这个结论真的是论文里说的吗？”），能够快速定位到原文位置。
2. **冲突仲裁**：如果两篇论文的关系推理出现争议（比如 LLM 判断“支持”，但实际原文是反驳），source 字段可以让人工快速核查。
3. **前端交互**：点击图谱中的节点，可以展示原文引用或跳转到 PDF 对应位置。
4. **调试与优化**：当你迭代 Skill 的 Prompt 时，source 字段可以帮助你判断 LLM 提取的依据是否合理。

------

## Source 字段的成本

1. **LLM 输出复杂度增加**：要求输出 `section`、`page`、`quote` 会让 LLM 输出更长、更容易出错。
2. **解析难度增加**：从 PDF 中提取页码和段落引用本身就不稳定（尤其是双栏、扫描件）。
3. **存储和传输开销**：每个单元都带一段原文引用，会显著膨胀 JSON 文件体积。
4. **对图谱构建没有直接贡献**：节点之间的边（关系）不需要 source 信息也能生成。



可以考虑删除每个unit的source 字段或者说改为更轻量版本的。