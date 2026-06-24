"""
Citrinitas · 熔知 — 报告渲染器（完整版）

负责将搜索结果和LLM合成结果渲染为HTML/PDF报告。
包含图片处理、表格转换、KaTeX公式渲染等功能。
"""
import os
import re
import io
import base64
import tempfile
import html
import subprocess
from typing import Optional

from qconst import PROJECT_DIR
from datetime import datetime, timezone

# 输出目录（与 search_engine.py 保持一致）
OUTPUT_DIR = os.path.join(PROJECT_DIR, "local_data", "reports")

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    PILImage = None
    HAS_PIL = False

# ── 图片处理 ──

def img_to_b64(img_path: str, max_w: int = 800) -> str:
    """
    将图片文件转为 base64 data URI，嵌入 HTML 使用。
    自动缩小到 max_w 像素以内（避免 HTML 文件过大）。
    失败返回空字符串。
    
    D5 修复：支持相对路径（相对于 PROJECT_DIR）
    """
    if not os.path.isabs(img_path):
        img_path = os.path.join(PROJECT_DIR, img_path)
    
    if HAS_PIL:
        try:
            with PILImage.open(img_path) as im:
                w, h = im.size
                if w > max_w:
                    ratio = max_w / w
                    im = im.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format=im.format or "PNG")
                data = base64.b64encode(buf.getvalue()).decode()
        except Exception:
            try:
                with open(img_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode()
            except Exception:
                return ""
    else:
        try:
            with open(img_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
        except Exception:
            return ""
    
    ext = os.path.splitext(img_path)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}.get(ext, "image/png")
    return f"data:{mime};base64,{data}"


def img_tag(img_path: str, max_w: int = 700) -> str:
    """将图片路径转为 base64 <img> 标签，失败返回原路径 file:// 引用。"""
    b64 = img_to_b64(img_path, max_w=max_w)
    if b64:
        return f'<br><img src="{b64}" class="evidence-img"><br>'
    return f'<br><img src="file://{html.escape(img_path)}" class="evidence-img"><br>'


# ── 表格处理 ──

def formula_to_html_spans(text: str) -> str:
    """将 LaTeX 公式转为 <span class="formula-block/inline"> 标记，供 KaTeX 后处理。"""
    FORMULA_BLOCK_RE = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
    FORMULA_INLINE_RE = re.compile(r'(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)', re.DOTALL)
    
    text = FORMULA_BLOCK_RE.sub(r'<span class="formula-block">\1</span>', text)
    text = FORMULA_INLINE_RE.sub(r'<span class="formula-inline">\1</span>', text)
    return text


def cell_html(raw: str) -> str:
    """处理 table cell: 先转义HTML防XSS，再还原公式和图片引用。"""
    s = html.escape(raw)
    s = formula_to_html_spans(s)
    s = re.sub(r'\[image:\s*(.+?)\]', lambda m: img_tag(m.group(1).strip()), s)
    return s


def pipe_table_to_html(pipe_lines: list) -> str:
    """将 Markdown 管道表格行列表转为 HTML <table>。列宽由内容预计算。"""
    rows = []
    for pl in pipe_lines:
        cells = pl.strip().strip('|').split('|')
        rows.append([c.strip() for c in cells])
    
    data_rows = [rows[0]] + rows[2:] if len(rows) >= 3 else rows
    ncols = max(len(r) for r in data_rows) if data_rows else 0
    
    if ncols > 0:
        col_widths_ch = [0.0] * ncols
        for row in data_rows:
            for i, cell in enumerate(row):
                if i >= ncols:
                    break
                w = sum(2.0 if ord(c) > 127 else 1.0 for c in cell)
                if w > col_widths_ch[i]:
                    col_widths_ch[i] = w
        
        total_ch = sum(col_widths_ch)
        if total_ch > 0:
            col_pcts = [max(5.0, w / total_ch * 100.0) for w in col_widths_ch]
            pct_sum = sum(col_pcts)
            col_pcts = [p / pct_sum * 100.0 for p in col_pcts]
        else:
            col_pcts = [100.0 / ncols] * ncols
        
        colgroup = '<colgroup>' + ''.join(f'<col style="width:{p:.1f}%">' for p in col_pcts) + '</colgroup>'
    else:
        colgroup = ''
    
    html_parts = ['<div class="md-table-wrap"><table class="md-table">', colgroup]
    for ri, row in enumerate(data_rows):
        tag = 'th' if ri == 0 else 'td'
        html_parts.append('<tr>')
        for cell in row:
            html_parts.append(f'<{tag}>{cell_html(cell)}</{tag}>')
        html_parts.append('</tr>')
    html_parts.append('</table></div>')
    
    return ''.join(html_parts)


def format_evidence_text(text: str) -> str:
    """格式化原始素材文本为 HTML：表格自动转 <table>，公式/图片引用包裹。"""
    lines = text.split('\n')
    pipe_lines = [l for l in lines if l.strip().startswith('|')]
    
    if len(pipe_lines) >= 3 and '---' in pipe_lines[1]:
        return pipe_table_to_html(pipe_lines)
    
    result = []
    for line in lines:
        escaped = html.escape(line)
        escaped = re.sub(r'\[image:\s*([^\]]+)\]', lambda m: img_tag(m.group(1).strip()), escaped)
        escaped = formula_to_html_spans(escaped)
        result.append(escaped)
    
    return '\n'.join(result)


# ── KaTeX 服务端渲染 ──

_KATEX_CSS = None
_NODE_BIN = os.environ.get("KB_NODE_BIN") or "node"
_NPM_ROOT = os.environ.get("KB_NPM_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "node_modules")
_KATEX_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_math.js")


def katex_css() -> str:
    """返回 KaTeX CSS（惰性加载，只读一次）。"""
    global _KATEX_CSS
    if _KATEX_CSS is None:
        css_path = os.path.join(_NPM_ROOT, "katex", "dist", "katex.min.css")
        try:
            with open(css_path, "r", encoding="utf-8") as f:
                _KATEX_CSS = f.read()
        except FileNotFoundError:
            _KATEX_CSS = ""
    return _KATEX_CSS


def katex_post_process(html: str) -> str:
    """将 HTML 中的 <span class="formula-block">... 和 <span class="formula-inline">...
    批量渲染为 KaTeX HTML。失败时保留原始 span作为兜底。"""
    import json
    
    formulas = []
    pattern = re.compile(
        r'<span class="formula-(block|inline)">(.*?)</span>',
        re.DOTALL
    )
    
    for m in pattern.finditer(html):
        display = (m.group(1) == "block")
        text = m.group(2).strip()
        if text:
            formulas.append({
                "text": text,
                "display": display,
                "start": m.start(),
                "end": m.end(),
                "original": m.group(0)
            })
    
    if not formulas:
        return html
    
    fd, tmp_in = tempfile.mkstemp(suffix=".json", prefix="katex_in_")
    os.close(fd)
    fd, tmp_out = tempfile.mkstemp(suffix=".json", prefix="katex_out_")
    os.close(fd)
    
    try:
        batch = [{"text": f["text"], "display": f["display"]} for f in formulas]
        with open(tmp_in, "w", encoding="utf-8") as f:
            json.dump({"formulas": batch}, f, ensure_ascii=False)
        
        env = os.environ.copy()
        env["NODE_PATH"] = _NPM_ROOT
        
        result = subprocess.run(
            [_NODE_BIN, _KATEX_SCRIPT, tmp_in, tmp_out],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 and os.path.exists(tmp_out):
            with open(tmp_out, "r", encoding="utf-8") as f:
                rendered = json.load(f)
            
            offset = 0
            for i, formula in enumerate(formulas):
                if i < len(rendered) and rendered[i].get("html"):
                    new_html = rendered[i]["html"]
                    start = formula["start"] + offset
                    end = formula["end"] + offset
                    html = html[:start] + new_html + html[end:]
                    offset += len(new_html) - (end - start)
        else:
            print(f"[KaTeX] 渲染失败: {result.stderr}")
    
    except Exception as e:
        print(f"[KaTeX] 渲染异常: {e}")
    finally:
        for tmp in [tmp_in, tmp_out]:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
    
    return html


# ── HTML 报告渲染 ──

def ensure_output_dir():
    """确保输出目录存在。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def render_report_html(
    query: str,
    synthesis: str,
    chunks: list,
    output_dir: str = None,
    used: list = None,
    citation_keys: list = None
) -> str:
    """
    渲染两层报告 HTML：上层 AI 回答 + 下层原始素材。
    返回 HTML 文件路径。
    """
    output_dir = output_dir or OUTPUT_DIR
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    # ── 上层：AI 回答（引用编号高亮） ──
    synthesis_html = synthesis
    synthesis_html = re.sub(r'\n\n+', '</p><p>', synthesis_html)
    synthesis_html = synthesis_html.replace('\n', '<br>')
    if not synthesis_html.startswith('<p>'):
        synthesis_html = '<p>' + synthesis_html
    if not synthesis_html.endswith('</p>'):
        synthesis_html = synthesis_html + '</p>'
    
    synthesis_html = re.sub(
        r'\[引用(\d+)\]',
        r'<a href="#ref\1" class="citation">[引用\1]</a>',
        synthesis_html
    )
    
    synthesis_html = formula_to_html_spans(synthesis_html)
    
    # ── 下层：原始素材 ──
    raw_sections = []
    for i, c in enumerate(chunks):
        orig_num = i + 1
        ref_id = f"ref{orig_num}"
        ref_tag = ""
        
        if used is not None:
            if orig_num in used:
                new_num = used.index(orig_num) + 1
                ref_id = f"ref{new_num}"
                ref_tag = f'<span class="ref-tag">[引用{new_num}]</span>'
            else:
                ref_id = f"ref{orig_num}-unused"
        else:
            ref_tag = f'<span class="ref-tag">[引用{orig_num}]</span>'
        
        src = c.get("source", "未知") or "未知"
        text_html = format_evidence_text(c["text"])
        score = c.get("score", 0)
        images_list = c.get("images", [])
        
        images_html = ""
        if images_list:
            imgs_parts = []
            for img in images_list:
                if not (img and os.path.isfile(img)):
                    continue
                b64 = img_to_b64(img, max_w=700)
                if b64:
                    imgs_parts.append(f'<div class="ev-img-wrap"><img src="{b64}" class="evidence-img"></div>')
            if imgs_parts:
                images_html = f'<div class="evidence-images">{"".join(imgs_parts)}</div>'
        
        raw_sections.append(f"""
        <div class="evidence-item" id="{ref_id}">
            <div class="evidence-header">
                {ref_tag}
                <span class="evidence-source">{html.escape(src)}</span>
                <span class="evidence-score">相关度: {score:.0%}</span>
            </div>
            <div class="evidence-text">{text_html}</div>
            {images_html}
        </div>""")
    
    # ── 完整 HTML ──
    katex_css_content = katex_css()
    
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
<title>知识库报告：{html.escape(query[:60])}</title>
<style>
  :root {{ --bg: #f8f9fa; --card: #fff; --text: #222; --muted: #666; --accent: #1a6fb5; --border: #e0e0e0; --formula-bg: #f0f4f8; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #1a1a2e; --card: #16213e; --text: #e0e0e0; --muted: #999; --accent: #7ec8e3; --border: #333; --formula-bg: #0f1928; }} }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; font-size: 15px; -webkit-text-size-adjust: 100%; }}
  .container {{ max-width: 900px; margin: 0 auto; padding: 32px 20px 80px; }}

  .toolbar {{ position: sticky; top: 0; z-index: 100; background: var(--card); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; }}
  .toolbar span {{ color: var(--muted); font-size: 13px; }}
  .btn-download {{ background: var(--accent); color: #fff; border: none; padding: 8px 20px; border-radius: 6px; font-size: 14px; cursor: pointer; }}
  .btn-download:hover {{ opacity: 0.85; }}

  .query-title {{ font-size: 22px; font-weight: 700; margin: 24px 0 8px; }}
  .query-meta {{ color: var(--muted); font-size: 13px; margin-bottom: 24px; }}

  .section {{ margin: 32px 0; }}
  .section h2 {{ font-size: 18px; color: var(--accent); border-bottom: 2px solid var(--border); padding-bottom: 8px; margin-bottom: 16px; }}

  .synthesis {{ background: var(--card); border-radius: 8px; padding: 24px; border: 1px solid var(--border); }}
  .synthesis p {{ margin: 8px 0; }}
  .citation {{ color: var(--accent); text-decoration: none; font-weight: 600; font-size: 13px; vertical-align: super; }}
  .citation:hover {{ text-decoration: underline; }}
  .formula-block {{ display: block; background: var(--formula-bg); padding: 10px 16px; border-radius: 4px; margin: 8px 0; font-family: "Times New Roman", serif; font-size: 16px; overflow-x: auto; }}
  .formula-inline {{ font-family: "Times New Roman", "Cambria Math", serif; font-style: italic; color: #1a5c8a; background: rgba(26,111,181,0.06); padding: 1px 4px; border-radius: 3px; word-break: keep-all; }}

  .evidence-item {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin: 16px 0; }}
  .evidence-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }}
  .ref-tag {{ background: var(--accent); color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; flex-shrink: 0; }}
  .evidence-source {{ color: var(--muted); font-size: 13px; }}
  .evidence-score {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
  .evidence-text {{ font-size: 14px; line-height: 1.8; word-break: break-word; }}
  .evidence-images {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
  .evidence-images img, .evidence-img {{ max-width: 100%; max-height: 400px; object-fit: contain; border: 1px solid var(--border); border-radius: 4px; margin: 6px 0; display: block; }}

  .md-table-wrap {{ max-width: 100%; overflow-x: auto; margin: 10px 0; -webkit-overflow-scrolling: touch; }}
  .md-table {{ border-collapse: collapse; font-size: 13px; table-layout: fixed; width: 100%; }}
  .md-table th {{ background: var(--formula-bg); color: var(--text); padding: 8px 10px; border: 1px solid var(--border); text-align: left; font-weight: 600; overflow-wrap: break-word; }}
  .md-table td {{ padding: 8px 10px; border: 1px solid var(--border); vertical-align: top; word-break: break-word; overflow-wrap: break-word; }}
  .md-table tr:nth-child(even) td {{ background: rgba(128,128,128,0.04); }}

  @media (max-width: 600px) {{
    .container {{ padding: 16px 12px 60px; }}
    .evidence-item {{ padding: 14px; }}
    .md-table {{ font-size: 12px; }}
    .md-table th, .md-table td {{ padding: 6px 8px; }}
    .formula-block {{ padding: 8px 10px; font-size: 14px; }}
    .evidence-images img, .evidence-img {{ max-height: 280px; }}
    .query-title {{ font-size: 18px; }}
    .toolbar {{ padding: 10px 16px; }}
  }}

  @media print {{
    .toolbar {{ display: none; }}
    body {{ background: #fff; color: #000; font-size: 12px; }}
    .container {{ max-width: 100%; padding: 0; }}
    .evidence-item, .synthesis {{ box-shadow: none; break-inside: avoid; }}
    .md-table-wrap {{ overflow-x: visible; }}
    .md-table {{ width: 100%; font-size: 11px; }}
  }}
{katex_css_content}
</style>
</head>
<body>
<div class="toolbar">
  <span>生成时间: {now_str}</span>
  <button class="btn-download" onclick="window.print()">📥 下载 PDF / 打印</button>
</div>
<div class="container">

  <h1 class="query-title">{html.escape(query)}</h1>
  <p class="query-meta">知识库检索 · {len(chunks)} 条匹配 · {now_str}</p>
  <div class="section">
    <h2>📝 综合回答</h2>
    <div class="synthesis">{synthesis_html}</div>
  </div>
  <div class="section">
    <h2>📚 原始素材</h2>
    {"".join(raw_sections)}
  </div>
</div>
</body>
</html>"""
    
    # KaTeX 服务端渲染
    html_content = katex_post_process(html_content)
    
    ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{timestamp}.html"
    html_path = os.path.join(output_dir, filename)
    
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return html_path
