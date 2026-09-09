# h5-courseware

> 将 Markdown 课件或培训大纲编排为苹果磨砂玻璃风格的单文件 H5 课件。

适用于需要桌面键盘翻页、鼠标点击、移动端纵向滚动与左右滑动翻页的课件生成任务。白色低饱和背景、半透明磨砂玻璃卡片、章节主题色，输出为一个可直接双击打开的单文件 HTML。

## 核心原理

采用「AI 决策 + 脚本渲染」的两段式架构，通用性来自 AI 对内容的自主编排，一致性来自脚本的确定性渲染：

```
Markdown 文档 / 大纲
      ↓  AI 通读、理解、拆解
plan.json（页面规划：章节 / 页数 / 页面类型 / 每页内容）
      ↓  Python 确定性校验 + 渲染
单文件 H5 HTML（苹果风、可翻页、移动端自适应）
```

- **AI 负责**：理解内容结构、学习目标与信息关系，自主决定章节划分、每章页数、页面类型和每页信息密度，产出符合契约的 `plan.json`。
- **脚本负责**：消费 `plan.json`，做结构与页面类型校验，并确定性渲染 HTML。脚本不调用任何模型，也不替 AI 做内容编排。

## 使用方式

### 方式一：Plan 模式（推荐，通用性最强）

由 AI 先通读文档、产出 `plan.json`，再交给脚本渲染：

```bash
python generate.py --plan plan.json --out 输出目录 --brand Alchemy
```

### 方式二：规则模式（适合结构工整的文档）

直接喂 Markdown，由关键词规则自动匹配模板：

```bash
python generate.py input.md --brand Alchemy --out 输出目录
```

### 命令行参数

| 参数 | 说明 |
|---|---|
| `md_path` | Markdown 路径，与 `--plan` 二选一 |
| `--plan` | AI 编排 JSON 路径，与 `md_path` 二选一 |
| `--brand` | 品牌名；默认 `Alchemy` |
| `--title` | 覆盖课件标题 |
| `--out` | 输出目录；默认使用输入文件所在目录，规则模式为 `H5输出` |
| `--theme` | 逗号分隔的 `#RRGGBB` 主题色，可循环应用到章节 |
| `--merged-name` | 合并版 HTML 文件名 |
| `--replace-legacy-brand` | 显式将 `BOGUJIN` 替换为当前品牌；默认关闭 |
| `--normalize-dates` | 显式将符合课程规则的日期转换为「第 N 天」；默认关闭 |
| `--help` | 查看命令帮助 |

默认输出一个合并版文件：`{out_dir}/{brand}_H5课件_完整版.html`

脚本**不**默认生成分章节文件，也**不**默认改写日期、URL 或旧品牌文本；需要清洗时必须显式传入对应开关。

## plan.json 契约

最小结构参考 [`plan.example.json`](plan.example.json)：

```json
{
  "brand": "Alchemy",
  "title": "课件标题",
  "theme_colors": ["#0071e3", "#5e5ce6"],
  "chapters": [
    {
      "title": "课程总览",
      "nav_label": "总览",
      "cover": {"title": "课程总览"},
      "pages": [{"type": "cards", "title": "页面标题", "cards": []}]
    }
  ]
}
```

脚本会**拒绝**以下非法输入并以非零退出码结束（不静默回退）：

- 空章节 / 缺少封面标题
- 未知页面类型（不在支持列表内）
- 空主题色数组 / 非 `#RRGGBB` 颜色

### 已支持页面类型

`cover`、`promise`、`cards`、`rows`、`flow`、`contrast`、`price`、`steps`、`cta`、`split`、`columns3`、`qa`、`checkin`

## 安全与内容处理

- 用户文本与 Plan 文本默认做 HTML escape。
- 仅恢复受支持的 `**粗体**`、`` `行内代码` `` 与换行，不保留原始 HTML 标签或 `javascript:` 等危险协议。
- 默认不修改日期、URL 或品牌；品牌替换与日期规范化仅在显式传入开关时执行。

## 视觉与交互

- 白色底色、低饱和 CSS 光斑、半透明磨砂玻璃卡片。
- 字体栈：`-apple-system`、`SF Pro Display`、`PingFang SC`。
- 默认主题色：`#0071e3`、`#5e5ce6`、`#d63384`、`#2da44e`、`#d97706`。
- 桌面端：`←/→/PageUp/PageDown/Space/Home/End`、左右区域点击、底部进度点跳转。
- 移动端：上下滚动、左右滑动翻页、章节导航横向滚动；卡片网格 / 价格流程 / 报名步骤 / 双栏对比 / 三层卡片等布局已适配单列，避免横向溢出。

## 依赖

Python 3.8+，仅使用标准库：`argparse`、`copy`、`html`、`json`、`pathlib`、`re`、`sys`。

## 质量自检清单

新增或改动后至少验证：

1. `python -m py_compile generate.py`
2. `python generate.py --help`
3. 示例 Plan 能生成 HTML，且每个 slide 恰好对应一个可点击进度点。
4. 真实 Markdown 能生成 HTML。
5. 非法 Plan / 非法颜色 / 未知页面类型返回非零错误。
6. 注入的 HTML 不会原样进入输出。
7. 主题样式位于 `<head>`，`</html>` 后无额外 HTML。
8. 项目版与已安装版 Skill 文件保持一致。
