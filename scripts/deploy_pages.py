#!/usr/bin/env python3
"""将 reports/*.md 转为 HTML + 生成 index.html → 推送到 gh-pages 分支"""
import os, re, base64, json, urllib.request, urllib.parse, glob
from datetime import datetime

TOKEN = os.environ.get('GITHUB_TOKEN', '')
OWNER = 'Elevensails'
REPO = 'daily_stock_analysis'
API = f'https://api.github.com/repos/{OWNER}/{REPO}/contents'
BRANCH = 'gh-pages'

def md_to_html(md_text, title=''):
    """简易 Markdown → HTML 转换"""
    lines = md_text.split('\n')
    html_lines = []
    in_table = False
    in_code = False
    for line in lines:
        if line.startswith('```'):
            if in_code:
                html_lines.append('</code></pre>')
                in_code = False
            else:
                html_lines.append('<pre><code>')
                in_code = True
            continue
        if in_code:
            html_lines.append(line)
            continue
        # Table
        if '|' in line and line.strip().startswith('|'):
            if not in_table:
                html_lines.append('<table class="tbl">')
                in_table = True
                # header
                cells = [c.strip() for c in line.split('|')[1:-1]]
                html_lines.append('<thead><tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr></thead><tbody>')
                continue
            elif '---' in line or '===' in line:
                continue  # separator
            else:
                cells = [c.strip() for c in line.split('|')[1:-1]]
                html_lines.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
                continue
        else:
            if in_table:
                html_lines.append('</tbody></table>')
                in_table = False
        # Headers
        if line.startswith('# '):
            html_lines.append(f'<h1>{line[2:]}</h1>')
        elif line.startswith('## '):
            html_lines.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('### '):
            html_lines.append(f'<h3>{line[4:]}</h3>')
        elif line.startswith('> '):
            html_lines.append(f'<blockquote>{line[2:]}</blockquote>')
        elif line.startswith('- ') or line.startswith('* '):
            html_lines.append(f'<li>{line[2:]}</li>')
        elif line.strip() == '---':
            html_lines.append('<hr>')
        elif line.strip():
            # bold
            line = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
            html_lines.append(f'<p>{line}</p>')
    if in_table:
        html_lines.append('</tbody></table>')
    return '\n'.join(html_lines)

def gh_put(path, content_b64, sha=None):
    payload = {'message': f'deploy {path}', 'content': content_b64, 'branch': BRANCH}
    if sha:
        payload['sha'] = sha
    req = urllib.request.Request(
        f'{API}/{urllib.parse.quote(path)}',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'},
        method='PUT'
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code

def gh_get_sha(path):
    try:
        req = urllib.request.Request(
            f'{API}/{urllib.parse.quote(path)}?ref={BRANCH}',
            headers={'Authorization': f'Bearer {TOKEN}'}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get('sha')
    except:
        return None

def main():
    reports_dir = os.environ.get('REPORTS_DIR', 'reports')
    md_files = sorted(glob.glob(os.path.join(reports_dir, '*.md')))
    if not md_files:
        print('No MD files found')
        return

    CSS = '''<style>
:root{--accent:#1e40af;--bg:#f5f7fa;--card:#fff;--mut:#64748b;--red:#dc2626;--green:#16a34a;--orange:#ea580c;--line:#e5e7eb}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:15px;line-height:1.7;color:#1f2937}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px 60px}
header{background:linear-gradient(135deg,#1e3a5f,#1e40af);color:#fff;padding:24px 0 20px;margin-bottom:0}
header h1{margin:0 0 6px;font-size:24px}
header .sub{opacity:.92;font-size:13px}
.back{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.95);backdrop-filter:blur(8px);padding:10px 20px;border-bottom:1px solid var(--line);margin:0 -20px 16px}
.back a{display:inline-flex;align-items:center;gap:6px;background:linear-gradient(135deg,#1e3a5f,#1e40af);color:#fff;text-decoration:none;border-radius:8px;padding:8px 16px;font-size:13px;font-weight:600}
.module{background:var(--card);border-radius:14px;padding:18px 20px;margin:12px 0;box-shadow:0 2px 10px rgba(30,64,175,.06)}
.module h2{font-size:18px;margin:0 0 12px;color:var(--accent);border-left:4px solid var(--accent);padding-left:10px}
.module h3{font-size:15px;margin:14px 0 8px;color:#374151}
.module p{font-size:14px;line-height:1.7;color:#374151;margin:0 0 8px}
.module blockquote{border-left:4px solid var(--accent);background:#eff6ff;padding:10px 14px;margin:8px 0;border-radius:0 6px 6px 0;font-size:14px}
.module li{font-size:14px;line-height:1.7;color:#374151;margin:2px 0}
.module hr{border:none;border-top:1px solid var(--line);margin:16px 0}
table.tbl{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
table.tbl th{background:#f1f5f9;padding:8px 10px;text-align:left;font-weight:600;border-bottom:2px solid #cbd5e1}
table.tbl td{padding:6px 10px;border-bottom:1px solid #f1f5f9}
table.tbl tr:hover{background:#f8fafc}
footer{margin-top:30px;color:var(--mut);font-size:12px;text-align:center;border-top:1px solid var(--line);padding-top:14px}
.report-card{display:block;background:var(--card);border:1px solid var(--line);border-radius:11px;padding:14px 16px;margin:10px 0;text-decoration:none;color:inherit;transition:.15s}
.report-card:hover{transform:translateY(-2px);box-shadow:0 6px 16px rgba(0,0,0,.08)}
.report-card .rt{font-size:16px;font-weight:700;color:var(--accent)}
.report-card .rd{font-size:13px;color:var(--mut);margin-top:4px}
@media(max-width:760px){.wrap{padding:0 14px 40px}table.tbl{font-size:12px}}
</style>'''

    # Generate index.html
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    cards = []
    for md_file in md_files:
        basename = os.path.basename(md_file)
        html_name = basename.replace('.md', '.html')
        with open(md_file, 'r'
