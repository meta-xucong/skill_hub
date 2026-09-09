# H5 课件一键生成器（h5-courseware）

将 Markdown 课件、培训大纲或课程文档编排为**单文件 HTML H5 课件**的 Skill：苹果风格磨砂玻璃视觉、章节主题色、桌面键盘/点击翻页、移动端纵向滚动与滑动翻页。

v1.2.0 起内置**弹出式详情卡片**机制：有必要展示、但文字过多过于细节、不便在主页面呈现的内容（案例细节、术语深读、数据归因说明等），可在 `cards` / `rows` / `flow` / `price` / `steps` / `columns3` / `qa` 的任意条目上挂 `detail` 字段，或使用专用 `chips` 胶囊页型，渲染后点击弹出详情弹卡。

完整规则与契约见 [SKILL.md](SKILL.md)，完整 plan 示例见 [plan.example.json](plan.example.json)。

## 设计

两段式流程，AI 与脚本各司其职：

1. AI 通读 Markdown，理解结构、学习目标与信息关系，自主决定章节、页数、页面类型和信息密度，输出符合契约的 `plan.json`。
2. `generate.py` 消费 `plan.json`，校验输入并确定性渲染 HTML。脚本不调用模型，也不替 AI 做内容编排。

支持 14 种页面类型：`cover` / `promise` / `cards` / `rows` / `flow` / `contrast` / `price` / `steps` / `cta` / `split` / `columns3` / `qa` / `checkin` / `chips`。

内置交互防御（都是真实踩坑固化下来的）：

- 首屏冷启动激活（slides[0] 补 `active` 类）
- 弹卡打开时键盘/滑动只关弹卡不翻页，点击弹卡不触发区域翻页
- modal `z-index:300` 压过章节导航，移动端底部抽屉样式
- 滚动余量手势检测：横滑先滚内容、到尽头才翻页
- `</script>` 转义与 body 全量 HTML escape，防 XSS / 防结构破坏

## 使用

```bash
# Plan 模式（推荐，AI 生成 plan.json 后执行）
python generate.py --plan plan.json --out 输出目录 --brand Alchemy

# 规则模式（结构工整的文档直接转换）
python generate.py input.md --brand Alchemy --out 输出目录
```

仅依赖 Python 3.8+ 标准库，无第三方依赖。

## 安装

放入可发现的个人技能目录，例如：

```bash
git clone https://github.com/meta-xucong/h5-courseware.git ~/.workbuddy/skills/h5-courseware
```

目标目录已存在时不要覆盖，先检查它是否是本仓库的 Git 副本；本地已做过定制时，更新前先 `git diff` 看差异。

## 弹出式详情卡片示例

```json
{
  "type": "cards",
  "title": "案例",
  "cards": [
    {
      "title": "某品牌 AI 提效",
      "desc": "主页面一句话概述即可",
      "detail": {
        "title": "某品牌 AI 提效：完整复盘",
        "badge": "已核实",
        "source": "来源归因，必填可核数据的出处",
        "body": "细节正文。支持段落、- 列表、**粗体**、`代码`。"
      }
    }
  ]
}
```
