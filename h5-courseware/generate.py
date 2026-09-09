#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
H5 课件一键生成器
输入：Markdown 课件文档
输出：苹果磨砂玻璃风格 H5 课件（单文件合并版）

用法：
    python generate.py <md_path> [--brand Alchemy] [--out 输出目录] [--title 标题]

流程：解析 Markdown → 页面类型识别 → 生成 slides → 命名空间化合并 → 移动端适配
"""
import re
import sys
import json
import argparse
import copy
import html as html_lib
from pathlib import Path

# ============================================================
# 默认配置
# ============================================================

DEFAULT_BRAND = "Alchemy"
DEFAULT_THEME = ["#0071e3", "#5e5ce6", "#d63384", "#2da44e", "#d97706"]

# ============================================================
# 第一步：解析 Markdown
# ============================================================

def parse_markdown(md_text):
    """
    解析 Markdown，返回章节列表。
    每个 chapter = { 'title': 章节标题, 'sections': [ { 'h3': ..., 'body': ... } ] }
    """
    lines = md_text.split('\n')
    doc_title = ""
    chapters = []
    current_chapter = None
    current_section = None
    in_code_block = False

    for line in lines:
        # 代码块开关（跳过块内所有行，避免 # 标记误判）
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            if current_section is not None:
                current_section['lines'].append(line)
            continue

        if in_code_block:
            if current_section is not None:
                current_section['lines'].append(line)
            continue

        h1 = re.match(r'^# (.+)$', line)
        h2 = re.match(r'^## (.+)$', line)
        h3 = re.match(r'^### (.+)$', line)

        if h1 and not doc_title:
            doc_title = h1.group(1).strip()
            continue

        if h2:
            current_chapter = {
                'title': h2.group(1).strip(),
                'sections': []
            }
            chapters.append(current_chapter)
            current_section = None
            continue

        if h3 and current_chapter is not None:
            current_section = {
                'h3': h3.group(1).strip(),
                'lines': []
            }
            current_chapter['sections'].append(current_section)
            continue

        # 正文行归入当前 section（或章节 preamble）
        if current_chapter is not None:
            target = current_section if current_section else None
            if target:
                target['lines'].append(line)
            else:
                if 'preamble' not in current_chapter:
                    current_chapter['preamble'] = []
                current_chapter['preamble'].append(line)

    return doc_title, chapters


def clean_lines(lines):
    """清理空行、合并多余空行"""
    out = []
    blank = 0
    for l in lines:
        if l.strip() == '':
            blank += 1
            if blank <= 1:
                out.append('')
        else:
            blank = 0
            out.append(l)
    return out

# ============================================================
# 第二步：页面类型识别
# ============================================================

def detect_page_type(section_text, h3, is_first_in_chapter):
    """根据内容特征识别页面模板类型"""
    text = section_text

    if is_first_in_chapter and ('目标' in h3 or '你会拥有' in text or '学完' in text):
        return 'goal'
    if re.search(r'不是.{1,12}而是', text) or ('❌' in text and '✅' in text):
        return 'contrast'
    if '```' in text:
        return 'code'
    if re.search(r'L\s*[123].*阶段|成熟度|Level', text):
        return 'stair'
    if '打卡' in h3 or '作业' in h3 or '必交' in text:
        return 'checkin'
    if 'QA' in h3 or '常见问题' in h3 or '高频疑问' in text:
        return 'qa'
    if '任务' in h3 or '实操' in h3:
        return 'task'
    if re.search(r'\|\s*---', text):
        return 'table'
    # 列表项多的用清单
    bullets = len(re.findall(r'^\s*[-*] ', text, re.M))
    if bullets >= 5:
        return 'list'
    if re.search(r'→|流程|步骤', text):
        return 'flow'
    return 'content'

# ============================================================
# 第三步：HTML 生成组件
# ============================================================

def esc(s):
    return html_lib.escape(str(s), quote=True)

def inline_md(s):
    """行内 Markdown → HTML（加粗、行内代码和换行）"""
    s = esc(s).replace('\r\n', '\n').replace('\r', '\n')
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    return s.replace('\n', '<br>')

def safe_color(value, default='var(--p)'):
    value = str(value)
    if re.fullmatch(r'#[0-9a-fA-F]{6}', value) or re.fullmatch(r'var\(--[a-zA-Z0-9_-]+\)', value):
        return value
    return default

def detail_body_html(text):
    """detail.body 的 markdown-lite 渲染：段落、- 列表、**粗体**、`行内代码`、空行分段。"""
    blocks, bullets = [], []

    def flush_bullets():
        if bullets:
            blocks.append('<ul>' + ''.join(f'<li>{inline_md(b)}</li>' for b in bullets) + '</ul>')
            bullets.clear()

    for raw in str(text).replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = raw.strip()
        if not line:
            flush_bullets()
            continue
        m = re.match(r'^[-•]\s+(.+)$', line)
        if m:
            bullets.append(m.group(1))
        else:
            flush_bullets()
            blocks.append(f'<p>{inline_md(line)}</p>')
    flush_bullets()
    return ''.join(blocks) or '<p></p>'

def item_cls(item, base):
    """卡片类条目的 class：带 detail 时追加 detailable。"""
    return f'{base} detailable' if item.get('_detail_id') else base

def detail_attrs(item):
    """带 detail 的条目输出 data-detail / tabindex / role 属性。"""
    did = item.get('_detail_id')
    if not did:
        return ''
    return f'data-detail="{did}" tabindex="0" role="button"'

def svg_icon(path_d, color, size=26):
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.7" style="width:{size}px;height:{size}px">'
            f'<path d="{path_d}"/></svg>')

def blob_html():
    return ('<div class="bg-decor">'
            '<div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div>'
            '</div>')

def eyebrow(t):
    return f'<div class="eyebrow-chip">{esc(t)}</div>'

def page_title(t):
    return f'<h2 class="title">{esc(t)}</h2>'

# ---------- 页面模板 ----------

def tpl_goal(chapter, section, idx):
    """目标页：3 列卡片。从内容中提取 3 个要点（标题/描述）"""
    items = re.findall(r'^\s*[-*]\s+\*\*(.+?)\*\*[：:]\s*(.+)$', section['body_md'], re.M)
    cards = ''
    colors = ['var(--p)', 'var(--indigo)', 'var(--green)']
    for i, (t, d) in enumerate(items[:3]):
        c = colors[i % 3]
        cards += f'''
        <div class="goal-card g{i+1}">
          <div class="goal-icon">{svg_icon("M12 2l3 6 6 1-4.5 4.3L17.5 20 12 17l-5.5 3 1-6.7L3 9l6-1 3-6z", c)}</div>
          <div class="goal-title">{esc(t)}</div>
          <div class="goal-desc">{inline_md(d)}</div>
        </div>'''
    body = f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center;">
      {eyebrow("今天的目标")}
      {page_title("下课前，你会拥有什么")}
      <div class="goal-cards">{cards}</div>
    </div>'''
    return body

def tpl_contrast(chapter, section, idx):
    """对比页：❌ vs ✅ 行"""
    rows = re.findall(r'^\s*[-*]\s+(.+)$', section['body_md'], re.M)
    items = ''
    for r in rows:
        m = re.match(r'(.+?)→(.+)', r)
        if m:
            items += f'''
        <div class="diff-row">
          <div class="diff-from"><span class="label">不是</span>{inline_md(m.group(1).strip())}</div>
          <div class="diff-arrow">→</div>
          <div class="diff-to"><span class="label">而是</span>{inline_md(m.group(2).strip())}</div>
        </div>'''
    body = f'''
    <div class="content-wrap">
      {eyebrow("关键认知")}
      {page_title("这门课不一样")}
      <div class="diff-list">{items}</div>
    </div>'''
    return body

def tpl_code(chapter, section, idx):
    """代码页：macOS 窗口"""
    m = re.search(r'```(\w*)\n(.*?)```', section['body_md'], re.DOTALL)
    if not m:
        return tpl_content(chapter, section, idx)
    fname = m.group(1) or 'code.txt'
    code = esc(m.group(2).rstrip())
    # 简单语法着色：注释
    code = re.sub(r'(#.*|//.*)$', r'<span class="cm">\1</span>', code, flags=re.M)
    before = section['body_md'][:m.start()].strip()
    after = section['body_md'][m.end():].strip()
    lead = f'<p class="body" style="margin-bottom:20px;">{inline_md(before)}</p>' if before else ''
    body = f'''
    <div class="content-wrap">
      {eyebrow("核心结构")}
      {page_title(esc(section['h3']))}
      {lead}
      <div class="code-window">
        <div class="code-header">
          <span class="cdot r"></span><span class="cdot y"></span><span class="cdot g"></span>
          <span class="fname">{esc(fname)}</span>
        </div>
        <div class="code-body">{code}</div>
      </div>
    </div>'''
    return body

def tpl_stair(chapter, section, idx):
    """阶梯页：L1→L3 递进卡片"""
    items = re.findall(r'^\s*[-*]\s+\*\*(L\d[^*]*)\*\*[：:]?\s*(.*)$', section['body_md'], re.M)
    cards = ''
    cls = ['tm1', 'tm2', 'tm3']
    for i, (t, d) in enumerate(items[:3]):
        k = cls[i]
        cards += f'''
        <div class="team-card {k}">
          <div class="tm-lv">{esc(t.split('·')[0].strip())}</div>
          <div class="tm-title">{esc(t.split('·')[-1].strip())}</div>
          <div class="tm-desc">{inline_md(d)}</div>
        </div>'''
    body = f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center;">
      {eyebrow("进阶路径")}
      {page_title(esc(section['h3']))}
      <div class="team-flow" style="margin-top:44px;">{cards}</div>
    </div>'''
    return body

def tpl_task(chapter, section, idx):
    """任务页：3 列任务卡"""
    # 匹配 **标题**（时长） + 后面的列表
    blocks = re.split(r'\n(?=\s*[-*]\s+\*\*)', section['body_md'].strip())
    cards = ''
    for i, b in enumerate(blocks[:3]):
        m = re.match(r'\s*[-*]\s+\*\*(.+?)\*\*[（(](\d+) 分钟[)）]', b)
        if not m:
            continue
        title, minutes = m.group(1), m.group(2)
        steps = re.findall(r'^\s+[-*]\s+(.+)$', b, re.M)
        lis = ''.join(f'<div class="li"><span class="bullet">·</span><span>{inline_md(s)}</span></div>' for s in steps)
        dm = re.search(r'[>｜|]\s*\*?\*?交付物\*?\*?[：:]?\s*(.+)', b)
        deliver = f'<div class="deliver"><strong>交付物</strong>：{inline_md(dm.group(1))}</div>' if dm else ''
        cards += f'''
        <div class="task-card">
          <span class="time-badge">{minutes} 分钟</span>
          <div class="tnum">0{i+1}</div>
          <div class="ttitle">{esc(title)}</div>
          <div class="tstep">{lis}</div>
          {deliver}
        </div>'''
    body = f'''
    <div class="content-wrap">
      {eyebrow("动手时间")}
      {page_title("要完成的实操任务")}
      <div class="task-grid">{cards}</div>
    </div>'''
    return body

def tpl_qa(chapter, section, idx):
    """QA 页：Q/A 卡片"""
    qa_items = re.findall(r'^\s*[-*]\s+\*\*([^*]+)[？?]\*\*\s*\n?\s*([^\n*]+)', section['body_md'], re.M)
    cards = ''
    for q, a in qa_items[:4]:
        cards += f'''
        <div class="qa-item">
          <div class="qa-q"><span class="qmark">Q</span><span>{esc(q)}？</span></div>
          <div class="qa-a">{inline_md(a.strip())}</div>
        </div>'''
    body = f'''
    <div class="content-wrap">
      {eyebrow("答疑")}
      {page_title("高频疑问")}
      <div class="qa-grid">{cards}</div>
    </div>'''
    return body

def tpl_checkin(chapter, section, idx):
    """打卡页：必交/加分双栏 + 预告"""
    must_items = re.findall(r'(?:必交|REQUIRED)[：:]?\s*\n((?:\s*[-*].+\n?)+)', section['body_md'])
    bonus_items = re.findall(r'(?:加分|BONUS)[：:]?\s*\n((?:\s*[-*].+\n?)+)', section['body_md'])
    def lis(block):
        items = re.findall(r'^\s*[-*]\s+(.+)$', block or '', re.M)
        return ''.join(f'<div class="cb-item"><span class="box"></span><span>{inline_md(i)}</span></div>' for i in items)
    must_html = lis(must_items[0] if must_items else '')
    bonus_html = lis(bonus_items[0] if bonus_items else '')
    # 找预告
    nxt = re.search(r'预告[：:]\s*(.+)', section['body_md'])
    next_html = ''
    if nxt:
        next_html = f'''
      <div class="next-bar">
        <div class="nb-text"><strong>{inline_md(nxt.group(1))}</strong></div>
        <span class="nb-badge">记得打卡 →</span>
      </div>'''
    body = f'''
    <div class="content-wrap">
      {eyebrow("今日打卡")}
      {page_title("下课前把它交了")}
      <div class="check-wrap">
        <div class="check-box must">
          <div class="cb-head"><span class="cb-icon">✓</span>
            <div><div class="cb-title">必交</div><div class="cb-sub">REQUIRED</div></div>
          </div>
          {must_html}
        </div>
        <div class="check-box bonus">
          <div class="cb-head"><span class="cb-icon">★</span>
            <div><div class="cb-title">加分项</div><div class="cb-sub">BONUS</div></div>
          </div>
          {bonus_html}
        </div>
      </div>
      {next_html}
    </div>'''
    return body

def tpl_list(chapter, section, idx):
    """清单页：tag 云"""
    items = re.findall(r'^\s*[-*]\s+(.+)$', section['body_md'], re.M)
    tags = ''.join(f'<span class="tag">{esc(i)}</span>' for i in items[:24])
    body = f'''
    <div class="content-wrap">
      {eyebrow("清单")}
      {page_title(esc(section['h3']))}
      <div class="tag-list" style="display:flex; flex-wrap:wrap; gap:10px; margin-top:36px;">
        {tags}
      </div>
    </div>'''
    return body

def tpl_flow(chapter, section, idx):
    """流程页：节点 + 箭头（竖排以适配移动端）"""
    items = re.findall(r'^\s*[-*]\s+(.+)$', section['body_md'], re.M)
    nodes = ''
    for i, it in enumerate(items[:5]):
        m = re.match(r'\*\*(.+?)\*\*[：:]?\s*(.*)', it)
        name = m.group(1) if m else it
        desc = m.group(2) if m else ''
        arrow = '<span class="pipe-arrow">→</span>' if i > 0 else ''
        nodes += f'''{arrow}
        <div class="pipe-node" style="min-width:0;">
          <div class="pipe-name" style="font-size:17px; font-weight:600;">{esc(name)}</div>
          {f'<div class="pipe-out">{inline_md(desc)}</div>' if desc else ''}
        </div>'''
    body = f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center;">
      {eyebrow("流程")}
      {page_title(esc(section['h3']))}
      <div class="pipe-flow" style="flex-direction:column; align-items:stretch; margin-top:40px; max-width:560px;">{nodes}</div>
    </div>'''
    return body

def tpl_table(chapter, section, idx):
    """表格页"""
    lines = [l for l in section['body_md'].split('\n') if l.strip().startswith('|')]
    rows = [l for l in lines if not re.match(r'^\|[\s\-|]+\|$', l)]
    head = [c.strip() for c in rows[0].strip('|').split('|')] if rows else []
    body_rows = rows[1:] if rows else []
    trs = ''
    for r in body_rows:
        cells = [c.strip() for c in r.strip('|').split('|')]
        tds = ''.join(f'<td style="padding:14px 16px; border-bottom:1px solid rgba(0,0,0,0.06); font-size:14.5px; color:var(--ink-2);">{inline_md(c)}</td>' for c in cells)
        trs += f'<tr>{tds}</tr>'
    ths = ''.join(f'<th style="padding:13px 16px; text-align:left; font-size:13px; font-weight:700; letter-spacing:0.06em; color:var(--ink-3); border-bottom:2px solid rgba(0,0,0,0.08);">{esc(h)}</th>' for h in head)
    body = f'''
    <div class="content-wrap">
      {eyebrow("对比")}
      {page_title(esc(section['h3']))}
      <div style="margin-top:34px; border-radius:18px; overflow:hidden; border:1px solid rgba(0,0,0,0.08); background:rgba(255,255,255,0.7);">
        <table style="width:100%; border-collapse:collapse;">
          <thead><tr>{ths}</tr></thead>
          <tbody>{trs}</tbody>
        </table>
      </div>
    </div>'''
    return body

def tpl_content(chapter, section, idx):
    """通用内容页：要点卡片（2 列）"""
    items = re.findall(r'^\s*[-*]\s+(.+)$', section['body_md'], re.M)
    cards = ''
    for it in items[:6]:
        m = re.match(r'\*\*(.+?)\*\*[：:]?\s*(.*)', it)
        t = m.group(1) if m else it[:20]
        d = m.group(2) if m else ''
        cards += f'''
        <div class="glass-card" style="padding:20px 22px;">
          <div style="font-size:17px; font-weight:600; margin-bottom:6px;">{esc(t)}</div>
          {f'<div style="font-size:14px; color:var(--ink-3); line-height:1.55;">{inline_md(d)}</div>' if d else ''}
        </div>'''
    grid = f'<div style="display:grid; grid-template-columns:repeat(2,1fr); gap:16px; margin-top:36px;">{cards}</div>' if cards else ''
    para = ''
    if not items:
        para = ''.join(f'<p class="body" style="margin-bottom:14px;">{inline_md(l)}</p>'
                       for l in section['body_md'].split('\n') if l.strip() and not l.strip().startswith('#'))
    body = f'''
    <div class="content-wrap">
      {eyebrow("要点")}
      {page_title(esc(section['h3']))}
      {grid}{para}
    </div>'''
    return body

TEMPLATES = {
    'goal': tpl_goal, 'contrast': tpl_contrast, 'code': tpl_code,
    'stair': tpl_stair, 'task': tpl_task, 'qa': tpl_qa,
    'checkin': tpl_checkin, 'list': tpl_list, 'flow': tpl_flow,
    'table': tpl_table, 'content': tpl_content,
}

# ============================================================
# 第三步半：Plan 渲染层（AI 编排 → JSON → 确定性渲染）
# ============================================================

def p_eyebrow(t):
    return f'<div class="eyebrow-chip">{esc(t)}</div>' if t else ''

def p_title(t):
    return f'<h2 class="title">{inline_md(t)}</h2>' if t else ''

def p_subtitle(t):
    return f'<p class="body" style="margin-top:14px; color:var(--ink-3); text-align:center;">{inline_md(t)}</p>' if t else ''

def r_cover(page, ch_idx):
    c = page
    inner = f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center; text-align:center;">
      {f'<div class="cover-badge">{esc(c.get("badge", ""))}</div>' if c.get('badge') else ''}
      {f'<div class="eyebrow-chip" style="margin-bottom:26px;">{esc(c["eyebrow"])}</div>' if c.get('eyebrow') else ''}
      <h1 style="font-weight:700; letter-spacing:-0.035em; line-height:1.05; margin-bottom:18px; text-align:center;">
        {f'<span class="cover-small">{esc(c["title_small"])}</span>' if c.get('title_small') else ''}
        <span class="gradient-text" style="font-size:76px; display:block;">{esc(c["title"])}</span>
        {f'<span class="cover-big" style="display:block; margin-top:6px;">{esc(c["title_big"])}</span>' if c.get('title_big') else ''}
      </h1>
      {f'<p style="font-size:23px; color:var(--ink-2); font-weight:400;">{inline_md(c["subtitle"])}</p>' if c.get('subtitle') else ''}
      {f'<div class="cover-meta">{"".join(f"<div class=meta-pill>{esc(m)}</div>" for m in c["meta"])}</div>' if c.get('meta') else ''}
    </div>'''
    return inner

def r_promise(page, ch_idx):
    c = page
    return f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center;">
      {p_eyebrow(c.get('eyebrow'))}
      <div class="glass-card promise-card">
        <p class="lead">{inline_md(c.get('lead', ''))}</p>
        <p class="from">"{inline_md(c.get('from', ''))}"</p>
        <div class="arrow">↓</div>
        <p class="to"><span class="gradient-text">{inline_md(c.get('to', ''))}</span></p>
      </div>
    </div>'''

def r_cards(page, ch_idx):
    cols = page.get('columns', 3)
    cards = ''
    for c in page.get('cards', []):
        head = ''
        if c.get('num'):
            col = c.get('color', 'var(--p)')
            head += f'<div class="pnum" style="color:{col}; opacity:0.9;">{esc(c["num"])}</div>' if c.get('color') else f'<div class="pnum">{esc(c["num"])}</div>'
        if c.get('tag'):
            head += f'<div class="ptag">{esc(c["tag"])}</div>'
        if c.get('label'):
            head += f'<div class="plabel">{esc(c["label"])}</div>'
        cards += f'''
        <div class="{item_cls(c, 'glass-card pcard')}" {detail_attrs(c)}>
          {head}
          <div class="ptitle">{inline_md(c.get('title', ''))}</div>
          <div class="pdesc">{inline_md(c.get('desc', ''))}</div>
        </div>'''
    return f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center;">
      {p_eyebrow(page.get('eyebrow'))}
      {p_title(page.get('title', ''))}
      {p_subtitle(page.get('subtitle'))}
      <div class="card-grid" data-columns="{cols}" style="width:100%; max-width:{1180 if cols >= 3 else 1080}px;">{cards}</div>
    </div>'''

def r_rows(page, ch_idx):
    rows = ''
    for r in page.get('rows', []):
        rows += f'''
        <div class="{item_cls(r, 'glass-card day-row')}" {detail_attrs(r)}>
          <span class="day-pill">{esc(r.get('pill', ''))}</span>
          <span class="date">{esc(r.get('date', ''))}</span>
          <span class="theme">{esc(r.get('theme', ''))}</span>
          <span class="output">{inline_md(r.get('output', ''))}</span>
        </div>'''
    return f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center;">
      {p_eyebrow(page.get('eyebrow'))}
      {p_title(page.get('title', ''))}
      {p_subtitle(page.get('subtitle'))}
      <div class="rows-list">{rows}</div>
    </div>'''

def r_flow(page, ch_idx):
    nodes = ''
    items = page.get('nodes', [])
    for i, n in enumerate(items):
        arrow = '<div class="logic-arrow">→</div>' if i > 0 else ''
        nodes += f'''{arrow}
        <div class="{item_cls(n, 'glass-card logic-card')}" {detail_attrs(n)}>
          <div class="icon-ring">{esc(n.get('label', str(i+1)))}</div>
          <div class="keyword">{esc(n.get('keyword', ''))}</div>
          <div class="desc">{inline_md(n.get('desc', ''))}</div>
        </div>'''
    return f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center;">
      {p_eyebrow(page.get('eyebrow'))}
      {p_title(page.get('title', ''))}
      {p_subtitle(page.get('subtitle'))}
      <div class="logic-flow" style="width:100%; max-width:1180px;">{nodes}</div>
    </div>'''

def r_contrast(page, ch_idx):
    rows = ''
    for r in page.get('rows', []):
        rows += f'''
        <div class="glass-card diff-row">
          <div class="diff-from"><span class="label">不是</span>{inline_md(r.get('from', ''))}</div>
          <div class="diff-arrow">→</div>
          <div class="diff-to"><span class="label">而是</span>{inline_md(r.get('to', ''))}</div>
        </div>'''
    return f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center;">
      {p_eyebrow(page.get('eyebrow'))}
      {p_title(page.get('title', ''))}
      <div class="diff-list" style="width:100%; max-width:1000px;">{rows}</div>
    </div>'''

def r_price(page, ch_idx):
    cards = ''
    items = page.get('steps', [])
    for i, s in enumerate(items):
        arrow = '<div class="price-arrow">→</div>' if i < len(items) - 1 else '<div class="price-arrow">=</div>'
        op = '<div class="price-arrow">-</div>' if s.get('style') == 'minus' else arrow
        cards += f'''{op}
        <div class="{item_cls(s, 'glass-card price-card')} {s.get('style', '')}" {detail_attrs(s)}>
          <div class="plabel">{esc(s.get('label', ''))}</div>
          <div class="pvalue"><span class="cur">¥</span>{esc(s.get('value', ''))}</div>
          <div class="pnote">{inline_md(s.get('note', ''))}</div>
        </div>'''
    notice = ''
    if page.get('notice'):
        notice = f'''
      <div class="notice-bar"><div class="check">✓</div><div>{inline_md(page['notice'])}</div></div>'''
    return f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center;">
      {p_eyebrow(page.get('eyebrow'))}
      {p_title(page.get('title', ''))}
      <div class="price-flow" style="width:100%; max-width:1100px;">{cards}</div>
      {notice}
    </div>'''

def r_steps(page, ch_idx):
    steps = ''
    for i, s in enumerate(page.get('steps', [])):
        steps += f'''
        <div class="{item_cls(s, 'glass-card step-card')}" {detail_attrs(s)}>
          <div class="step-num">{i+1}</div>
          <div class="step-title">{esc(s.get('title', ''))}</div>
          <div class="step-desc">{inline_md(s.get('desc', ''))}</div>
        </div>'''
        if i < len(page.get('steps', [])) - 1:
            steps += '<div class="logic-arrow">→</div>'
    return f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center;">
      {p_eyebrow(page.get('eyebrow'))}
      {p_title(page.get('title', ''))}
      <div class="signup-flow" style="width:100%; max-width:1140px;">{steps}</div>
    </div>'''

def r_cta(page, ch_idx):
    return f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center;">
      <div class="cta-card">
        {f'<div class="cta-eyebrow">{esc(page["eyebrow"])}</div>' if page.get('eyebrow') else ''}
        <h1 class="cta-title"><span class="gradient-text">{inline_md(page.get('title', ''))}</span></h1>
        {f'<p class="cta-subtitle">{inline_md(page["subtitle"])}</p>' if page.get('subtitle') else ''}
        {f'<div class="cta-slogan">{inline_md(page["slogan"])}</div>' if page.get('slogan') else ''}
      </div>
    </div>'''

def r_split(page, ch_idx):
    def panel(side, d):
        tone = d.get('tone', 'right' if side == 'right' else 'wrong')
        mark = '✕' if tone == 'wrong' else '✓'
        items = ''.join(f'<div class="item">{inline_md(i)}</div>' for i in d.get('items', []))
        formula = f'<div class="formula">{esc(d["formula"])}</div>' if d.get('formula') else ''
        return f'''
        <div class="panel {tone}">
          <div class="panel-head"><span class="mark">{mark}</span><span class="ptitle">{esc(d.get('head', ''))}</span></div>
          {items}
          {formula}
        </div>'''
    return f'''
    <div class="content-wrap">
      {p_eyebrow(page.get('eyebrow'))}
      {p_title(page.get('title', ''))}
      <div class="why-split">
        {panel('left', page.get('left', {}))}
        {panel('right', page.get('right', {}))}
      </div>
    </div>'''

def r_columns3(page, ch_idx):
    cols = ''
    for c in page.get('columns_data', []):
        cols += f'''
        <div class="{item_cls(c, 'glass-card layer-card')}" {detail_attrs(c)}>
          <span class="layer-tag">{esc(c.get('tag', ''))}</span>
          <div class="layer-file">{esc(c.get('file', ''))}</div>
          <div class="layer-cn">{esc(c.get('cn', ''))}</div>
          <div class="layer-def">{inline_md(c.get('def', ''))}</div>
          <div class="layer-q"><span class="q">Q</span><span>{esc(c.get('q', ''))}</span></div>
        </div>'''
    return f'''
    <div class="content-wrap">
      {p_eyebrow(page.get('eyebrow'))}
      {p_title(page.get('title', ''))}
      <div class="layer-flow">{cols}</div>
    </div>'''

def r_qa(page, ch_idx):
    cards = ''
    for qa in page.get('qa', [])[:6]:
        cards += f'''
        <div class="{item_cls(qa, 'glass-card qa-item')}" {detail_attrs(qa)}>
          <div class="qa-q"><span class="qmark">Q</span><span>{esc(qa.get('q', ''))}</span></div>
          <div class="qa-a">{inline_md(qa.get('a', ''))}</div>
        </div>'''
    return f'''
    <div class="content-wrap">
      {p_eyebrow(page.get('eyebrow'))}
      {p_title(page.get('title', ''))}
      <div class="qa-grid">{cards}</div>
    </div>'''

def r_checkin(page, ch_idx):
    def lis(items, box_cls=''):
        return ''.join(f'<div class="cb-item"><span class="box" style="{box_cls}"></span><span>{inline_md(i)}</span></div>' for i in items)
    must = lis(page.get('must', []), 'border-color:rgba(var(--p-rgb),0.4);')
    bonus = lis(page.get('bonus', []), 'border-color:rgba(95,204,124,0.45);')
    nxt = page.get('next', {})
    next_html = ''
    if nxt:
        next_html = f'''
      <div class="next-bar">
        <div class="nb-text"><strong>{inline_md(nxt.get('title', ''))}</strong>
        <div class="nb-time" style="font-size:14px; color:var(--ink-3); margin-top:4px;">{esc(nxt.get('time', ''))}</div></div>
        <span class="nb-badge">记得打卡 →</span>
      </div>'''
    return f'''
    <div class="content-wrap">
      {p_eyebrow(page.get('eyebrow'))}
      {p_title(page.get('title', ''))}
      <div class="check-wrap">
        <div class="glass-card check-box must" style="border-radius:24px;">
          <div class="cb-head"><span class="cb-icon">✓</span>
            <div><div class="cb-title">必交</div><div class="cb-sub">REQUIRED</div></div></div>
          {must}
        </div>
        <div class="glass-card check-box bonus" style="border-radius:24px;">
          <div class="cb-head"><span class="cb-icon">★</span>
            <div><div class="cb-title">加分项</div><div class="cb-sub">BONUS</div></div></div>
          {bonus}
        </div>
      </div>
      {next_html}
    </div>'''

def r_chips(page, ch_idx):
    """胶囊词条页：每个胶囊点开弹出详情卡片（术语深读、扩展说明等）。"""
    chips_html = ''
    for c in page.get('chips', []):
        sub = f'<span class="chip-sub">{esc(c["hint"])}</span>' if c.get('hint') else ''
        chips_html += f'''
        <div class="{item_cls(c, 'deep-chip glass-card')}" {detail_attrs(c)}>{esc(c.get('label', ''))}{sub}</div>'''
    note = f'<p class="chips-note">{inline_md(page["note"])}</p>' if page.get('note') else ''
    return f'''
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center;">
      {p_eyebrow(page.get('eyebrow'))}
      {p_title(page.get('title', ''))}
      {p_subtitle(page.get('subtitle'))}
      <div class="chips-wrap">{chips_html}</div>
      {note}
    </div>'''

PLAN_RENDERERS = {
    'cover': r_cover, 'promise': r_promise, 'cards': r_cards, 'rows': r_rows,
    'flow': r_flow, 'contrast': r_contrast, 'price': r_price, 'steps': r_steps,
    'cta': r_cta, 'split': r_split, 'columns3': r_columns3,
    'qa': r_qa, 'checkin': r_checkin, 'chips': r_chips,
}

def _walk_details(node, where, errors):
    """递归校验任意层级的 detail 字段，收集错误信息。"""
    if isinstance(node, dict):
        detail = node.get('detail')
        if detail is not None:
            if not isinstance(detail, dict):
                errors.append(f'{where}.detail 必须是 object')
            elif not isinstance(detail.get('body'), str) or not detail.get('body', '').strip():
                errors.append(f'{where}.detail.body 必须是非空字符串')
        for key, value in node.items():
            if key == 'detail':
                continue
            _walk_details(value, f'{where}.{key}', errors)
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            _walk_details(value, f'{where}[{idx}]', errors)


def validate_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError('Plan 根对象必须是 JSON object')
    chapters = plan.get('chapters')
    if not isinstance(chapters, list) or not chapters:
        raise ValueError('Plan chapters 必须是非空数组')
    colors = plan.get('theme_colors')
    if not isinstance(colors, list) or not colors:
        raise ValueError('Plan theme_colors 必须是非空数组')
    for i, color in enumerate(colors):
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValueError(f'Plan theme_colors[{i}] 必须是 6 位十六进制颜色')
    for i, chapter in enumerate(chapters):
        if not isinstance(chapter, dict) or not isinstance(chapter.get('title'), str) or not chapter['title'].strip():
            raise ValueError(f'Plan chapters[{i}].title 必须是非空字符串')
        cover = chapter.get('cover')
        if not isinstance(cover, dict) or not isinstance(cover.get('title'), str) or not cover['title'].strip():
            raise ValueError(f'Plan chapters[{i}].cover.title 必须是非空字符串')
        pages = chapter.get('pages')
        if not isinstance(pages, list):
            raise ValueError(f'Plan chapters[{i}].pages 必须是数组')
        for j, page in enumerate(pages):
            if not isinstance(page, dict) or page.get('type') not in PLAN_RENDERERS:
                raise ValueError(f'Plan chapters[{i}].pages[{j}].type 必须属于: {", ".join(PLAN_RENDERERS)}')
            errors = []
            _walk_details(page, f'Plan chapters[{i}].pages[{j}]', errors)
            if page.get('type') == 'chips':
                chips = page.get('chips')
                if not isinstance(chips, list) or not chips:
                    raise ValueError(f'Plan chapters[{i}].pages[{j}].chips 必须是非空数组')
                for k, chip in enumerate(chips):
                    if not isinstance(chip, dict) or not str(chip.get('label', '')).strip():
                        raise ValueError(f'Plan chapters[{i}].pages[{j}].chips[{k}].label 必须是非空字符串')
                    if not isinstance(chip.get('detail'), dict):
                        raise ValueError(f'Plan chapters[{i}].pages[{j}].chips[{k}].detail 必须是 object（chips 页每个胶囊都应有详情）')
            if errors:
                raise ValueError('; '.join(errors))


def collect_details(node, out):
    """递归扫描页面树：凡带 detail 的条目分配 _detail_id 并收集详情。"""
    if isinstance(node, dict):
        if isinstance(node.get('detail'), dict):
            did = f'd{len(out)}'
            node['_detail_id'] = did
            out[did] = node['detail']
        for value in node.values():
            if value is not node.get('detail'):
                collect_details(value, out)
    elif isinstance(node, list):
        for value in node:
            collect_details(value, out)


def render_plan(plan):
    """从 plan JSON 渲染完整 HTML。AI 编排 → 此函数确定性执行。"""
    validate_plan(plan)
    brand = plan.get('brand', DEFAULT_BRAND)
    title = plan.get('title', 'H5 课件')
    theme_colors = plan.get('theme_colors', DEFAULT_THEME)

    all_slides = []
    chapter_starts = []
    theme_css = ''
    details = {}

    for ch_idx, ch in enumerate(plan.get('chapters', [])):
        color = theme_colors[ch_idx % len(theme_colors)]
        chapter_starts.append(len(all_slides))
        theme_css += (f'\n.slide[data-chapter="{ch_idx}"] {{ '
                      f'--p: {color}; --p2: #8e8cff; --p-rgb: {rgb(color)}; }}')

        # 封面
        cover = ch.get('cover', {})
        all_slides.append(f'''
  <section class="slide slide-cover" data-chapter="{ch_idx}">
    {blob_html()}
    {r_cover(cover, ch_idx)}
  </section>''')

        # 内容页
        for i, page in enumerate(ch.get('pages', [])):
            ptype = page.get('type', 'cards')
            renderer = PLAN_RENDERERS.get(ptype, r_cards)
            collect_details(page, details)
            inner = renderer(page, ch_idx)
            all_slides.append(f'''
  <section class="slide slide-{ptype}" data-chapter="{ch_idx}">
    {blob_html()}
    <div class="page-tag">{esc(ch["title"])} · {i+1:02d}</div>
    {inner}
  </section>''')

    detail_data = {
        did: {
            'title': str(d.get('title', '') or ''),
            'badge': str(d.get('badge', '') or ''),
            'source': str(d.get('source', '') or ''),
            'html': detail_body_html(d.get('body', '')),
        }
        for did, d in details.items()
    }
    return merge(all_slides, chapter_starts, brand, title, theme_colors, detail_data)

# ============================================================
# 第四步：CSS 基础（全局样式，从手工版提炼）
# ============================================================

BASE_CSS = """
:root {
  --bg: #ffffff;
  --ink: #1d1d1f; --ink-2: #424245; --ink-3: #6e6e73; --ink-4: #86868b;
  --p: #0071e3; --p2: #5e5ce6; --p-rgb: 0,113,227;
  --indigo: #5e5ce6; --green: #5fcc7c; --pink: #ff8db8;
  --glass: rgba(255,255,255,0.7);
  --shadow-1: 0 8px 32px rgba(0,0,0,0.06);
  --shadow-2: 0 20px 60px rgba(0,0,0,0.08);
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}
* { margin:0; padding:0; box-sizing:border-box; }
html, body { width:100%; height:100%; overflow:hidden; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Helvetica Neue", "Inter", sans-serif;
  color: var(--ink); background: var(--bg);
  -webkit-font-smoothing: antialiased;
}
.deck {
  width:100vw; height:100vh; position:relative; overflow:hidden;
  background: radial-gradient(ellipse at top left, #f5f7fa 0%, transparent 50%),
              radial-gradient(ellipse at bottom right, #fafbfc 0%, transparent 50%), #ffffff;
}
.slide {
  position:absolute; inset:0;
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  padding:70px 90px;
  opacity:0; visibility:hidden; transform:translateY(8px) scale(0.99);
  transition:opacity .7s cubic-bezier(.4,0,.2,1), transform .7s cubic-bezier(.4,0,.2,1);
}
.slide.active { opacity:1; visibility:visible; transform:translateY(0) scale(1); }
.bg-decor { position:absolute; inset:0; overflow:hidden; z-index:0; pointer-events:none; }
.blob { position:absolute; border-radius:50%; filter:blur(90px); opacity:0.45; }
.blob.b1 { width:520px; height:520px; background:radial-gradient(circle, rgba(var(--p-rgb),0.16), transparent 70%); top:-100px; left:-100px; }
.blob.b2 { width:600px; height:600px; background:radial-gradient(circle, rgba(94,92,230,0.12), transparent 70%); bottom:-200px; right:-150px; }
.blob.b3 { width:400px; height:400px; background:radial-gradient(circle, rgba(255,141,184,0.12), transparent 70%); top:30%; right:20%; opacity:0.35; }
.title { font-size:56px; font-weight:600; letter-spacing:-0.02em; line-height:1.12; }
.body { font-size:19px; line-height:1.55; color:var(--ink-2); }
.small { font-size:15px; color:var(--ink-3); }
.brand-tag { position:absolute; top:30px; left:40px; font-size:12px; color:var(--ink-4); letter-spacing:0.16em; font-weight:600; z-index:5; }
.brand-tag span { color:var(--p); }
.page-tag { position:absolute; top:30px; right:40px; font-size:12px; color:var(--ink-4); letter-spacing:0.14em; font-weight:500; z-index:5; }
.day-nav {
  position:absolute; top:26px; left:50%; transform:translateX(-50%);
  display:flex; gap:6px; padding:6px 8px;
  background:rgba(255,255,255,0.7);
  backdrop-filter:blur(24px) saturate(180%); -webkit-backdrop-filter:blur(24px) saturate(180%);
  border:1px solid rgba(255,255,255,0.6); border-radius:100px; z-index:5;
  box-shadow:var(--shadow-1);
}
.day-nav .dp { padding:6px 14px; border-radius:100px; font-size:12px; font-weight:600; letter-spacing:0.06em; color:var(--ink-4); }
.day-nav .dp.active { background:linear-gradient(135deg,var(--p),var(--p2)); color:#fff; }
.day-nav .dp.done { color:var(--ink-3); background:rgba(0,0,0,0.04); }
.progress {
  position:fixed; bottom:26px; left:50%; transform:translateX(-50%);
  display:flex; gap:6px; padding:9px 15px;
  background:rgba(255,255,255,0.75);
  backdrop-filter:blur(30px) saturate(180%); -webkit-backdrop-filter:blur(30px) saturate(180%);
  border-radius:100px; z-index:100;
  box-shadow:0 8px 32px rgba(0,0,0,0.08); border:1px solid rgba(255,255,255,0.6);
}
.progress .dot { width:7px; height:7px; border-radius:50%; background:rgba(0,0,0,0.18); cursor:pointer; transition:all .35s; }
.progress .dot.active { background:var(--p); width:24px; border-radius:4px; }
.eyebrow-chip {
  display:inline-block; padding:7px 16px; border-radius:100px;
  background:rgba(var(--p-rgb),0.08); color:var(--p);
  font-size:13px; font-weight:600; letter-spacing:0.06em; margin-bottom:22px;
}
.content-wrap { position:relative; z-index:2; width:100%; max-width:1220px; }
.glass-card {
  background:var(--glass);
  backdrop-filter:blur(30px) saturate(180%); -webkit-backdrop-filter:blur(30px) saturate(180%);
  border:1px solid rgba(255,255,255,0.6); border-radius:24px; box-shadow:var(--shadow-1);
}
.code-window {
  background:rgba(255,255,255,0.62);
  backdrop-filter:blur(30px) saturate(180%); -webkit-backdrop-filter:blur(30px) saturate(180%);
  border:1px solid rgba(255,255,255,0.7); border-radius:18px; overflow:hidden; box-shadow:var(--shadow-2);
}
.code-header { display:flex; align-items:center; gap:8px; padding:13px 18px; background:rgba(0,0,0,0.035); border-bottom:1px solid rgba(0,0,0,0.055); }
.code-header .cdot { width:12px; height:12px; border-radius:50%; }
.code-header .cdot.r { background:#ff5f57; }
.code-header .cdot.y { background:#febc2e; }
.code-header .cdot.g { background:#28c840; }
.code-header .fname { margin:0 auto; font-family:var(--mono); font-size:13px; color:var(--ink-3); font-weight:500; }
.code-body { padding:22px 26px; font-family:var(--mono); font-size:14.5px; line-height:1.85; color:var(--ink-2); white-space:pre; overflow-x:auto; }
.code-body .cm { color:var(--ink-4); }
.gradient-text {
  background:linear-gradient(135deg, var(--p) 0%, var(--p2) 50%, #ff8db8 100%);
  -webkit-background-clip:text; background-clip:text;
  -webkit-text-fill-color:transparent; color:transparent;
}
.goal-cards { display:grid; grid-template-columns:repeat(3,1fr); gap:20px; margin-top:44px; }
.goal-card { padding:32px 28px; text-align:center; }
.goal-icon { width:60px; height:60px; border-radius:18px; margin:0 auto 18px; display:flex; align-items:center; justify-content:center; background:rgba(var(--p-rgb),0.1); }
.goal-title { font-size:21px; font-weight:600; margin-bottom:10px; }
.goal-desc { font-size:14px; color:var(--ink-3); line-height:1.55; }
.diff-list { display:flex; flex-direction:column; gap:18px; margin-top:44px; max-width:1000px; }
.diff-row {
  display:grid; grid-template-columns:1fr 80px 1fr; align-items:center; gap:24px; padding:24px 32px;
}
.diff-from, .diff-to { font-size:21px; }
.diff-from { color:var(--ink-3); text-decoration:line-through; text-decoration-color:rgba(0,0,0,0.2); }
.diff-to { font-weight:600; }
.diff-from .label { display:block; font-size:11px; letter-spacing:0.14em; color:#c83a3a; margin-bottom:6px; font-weight:600; }
.diff-to .label { display:block; font-size:11px; letter-spacing:0.14em; color:#2da44e; margin-bottom:6px; font-weight:600; }
.diff-arrow {
  width:52px; height:52px; border-radius:50%;
  background:linear-gradient(135deg,var(--p),var(--p2));
  display:flex; align-items:center; justify-content:center; color:#fff; font-size:20px;
}
.tag-list .tag {
  padding:6px 13px; border-radius:9px; font-size:13px; font-weight:500;
  background:rgba(var(--p-rgb),0.06); color:var(--ink-2); border:1px solid rgba(var(--p-rgb),0.1);
}
.team-flow { display:flex; gap:20px; align-items:flex-end; }
.team-card { flex:1; padding:28px 24px; border-radius:22px; text-align:center; }
.team-card.tm3 { border:2px solid rgba(var(--p-rgb),0.3); }
.team-card .tm-lv { font-size:12px; font-weight:700; letter-spacing:0.14em; color:var(--ink-4); margin-bottom:10px; }
.team-card .tm-title { font-size:20px; font-weight:600; margin-bottom:8px; }
.team-card .tm-desc { font-size:14px; color:var(--ink-3); line-height:1.55; }
.task-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:20px; margin-top:44px; }
.task-card { padding:32px 28px; position:relative; overflow:hidden; }
.time-badge { position:absolute; top:24px; right:24px; padding:6px 13px; border-radius:100px; background:rgba(var(--p-rgb),0.1); color:var(--p); font-size:12px; font-weight:700; }
.tnum { font-size:52px; font-weight:700; line-height:1; color:rgba(var(--p-rgb),0.16); margin-bottom:12px; }
.ttitle { font-size:22px; font-weight:600; margin-bottom:14px; }
.tstep { font-size:14.5px; color:var(--ink-2); line-height:1.75; }
.tstep .li { display:flex; gap:9px; margin-bottom:7px; }
.tstep .li .bullet { color:var(--p); font-weight:700; flex-shrink:0; }
.deliver { margin-top:16px; padding-top:14px; border-top:1px solid rgba(0,0,0,0.06); font-size:13.5px; color:var(--ink-3); }
.deliver strong { color:var(--ink); }
.qa-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:18px; margin-top:42px; }
.qa-item { padding:26px 28px; }
.qa-q { font-size:17px; font-weight:600; margin-bottom:12px; display:flex; gap:11px; }
.qa-q .qmark { color:var(--p); font-weight:700; }
.qa-a { font-size:15px; color:var(--ink-3); line-height:1.65; padding-left:30px; }
.check-wrap { display:grid; grid-template-columns:1fr 1fr; gap:24px; margin-top:42px; }
.check-box { padding:32px 30px; border-radius:24px; }
.check-box.must { background:rgba(var(--p-rgb),0.055); }
.check-box.bonus { background:rgba(95,204,124,0.06); }
.cb-head { display:flex; align-items:center; gap:12px; margin-bottom:22px; }
.cb-icon { width:38px; height:38px; border-radius:12px; display:flex; align-items:center; justify-content:center; font-size:19px; color:#fff; background:linear-gradient(135deg,var(--p),var(--p2)); }
.check-box.bonus .cb-icon { background:linear-gradient(135deg,#5fcc7c,#2da44e); }
.cb-title { font-size:20px; font-weight:600; }
.cb-sub { font-size:12px; color:var(--ink-4); letter-spacing:0.08em; margin-top:2px; }
.cb-item { display:flex; gap:13px; align-items:flex-start; padding:14px 0; border-bottom:1px solid rgba(0,0,0,0.05); font-size:15.5px; color:var(--ink-2); line-height:1.55; }
.cb-item:last-child { border-bottom:none; }
.cb-item .box { width:19px; height:19px; border-radius:6px; flex-shrink:0; margin-top:2px; border:2px solid rgba(0,0,0,0.15); }
.next-bar {
  margin-top:26px; padding:22px 32px; border-radius:20px;
  background:rgba(var(--p-rgb),0.06); border:1px solid rgba(var(--p-rgb),0.14);
  display:flex; align-items:center; justify-content:space-between; gap:24px;
}
.nb-text strong { font-size:18px; letter-spacing:-0.01em; }
.nb-badge { padding:11px 22px; border-radius:100px; background:linear-gradient(135deg,var(--p),var(--p2)); color:#fff; font-size:15px; font-weight:600; }
.pipe-flow { display:flex; align-items:center; gap:14px; }
.pipe-node {
  padding:22px 20px; border-radius:18px; text-align:center; flex:1;
}
.pipe-name { font-size:16px; font-weight:600; margin-bottom:5px; }
.pipe-out { font-size:12.5px; color:var(--ink-3); line-height:1.45; }
.pipe-arrow { font-size:20px; color:var(--ink-4); flex-shrink:0; }
.chapter-nav {
  position:fixed; top:26px; left:50%; transform:translateX(-50%);
  display:flex; gap:6px; padding:6px 8px; z-index:200;
  background:rgba(255,255,255,0.75);
  backdrop-filter:blur(24px) saturate(180%); -webkit-backdrop-filter:blur(24px) saturate(180%);
  border:1px solid rgba(255,255,255,0.6); border-radius:100px;
  box-shadow:0 8px 32px rgba(0,0,0,0.08);
}
.chapter-nav .cp {
  padding:6px 14px; border-radius:100px; font-size:12px; font-weight:600;
  letter-spacing:0.06em; color:var(--ink-4); cursor:pointer; transition:all .3s;
}
.chapter-nav .cp.active { background:linear-gradient(135deg,var(--p),var(--p2)); color:#fff; }
.chapter-nav .cp.done { color:var(--ink-3); background:rgba(0,0,0,0.04); }

/* ===== Plan 页面类型样式 ===== */
.cover-small { font-size:34px; color:var(--ink-3); font-weight:500; display:block; margin-bottom:8px; }
.cover-big { font-size:52px; font-weight:600; }
.cover-badge {
  display:inline-flex; align-items:center; gap:10px; padding:9px 20px; border-radius:100px;
  background:rgba(var(--p-rgb),0.1); border:1px solid rgba(var(--p-rgb),0.18);
  font-size:14px; font-weight:600; letter-spacing:0.1em; color:var(--p); margin-bottom:30px;
}
.cover-meta { display:flex; gap:14px; margin-top:44px; justify-content:center; flex-wrap:wrap; }
.cover-meta .meta-pill {
  display:flex; align-items:center; padding:11px 20px; border-radius:100px;
  background:var(--glass); border:1px solid rgba(255,255,255,0.6); box-shadow:var(--shadow-1);
  font-size:15px; font-weight:500; color:var(--ink-2);
}
.promise-card { padding:60px 80px; max-width:1000px; text-align:center; }
.promise-card .lead { font-size:34px; color:var(--ink-3); margin-bottom:12px; }
.promise-card .from { font-size:50px; font-weight:600; margin-bottom:16px; }
.promise-card .arrow { font-size:34px; color:var(--ink-3); margin:12px 0; }
.promise-card .to { font-size:52px; font-weight:700; line-height:1.15; }
.card-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:18px; margin-top:44px; }
.card-grid[data-columns="2"] { grid-template-columns:repeat(2,1fr); }
.card-grid[data-columns="4"] { grid-template-columns:repeat(4,1fr); }
.card-grid .pcard { padding:30px 26px; border-radius:22px; text-align:center; position:relative; overflow:hidden; }
.pcard .pnum { font-size:48px; font-weight:700; line-height:1; color:rgba(var(--p-rgb),0.16); margin-bottom:12px; }
.pcard .ptag { font-size:11px; font-weight:700; letter-spacing:0.14em; color:var(--ink-4); margin-bottom:12px; text-transform:uppercase; }
.pcard .ptitle { font-size:21px; font-weight:600; margin-bottom:10px; }
.pcard .pdesc { font-size:14px; color:var(--ink-3); line-height:1.55; }
.pcard .plabel { font-size:12px; font-weight:600; letter-spacing:0.14em; color:var(--ink-4); margin-bottom:8px; }
.pcard .pnum-color { font-weight:700; }
.rows-list { display:flex; flex-direction:column; gap:14px; margin-top:44px; max-width:1080px; margin-left:auto; margin-right:auto; }
.day-row {
  display:grid; grid-template-columns:110px 110px 1fr 1.2fr; align-items:center; gap:20px; padding:20px 28px;
}
.day-row .day-pill { padding:6px 14px; border-radius:100px; font-size:14px; font-weight:600; background:rgba(var(--p-rgb),0.12); color:var(--p); justify-self:start; }
.day-row .date { font-size:15px; color:var(--ink-3); font-weight:500; }
.day-row .theme { font-size:20px; font-weight:600; }
.day-row .output { font-size:15px; color:var(--ink-2); }
.logic-flow { display:flex; align-items:stretch; justify-content:center; gap:14px; margin-top:56px; }
.logic-card { flex:1; padding:30px 22px 26px; text-align:center; border-radius:22px; }
.logic-card .icon-ring { width:60px; height:60px; border-radius:50%; margin:0 auto 14px; background:rgba(var(--p-rgb),0.12); display:flex; align-items:center; justify-content:center; font-size:20px; font-weight:700; color:var(--p); }
.logic-card .label { font-size:11px; font-weight:600; letter-spacing:0.16em; color:var(--ink-4); margin-bottom:6px; }
.logic-card .keyword { font-size:29px; font-weight:700; margin-bottom:8px; color:var(--p); }
.logic-card .desc { font-size:13px; color:var(--ink-3); line-height:1.5; }
.logic-arrow { display:flex; align-items:center; color:var(--ink-4); font-size:20px; }
.price-flow { display:flex; align-items:center; justify-content:center; gap:20px; margin-top:56px; }
.price-card { flex:1; padding:34px 28px; text-align:center; border-radius:24px; }
.price-card .plabel { font-size:13px; font-weight:600; letter-spacing:0.1em; color:var(--ink-4); margin-bottom:14px; }
.price-card .pvalue { font-size:60px; font-weight:700; letter-spacing:-0.04em; line-height:1; }
.price-card .pvalue .cur { font-size:30px; color:var(--ink-3); font-weight:500; margin-right:4px; }
.price-card .pnote { font-size:13.5px; color:var(--ink-3); margin-top:12px; line-height:1.45; }
.price-card.original .pvalue { color:var(--ink-3); text-decoration:line-through; }
.price-card.final { background:linear-gradient(135deg,var(--p),var(--p2)); }
.price-card.final .plabel, .price-card.final .pvalue, .price-card.final .pnote, .price-card.final .pvalue .cur { color:#fff; }
.price-arrow { font-size:26px; color:var(--ink-4); }
.notice-bar {
  margin-top:30px; display:flex; align-items:center; justify-content:center; gap:12px;
  padding:16px 26px; border-radius:100px; max-width:760px; margin-left:auto; margin-right:auto;
  background:rgba(95,204,124,0.1); border:1px solid rgba(95,204,124,0.25); font-size:15px;
}
.notice-bar .check { width:24px; height:24px; border-radius:50%; background:#2da44e; color:#fff; display:flex; align-items:center; justify-content:center; font-size:14px; font-weight:700; flex-shrink:0; }
.signup-flow { display:flex; gap:14px; margin-top:48px; }
.step-card { flex:1; padding:28px 22px; text-align:center; border-radius:22px; }
.step-num { width:46px; height:46px; border-radius:50%; margin:0 auto 16px; background:linear-gradient(135deg,var(--p),var(--p2)); color:#fff; display:flex; align-items:center; justify-content:center; font-size:19px; font-weight:700; }
.step-title { font-size:18px; font-weight:600; margin-bottom:8px; }
.step-desc { font-size:13.5px; color:var(--ink-3); line-height:1.5; }
.cta-card {
  padding:60px 72px; max-width:900px; text-align:center; border-radius:36px;
  background:linear-gradient(135deg, rgba(var(--p-rgb),0.05), rgba(142,140,255,0.07));
}
.cta-eyebrow { font-size:13px; font-weight:700; letter-spacing:0.18em; color:var(--p); margin-bottom:22px; }
.cta-title { font-size:66px; font-weight:700; letter-spacing:-0.03em; line-height:1.08; margin-bottom:26px; white-space:pre-line; }
.cta-subtitle { font-size:20px; color:var(--ink-2); line-height:1.55; white-space:pre-line; }
.cta-slogan { font-size:17px; color:var(--ink-3); margin-top:32px; letter-spacing:0.04em; }
.why-split { display:grid; grid-template-columns:1fr 1fr; gap:26px; margin-top:44px; }
.panel { padding:32px; border-radius:26px; }
.panel.wrong { background:rgba(255,95,87,0.05); }
.panel.right { background:rgba(95,204,124,0.07); }
.panel-head { display:flex; align-items:center; gap:11px; margin-bottom:20px; }
.panel-head .mark { width:30px; height:30px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:15px; font-weight:700; color:#fff; flex-shrink:0; }
.panel.wrong .mark { background:#ff5f57; }
.panel.right .mark { background:#2da44e; }
.panel-head .ptitle { font-size:21px; font-weight:600; }
.panel.wrong .ptitle { color:#c83a3a; }
.panel.right .ptitle { color:#2da44e; }
.panel .item { display:flex; gap:12px; padding:13px 0; border-bottom:1px solid rgba(0,0,0,0.05); font-size:15.5px; color:var(--ink-2); line-height:1.55; }
.panel .item:last-of-type { border-bottom:none; }
.panel .formula {
  margin-top:18px; padding:16px 20px; border-radius:14px; background:rgba(255,255,255,0.65);
  font-family:var(--mono); font-size:14px; text-align:center;
}
.layer-flow { display:grid; grid-template-columns:repeat(3,1fr); gap:20px; margin-top:44px; }
.layer-card { padding:28px 24px; border-radius:24px; position:relative; overflow:hidden; }
.layer-card::before { content:''; position:absolute; top:0; left:0; right:0; height:5px; background:linear-gradient(90deg,var(--p),var(--p2)); }
.layer-tag { display:inline-block; padding:5px 12px; border-radius:100px; font-size:11px; font-weight:700; letter-spacing:0.14em; background:rgba(var(--p-rgb),0.12); color:var(--p); margin-bottom:14px; }
.layer-file { font-family:var(--mono); font-size:19px; font-weight:600; margin-bottom:6px; }
.layer-cn { font-size:14px; color:var(--ink-4); margin-bottom:14px; }
.layer-def { font-size:14.5px; color:var(--ink-2); line-height:1.6; padding:13px 15px; border-radius:13px; background:rgba(255,255,255,0.55); margin-bottom:12px; }
.layer-q { font-size:13.5px; color:var(--ink-3); display:flex; gap:8px; }
.layer-q .q { color:var(--p); font-weight:700; }

/* ===== 弹出式详情卡片（detailable / modal / chips） ===== */
.detailable { cursor:pointer; position:relative; transition:transform .25s, box-shadow .25s, border-color .25s; }
.detailable:hover, .detailable:focus-visible { border-color:rgba(var(--p-rgb),0.4); box-shadow:var(--shadow-2); transform:translateY(-2px); }
.detailable:focus-visible { outline:2px solid var(--p); outline-offset:2px; }
.detailable::after {
  content:'ⓘ 详情'; position:absolute; top:12px; right:14px;
  font-size:11px; font-weight:600; letter-spacing:0.04em; color:var(--p);
  background:rgba(var(--p-rgb),0.09); padding:3px 10px; border-radius:100px;
}
.chips-wrap { display:flex; flex-wrap:wrap; gap:14px; justify-content:center; margin-top:46px; max-width:1020px; }
.deep-chip {
  padding:13px 22px; border-radius:100px; font-size:15px; font-weight:600; color:var(--ink-2);
  display:inline-flex; align-items:center; gap:8px;
}
.deep-chip .chip-sub { font-size:12px; font-weight:500; color:var(--ink-4); }
.deep-chip.detailable::after { content:'⌄'; position:static; background:none; padding:0; color:var(--p); font-size:14px; }
.chips-note { margin-top:26px; font-size:14px; color:var(--ink-3); text-align:center; }
.modal-overlay {
  position:fixed; inset:0; z-index:300; display:flex; align-items:center; justify-content:center;
  padding:28px; background:rgba(20,22,28,0.38);
  backdrop-filter:blur(14px) saturate(160%); -webkit-backdrop-filter:blur(14px) saturate(160%);
}
.modal-overlay[hidden] { display:none; }
.modal-card {
  position:relative; width:min(680px, 100%); max-height:78vh; overflow-y:auto;
  background:rgba(255,255,255,0.9);
  backdrop-filter:blur(30px) saturate(180%); -webkit-backdrop-filter:blur(30px) saturate(180%);
  border:1px solid rgba(255,255,255,0.7); border-radius:26px; box-shadow:var(--shadow-2);
  padding:34px 38px 30px;
}
.modal-close {
  position:absolute; top:16px; right:16px; width:36px; height:36px; border-radius:50%;
  border:none; background:rgba(0,0,0,0.05); color:var(--ink-2); font-size:15px; cursor:pointer;
}
.modal-close:hover { background:rgba(0,0,0,0.1); }
.modal-head { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:14px; padding-right:44px; }
.modal-badge {
  padding:4px 12px; border-radius:100px; font-size:11px; font-weight:700; letter-spacing:0.06em;
  background:rgba(var(--p-rgb),0.1); color:var(--p); flex:none;
}
.modal-title { font-size:24px; font-weight:700; letter-spacing:-0.01em; line-height:1.3; }
.modal-body { font-size:15.5px; line-height:1.75; color:var(--ink-2); }
.modal-body p { margin-bottom:12px; }
.modal-body ul { margin:0 0 12px 20px; }
.modal-body li { margin-bottom:6px; }
.modal-body code { background:rgba(0,0,0,0.05); border-radius:5px; padding:2px 6px; font-family:var(--mono); font-size:13px; }
.modal-source { margin-top:16px; padding-top:14px; border-top:1px solid rgba(0,0,0,0.06); font-size:12.5px; color:var(--ink-4); }

/* ===== 移动端适配 ===== */
@media (max-width: 768px) {
  .slide { padding:76px 20px 90px; justify-content:flex-start; overflow-y:auto; -webkit-overflow-scrolling:touch; }
  .title { font-size:30px !important; }
  .body { font-size:15px !important; }
  .goal-cards, .task-grid, .qa-grid, .check-wrap, .card-grid, .why-split, .layer-flow { grid-template-columns:1fr !important; gap:16px !important; }
  .card-grid[data-columns="2"], .card-grid[data-columns="4"] { grid-template-columns:1fr !important; }
  .diff-row { grid-template-columns:1fr !important; gap:10px; padding:18px 20px; }
  .price-flow, .signup-flow { flex-direction:column !important; align-items:stretch !important; gap:14px !important; }
  .price-card, .step-card { width:100% !important; }
  .price-arrow, .signup-flow .logic-arrow { transform:rotate(90deg); align-self:center; }
  .cta-card { max-width:100% !important; padding:36px 22px !important; border-radius:26px !important; }
  .cta-title { font-size:38px !important; }
  .cover-small { font-size:24px !important; }
  .cover-big { font-size:36px !important; }
  .table-wrap, table { max-width:100%; }
  table { display:block; overflow-x:auto; }
  .next-bar { flex-direction:column; align-items:flex-start; padding:18px 20px; }
  .chapter-nav { white-space:nowrap; }
  .content-wrap { min-width:0 !important; overflow-wrap:anywhere; }
  .diff-arrow { display:none; }
  .team-flow { flex-direction:column !important; align-items:stretch !important; }
  .team-card { width:100% !important; padding-bottom:28px !important; }
  .content-wrap { max-width:100% !important; }
  .blob { filter:blur(60px) !important; opacity:0.3 !important; }
  .blob.b1 { width:280px !important; height:280px !important; }
  .blob.b2 { width:320px !important; height:320px !important; }
  .blob.b3 { width:220px !important; height:220px !important; }
  .brand-tag { display:none; }
  .page-tag { top:14px; right:16px; font-size:10px; }
  .day-nav { top:10px; padding:4px 6px; }
  .day-nav .dp { padding:5px 10px; font-size:11px; }
  .chapter-nav { top:10px; padding:4px 6px; max-width:calc(100vw - 32px); overflow-x:auto; }
  .chapter-nav .cp { padding:5px 10px; font-size:11px; }
  .progress { bottom:14px; max-width:92vw; overflow:hidden; }
  .code-body { font-size:12.5px !important; padding:16px 18px !important; }
  .pipe-flow { flex-direction:column !important; align-items:stretch !important; }
  .pipe-node { min-width:0 !important; }
  .pipe-arrow { transform:rotate(90deg); align-self:center; }
  .num-badge, .tnum { font-size:38px !important; }
  .cmp-table { font-size:13px !important; }
  .scroll-hint { display:none; }
  .detailable::after { top:8px; right:10px; font-size:10px; }
  .chips-wrap { gap:10px; margin-top:32px; }
  .deep-chip { padding:11px 18px; font-size:14px; }
  .modal-overlay { padding:0; align-items:flex-end; }
  .modal-card { border-radius:22px 22px 0 0; max-height:82vh; padding:26px 22px 30px; width:100%; }
  .modal-title { font-size:20px; }
  .modal-body { font-size:14.5px; }
}
"""

# ============================================================
# 第五步：生成章节 HTML
# ============================================================

def rgb(hex_color):
    h = hex_color.lstrip('#')
    return ','.join(str(int(h[i:i+2], 16)) for i in (0, 2, 4))

def gen_chapter_slides(chapter, ch_idx, brand, theme_color, doc_title):
    """生成一个章节的所有 slide HTML"""
    # 设置章节主题色
    style_override = (f'<style>.slide[data-chapter="{ch_idx}"] {{ '
                      f'--p: {theme_color}; --p2: #8e8cff; '
                      f'--p-rgb: {rgb(theme_color)}; }}</style>')
    slides = []
    sections = chapter.get('sections', [])
    preamble = chapter.get('preamble', [])

    # 封面页（每章第一个 slide）
    cover = f'''
  <section class="slide slide-cover" data-chapter="{ch_idx}">
    {blob_html()}
    <div class="content-wrap" style="display:flex; flex-direction:column; align-items:center; text-align:center;">
      <div class="eyebrow-chip" style="margin-bottom:26px;">{esc(brand)} · {esc(doc_title)}</div>
      <h1 class="cover-title" style="font-size:72px; font-weight:700; letter-spacing:-0.03em; margin-bottom:20px;">
        <span class="gradient-text">{esc(chapter['title'])}</span>
      </h1>
      {f'<p class="body-lg">{inline_md(" ".join(preamble))}</p>' if preamble else ''}
    </div>
  </section>'''
    slides.append(cover + (style_override if ch_idx == 0 else ''))

    # 内容页
    for i, sec in enumerate(sections):
        body_md = '\n'.join(clean_lines(sec['lines']))
        sec['body_md'] = body_md
        ptype = detect_page_type(body_md, sec['h3'], i == 0)
        tpl = TEMPLATES.get(ptype, tpl_content)
        inner = tpl(chapter, sec, i)
        nav = f'<div class="page-tag">{esc(chapter["title"])} · {i+1:02d}</div>'
        slides.append(f'''
  <section class="slide slide-{ptype}" data-chapter="{ch_idx}">
    {blob_html()}
    {nav}
    {inner}
  </section>''')

    return slides, style_override

# ============================================================
# 第六步：合并
# ============================================================

def merge(all_slides_html, chapter_starts, brand, title, theme_colors, detail_data=None):
    detail_data = detail_data or {}
    dots = ''
    nav_labels = ['总览'] + [f'Day {i}' for i in range(1, len(chapter_starts))]
    nav_html = ''.join(
        f'<span class="cp{" active" if i == 0 else ""}" data-goto="{s}">{l}</span>'
        for i, (s, l) in enumerate(zip(chapter_starts, nav_labels))
    )

    # 各章节主题色覆盖（放在所有样式之后，覆盖 :root）
    theme_css = ''
    for i, c in enumerate(theme_colors):
        theme_css += (f'\n.slide[data-chapter="{i}"] {{ '
                      f'--p: {c}; --p-rgb: {rgb(c)}; }}')

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(brand)} · {esc(title)}</title>
<style>{BASE_CSS}{theme_css}</style>
</head>
<body>
<div class="chapter-nav" id="chapterNav">{nav_html}</div>
<div class="deck" id="deck">
{''.join(all_slides_html)}
</div>
<div class="progress" id="progress">{dots}</div>
<div class="modal-overlay" id="detailModal" hidden>
  <div class="modal-card" role="dialog" aria-modal="true" aria-label="详情">
    <button class="modal-close" type="button" aria-label="关闭详情">✕</button>
    <div class="modal-head">
      <span class="modal-badge" hidden></span>
      <h3 class="modal-title"></h3>
    </div>
    <div class="modal-body"></div>
    <div class="modal-source" hidden></div>
  </div>
</div>
<script>
const slides = document.querySelectorAll('.slide');
const progress = document.getElementById('progress');
const chapterNav = document.getElementById('chapterNav');
const cps = chapterNav.querySelectorAll('.cp');
const chapterStarts = {json.dumps(chapter_starts)};

slides.forEach((_, i) => {{
  const dot = document.createElement('span');
  dot.className = 'dot' + (i === 0 ? ' active' : '');
  dot.addEventListener('click', () => go(i));
  progress.appendChild(dot);
}});
const dots = progress.querySelectorAll('.dot');
let current = 0;
if (slides[current]) slides[current].classList.add('active');
const DETAIL_DATA = {json.dumps(detail_data, ensure_ascii=False).replace('</', '<\\/')};
const detailModal = document.getElementById('detailModal');
let detailModalOpen = false;
function openDetail(id) {{
  const d = DETAIL_DATA[id];
  if (!d) return;
  detailModal.querySelector('.modal-title').textContent = d.title || '';
  const badge = detailModal.querySelector('.modal-badge');
  if (d.badge) {{ badge.textContent = d.badge; badge.hidden = false; }} else {{ badge.hidden = true; }}
  const src = detailModal.querySelector('.modal-source');
  if (d.source) {{ src.textContent = '来源：' + d.source; src.hidden = false; }} else {{ src.hidden = true; }}
  detailModal.querySelector('.modal-body').innerHTML = d.html;
  detailModal.hidden = false;
  detailModalOpen = true;
  detailModal.querySelector('.modal-card').scrollTop = 0;
}}
function closeDetailModal() {{
  if (!detailModalOpen) return;
  detailModal.hidden = true;
  detailModalOpen = false;
}}
detailModal.addEventListener('click', e => {{
  if (e.target === detailModal || e.target.closest('.modal-close')) closeDetailModal();
}});
function go(n) {{
  if (n < 0 || n >= slides.length) return;
  slides[current].classList.remove('active');
  dots[current].classList.remove('active');
  current = n;
  slides[current].classList.add('active');
  dots[current].classList.add('active');
  updateChapterNav();
}}
function updateChapterNav() {{
  let ac = 0;
  for (let i = chapterStarts.length - 1; i >= 0; i--) {{
    if (current >= chapterStarts[i]) {{ ac = i; break; }}
  }}
  cps.forEach((cp, i) => {{
    cp.classList.toggle('active', i === ac);
    cp.classList.toggle('done', i < ac);
  }});
}}
cps.forEach(cp => cp.addEventListener('click', () => go(parseInt(cp.dataset.goto))));
document.addEventListener('keydown', e => {{
  if (detailModalOpen) {{ if (e.key === 'Escape') closeDetailModal(); return; }}
  if (['ArrowRight','PageDown',' '].includes(e.key)) {{ e.preventDefault(); go(current+1); }}
  if (['ArrowLeft','PageUp'].includes(e.key)) go(current-1);
  if (e.key === 'Home') go(0);
  if (e.key === 'End') go(slides.length-1);
}});
document.addEventListener('click', e => {{
  if (e.target.closest('.progress') || e.target.closest('.chapter-nav')) return;
  if (e.target.closest('.modal-overlay')) return;
  const card = e.target.closest('.detailable');
  if (card && card.dataset.detail) {{ openDetail(card.dataset.detail); return; }}
  if (e.clientX > window.innerWidth * 0.6) go(current+1);
  else if (e.clientX < window.innerWidth * 0.4) go(current-1);
}});
(function() {{
  let sx = 0, sy = 0, st = 0;
  document.addEventListener('touchstart', e => {{
    if (e.target.closest('.progress') || e.target.closest('.chapter-nav') || e.target.closest('.modal-overlay')) {{ sx = 0; return; }}
    sx = e.touches[0].clientX; sy = e.touches[0].clientY; st = Date.now();
  }}, {{passive:true}});
  document.addEventListener('touchend', e => {{
    if (!sx) return;
    const dx = e.changedTouches[0].clientX - sx;
    const dy = e.changedTouches[0].clientY - sy;
    const dt = Date.now() - st;
    sx = 0;
    if (dt > 600 || Math.abs(dx) < 50 || Math.abs(dy) > 80) return;
    if (detailModalOpen) {{ closeDetailModal(); return; }}
    let el = e.target, scroller = null;
    while (el && el !== document.body) {{
      const stl = window.getComputedStyle(el);
      if ((stl.overflowX === 'auto' || stl.overflowX === 'scroll') && el.scrollWidth > el.clientWidth) {{ scroller = el; break; }}
      el = el.parentElement;
    }}
    if (scroller) {{
      const atStart = scroller.scrollLeft <= 0;
      const atEnd = scroller.scrollLeft + scroller.clientWidth >= scroller.scrollWidth - 1;
      if ((dx < 0 && !atEnd) || (dx > 0 && !atStart)) return;
    }}
    if (dx < 0) go(current + 1); else go(current - 1);
  }}, {{passive:true}});
}})();
updateChapterNav();
</script>
</body>
</html>
'''

# ============================================================
# 主入口
# ============================================================

def sanitize_text(text, brand, replace_legacy_brand=False, normalize_dates=False):
    """按显式策略清洗文本；默认不改写日期、URL或品牌。"""
    text = str(text)
    if replace_legacy_brand:
        text = re.sub(r'BOGUJIN|bogujin', brand, text)
    if normalize_dates:
        text = re.sub(r'(?<![\w:/])7/(\d+)（周[一二三四五]）', lambda m: f'第 {int(m.group(1))-5} 天', text)
        text = re.sub(r'(?<![\w:/])7/(\d+) 周[一二三四五]', lambda m: f'第 {int(m.group(1))-5} 天', text)
        text = re.sub(r'(?<![\w:/])7/(\d+)', lambda m: f'第 {int(m.group(1))-5} 天', text)
        text = text.replace('每周一', '每周固定时间')
    return text


def sanitize_plan(plan, brand, replace_legacy_brand=False, normalize_dates=False):
    """对 Plan 中的文本字段统一应用显式清洗策略。"""
    plan = copy.deepcopy(plan)
    def visit(value):
        if isinstance(value, dict):
            return {k: visit(v) for k, v in value.items()}
        if isinstance(value, list):
            return [visit(v) for v in value]
        if isinstance(value, str):
            return sanitize_text(value, brand, replace_legacy_brand, normalize_dates)
        return value
    return visit(plan)


def build_parser():
    parser = argparse.ArgumentParser(description='将 Markdown 或 AI 生成的 plan.json 渲染为单文件 H5 课件')
    parser.add_argument('md_path', nargs='?', help='Markdown 课件路径（规则模式）')
    parser.add_argument('--plan', dest='plan_path', help='AI 编排 plan.json 路径')
    parser.add_argument('--brand', default=None, help='品牌名')
    parser.add_argument('--title', default=None, help='课件标题')
    parser.add_argument('--out', dest='out_dir', default=None, help='输出目录')
    parser.add_argument('--theme', default=None, help='逗号分隔的 #RRGGBB 主题色')
    parser.add_argument('--merged-name', default=None, help='合并版 HTML 文件名')
    parser.add_argument('--replace-legacy-brand', action='store_true', help='将 BOGUJIN 替换为当前品牌')
    parser.add_argument('--normalize-dates', action='store_true', help='将符合规则的课程日期转换为第 N 天')
    return parser


def parse_theme(value):
    if value is None:
        return None
    colors = [item.strip() for item in value.split(',') if item.strip()]
    if not colors or any(not re.fullmatch(r'#[0-9a-fA-F]{6}', c) for c in colors):
        raise ValueError('--theme 必须是逗号分隔的 #RRGGBB 颜色')
    return colors


def output_file(out_dir, brand, merged_name):
    return Path(out_dir) / (merged_name or f'{brand}_H5课件_完整版.html')


def main():
    parser = build_parser()
    args = parser.parse_args()
    if bool(args.plan_path) == bool(args.md_path):
        parser.error('必须且只能指定 md_path 或 --plan')
    try:
        theme = parse_theme(args.theme)
        if args.plan_path:
            plan_path = Path(args.plan_path)
            plan = json.loads(plan_path.read_text(encoding='utf-8'))
            brand = args.brand or plan.get('brand', DEFAULT_BRAND)
            plan = sanitize_plan(plan, brand, args.replace_legacy_brand, args.normalize_dates)
            if args.brand:
                plan['brand'] = args.brand
            if args.title:
                plan['title'] = args.title
            if theme:
                plan['theme_colors'] = theme
            html = render_plan(plan)
            out_dir = Path(args.out_dir) if args.out_dir else plan_path.parent
            out_file = output_file(out_dir, plan.get('brand', DEFAULT_BRAND), args.merged_name)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file.write_text(html, encoding='utf-8')
            print(f'生成完成: {out_file}')
            print(f'总页数: {html.count("<section class=")}')
            print(f'文件大小: {out_file.stat().st_size / 1024:.1f} KB')
            return

        md_path = Path(args.md_path)
        brand = args.brand or DEFAULT_BRAND
        md_text = sanitize_text(md_path.read_text(encoding='utf-8'), brand, args.replace_legacy_brand, args.normalize_dates)
        doc_title, chapters = parse_markdown(md_text)
        title = args.title or doc_title or 'H5 课件'
        chapters = [c for c in chapters if c.get('sections') or c.get('preamble')]
        if not chapters:
            raise ValueError('Markdown 中没有找到任何 ## 章节')
        out_dir = Path(args.out_dir) if args.out_dir else md_path.parent / 'H5输出'
        theme_source = theme or DEFAULT_THEME
        theme_colors = [theme_source[i % len(theme_source)] for i in range(len(chapters))]
        all_slides, chapter_starts = [], []
        for idx, ch in enumerate(chapters):
            chapter_starts.append(len(all_slides))
            slides, _ = gen_chapter_slides(ch, idx, brand, theme_colors[idx], title)
            all_slides.extend(slides)
            print(f'  {ch["title"]}: {len(slides)} 页 (主题色 {theme_colors[idx]})')
        html = merge(all_slides, chapter_starts, brand, title, theme_colors)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_file(out_dir, brand, args.merged_name)
        out_file.write_text(html, encoding='utf-8')
        print(f'\n生成完成: {out_file}')
        print(f'总页数: {len(all_slides)}')
        print(f'文件大小: {out_file.stat().st_size / 1024:.1f} KB')
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

if __name__ == '__main__':
    main()
