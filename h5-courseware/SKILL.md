---
name: h5-courseware
display_name: "H5 课件生成器"
display_name_en: "H5 Courseware Generator"
description: >-
  将 Markdown 课件或培训大纲编排为苹果磨砂玻璃风格的单文件 H5 课件。
  适用于需要桌面键盘翻页、鼠标点击、移动端纵向滚动和左右滑动翻页的课件生成任务。
  AI 负责通读文档并自主生成 plan.json 页面规划；Python 脚本负责校验、确定性渲染和输出 HTML。
  触发词：做成 H5 课件、生成课件、可翻页演示、培训课件、幻灯 HTML、课程 H5、markdown 转课件、h5-courseware。
version: 1.2.0
author: Alchemy
agent_created: true
---

# H5 课件一键生成器

## 定位

将 Markdown 课件、培训材料或大纲生成单文件 HTML H5 课件。保留苹果风格磨砂玻璃视觉、章节主题色、键盘/点击/触摸翻页和移动端滚动能力。

采用两段式流程：

1. AI 通读 Markdown，理解内容结构、学习目标和信息关系，自主决定章节、页数、页面类型和每页信息密度，输出符合示例契约的 `plan.json`。
2. Python 脚本消费 `plan.json`，校验输入并确定性渲染 HTML。脚本不调用模型，也不替 AI 做内容编排。

## 输入与输出

推荐使用 Plan 模式：

```bash
python generate.py --plan plan.json --out 输出目录 --brand Alchemy
```

规则模式适用于结构工整的文档：

```bash
python generate.py input.md --brand Alchemy --out 输出目录
```

支持参数：

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
| `--normalize-dates` | 显式将符合课程规则的日期转换为“第 N 天”；默认关闭 |
| `--help` | 查看命令帮助 |

默认输出一个合并版文件：

```text
{out_dir}/{brand}_H5课件_完整版.html
```

脚本不默认生成分章节文件，也不会默认改写日期、URL 或旧品牌文本。需要清洗时必须显式传入对应开关。

## Plan 契约

最小结构参考 `plan.example.json`：

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

脚本会拒绝：空章节、缺少封面标题、未知页面类型、空主题色数组和非 `#RRGGBB` 颜色。非法输入以非零退出码结束，不静默回退。

已支持页面类型：`cover`、`promise`、`cards`、`rows`、`flow`、`contrast`、`price`、`steps`、`cta`、`split`、`columns3`、`qa`、`checkin`、`chips`。

## 弹出式详情卡片（detail）

**核心规则：有必要展示、但文字太多且过于细节、不便在主页面呈现的内容，一律做成可点击的弹出式详情卡片。** 主页面保持一屏一论点，细节下沉到弹卡。

适用内容包括但不限于：案例完整背景与数据口径、操作步骤全文、术语深读、Skill 用法详解、协议/许可证说明、对比分析、FAQ 长答案。

### 用法一：卡片条目挂 `detail` 字段

`cards`、`rows`、`flow.nodes`、`price.steps`、`steps`、`columns3.columns_data`、`qa` 的任意条目都可加 `detail`；渲染后该卡片带 `ⓘ 详情` 徽标，点击弹出磨砂玻璃 modal：

```json
{"title": "磁力金牛投放", "desc": "单商家冷启动案例", "detail": {
  "title": "磁力金牛 · 案例详情",
  "badge": "已核实",
  "source": "快手磁力引擎官方案例库",
  "body": "正文支持段落、- 列表、**粗体**、`行内代码`，空行分段。\n\n- 数据口径：单一商家，非平台平均\n- 结论：AIGC 素材 CTR 提升约 23%"
}}
```

`detail` 字段结构：

| 字段 | 必填 | 说明 |
|---|---|---|
| `body` | 是 | 弹卡正文，markdown-lite：段落 / `- 列表` / `**粗体**` / `` `行内代码` `` / 空行分段 |
| `title` | 否 | 弹卡标题，缺省时可读性下降，建议始终填写 |
| `badge` | 否 | 徽标，如 `已核实`、`教学示意`、`方法论`、`注意协议` |
| `source` | 否 | 来源/归因标注，有数据的地方强烈建议写 |

