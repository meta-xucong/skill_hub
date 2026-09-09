# skill_hub

个人 AI Skill 集合仓库。用于统一收纳、版本化、分享我自己编写的 WorkBuddy / CodeBuddy Skill，便于复用与演进。

## 仓库结构

每个 skill 独立占用一个以 skill 命名的文件夹，内部至少包含：

- `SKILL.md`：Skill 元数据（YAML frontmatter）与说明
- 逻辑脚本 / 提示词 / 模板等附属文件
- 至少一个可运行的示例

```
skill_hub/
├── README.md              # 本文件：仓库总说明
└── h5-courseware/         # 第一个 skill：H5 课件生成器
    ├── SKILL.md           # Skill 元信息 + 使用说明
    ├── generate.py        # 确定性渲染脚本（仅标准库）
    ├── plan.example.json  # plan.json 示例契约
    └── README.md          # skill 详细说明
```

## 如何新增一个 skill

1. 在仓库根目录新建与 skill 同名的文件夹。
2. 放入 `SKILL.md`，frontmatter 至少包含：`name`、`display_name`、`description`、`version`、`author`、`agent_created: true`。
3. 放入脚本、提示词、示例等附属文件。
4. 写一份 `README.md` 说明用途、用法与最小示例。
5. 提交并推送：

```bash
git add <skill文件夹>
git commit -m "add skill: <skill名>"
git push
```

## 已收录 skill

| Skill | 说明 | 文档 |
|---|---|---|
| `h5-courseware` | 将 Markdown / 大纲编排为苹果磨砂玻璃风格单文件 H5 课件（支持键盘/点击/触摸翻页、移动端滚动、弹出式详情卡片） | [h5-courseware/README.md](h5-courseware/README.md) |

## 约定

- 优先仅使用标准库或必要依赖，避免引入重型第三方包。
- 每个 skill 自带示例，便于生成后直接验证。
- 提交信息统一以 `add skill:` / `update skill:` 开头。