### 用法二：`chips` 胶囊词条页

适合「术语表 / Skill 清单 / 深读入口」这类一页多个词条的场景，每个胶囊点开弹卡：

```json
{"type": "chips", "title": "术语深读", "subtitle": "点击胶囊查看详解",
 "chips": [{"label": "Skill", "hint": "技能包", "detail": {"title": "Skill · 是什么", "body": "..."}}],
 "note": "页面底部备注（可选）"}
```

`chips` 页每个条目都必须带 `detail`（校验强制）。

### 设计原则（AI 编排时遵守）

1. **判断标准**：内容删掉主页面会缺论据，放上去又撑爆版面 → 做成弹卡；只放一句话概述在卡片 `desc`，完整内容进 `detail.body`。
2. **数据必须归因**：案例数据弹卡务必写 `source` 与 `badge`，无法核实的标注 `教学示意`，不得伪装成已核实。
3. **弹卡正文密度**：每张弹卡 100–400 字为宜，超长考虑拆两张卡。
4. **不要滥用**：一页弹卡数量 ≤ 卡片总数的一半；主页面自身能讲清楚的，不加弹卡。

### 交互实现（脚本内置，无需配置）

- modal 层 `z-index:300`，高于章节导航与进度点；ESC / 遮罩 / ✕ 三种关闭方式。
- 移动端 modal 为底部抽屉样式，touch 手势在 modal 打开时优先关闭弹卡而非翻页。
- 带滚动的容器（表格/代码）内横滑放行原生滚动，滑到尽头才翻页。
- 首屏 slide 初始化即激活，冷启动不空白。

## 安全与内容处理

- 用户文本和 Plan 文本默认 HTML escape。
- 仅恢复受支持的 `**粗体**`、`` `行内代码` `` 和换行；不保留原始 HTML 标签。
- 默认不修改日期、URL 或品牌。
- 品牌替换和日期规范化只有在显式传入开关时才执行。

## 视觉与交互

- 白色底色、低饱和 CSS 光斑和半透明磨砂玻璃卡片。
- 字体栈：`-apple-system`、`SF Pro Display`、`PingFang SC`。
- 默认主题色：`#0071e3`、`#5e5ce6`、`#d63384`、`#2da44e`、`#d97706`。
- 桌面端支持 `←/→/PageUp/PageDown/Space/Home/End`、左右区域点击和底部进度点跳转。
- 移动端支持上下滚动、左右滑动翻页、章节导航横向滚动。
- 移动端覆盖卡片网格、价格流程、报名步骤、双栏对比、三层卡片、表格、CTA 和封面布局，避免固定列数导致横向溢出。

## 质量检查

生成后至少验证：

1. `python -m py_compile generate.py`
2. `python generate.py --help`
3. 示例 Plan 能生成 HTML，且每个 slide 恰好对应一个可点击进度点。
4. 真实 Markdown 能生成 HTML。
5. 非法 Plan、非法颜色和未知页面类型返回非零错误。
6. 注入 HTML 不会原样进入输出（含 detail.body 内的 `<script>` 等标签）。
7. 主题样式位于 `<head>`，`</html>` 后无额外 HTML。
8. 含 `detail` 的 Plan 生成后：`detailable` 卡片数与 `DETAIL_DATA` 键数一致；modal 打开时键盘/滑动不翻页；输出含 `slides[current].classList.add('active')`。
9. 非法 detail（body 缺失/为空）与缺 detail 的 chips 条目返回非零错误。
10. 项目版和个人安装版 Skill 文件保持一致。

## 依赖

Python 3.8+，仅使用标准库：`argparse`、`copy`、`html`、`json`、`pathlib`、`re`、`sys`。
