#!/usr/bin/env python3
"""Deploy reports to GitHub Pages with time-slot structure.
Scans reports/ for report_HHMM_YYYYMMDD.md and market_review_HHMM_YYYYMMDD.md.
Converts MD→HTML, generates slot_HHMM.html pages, updates index.html."""
import os, re, base64, json, urllib.request, urllib.error, glob
from datetime import datetime, timezone, timedelta

TOKEN = os.environ.get('GITHUB_TOKEN', '')
if not TOKEN:
    print('FATAL: GITHUB_TOKEN is empty! Deploy cannot proceed.')
    raise SystemExit(1)
print(f'GITHUB_TOKEN length: {len(TOKEN)} (starts with: {TOKEN[:4]}...)')
API = 'https://api.github.com/repos/Elevensails/daily_stock_analysis/contents'
BRANCH = 'gh-pages'
HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}

CSS = '''<style>
:root{--accent:#1e40af;--bg:#f5f7fa;--card:#fff;--mut:#64748b;--line:#e5e7eb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:15px;line-height:1.7;color:#1f2937}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px 60px}
.back{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.95);backdrop-filter:blur(8px);padding:10px 20px;border-bottom:1px solid var(--line);margin:0 -20px 16px}
.back a{display:inline-flex;align-items:center;gap:6px;background:linear-gradient(135deg,#1e3a5f,#1e40af);color:#fff;text-decoration:none;border-radius:8px;padding:8px 16px;font-size:13px;font-weight:600}
.module{background:var(--card);border-radius:14px;padding:18px 20px;margin:12px 0;box-shadow:0 2px 10px rgba(30,64,175,.06)}
.module h2{font-size:18px;margin:0 0 12px;color:var(--accent);border-left:4px solid var(--accent);padding-left:10px}
.module h3{font-size:15px;margin:14px 0 8px;color:#374151}
.module p{font-size:14px;line-height:1.7;color:#374151;margin:0 0 8px}
.module blockquote{border-left:4px solid var(--accent);background:#eff6ff;padding:10px 14px;margin:8px 0;border-radius:0 6px 6px 0}
.module li{font-size:14px;line-height:1.7;color:#374151;margin:2px 0}
.module hr{border:none;border-top:1px solid var(--line);margin:16px 0}
table.tbl{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
table.tbl th{background:#f1f5f9;padding:8px 10px;text-align:left;font-weight:600;border-bottom:2px solid #cbd5e1}
table.tbl td{padding:6px 10px;border-bottom:1px solid #f1f5f9}
footer{margin-top:30px;color:var(--mut);font-size:12px;text-align:center;border-top:1px solid var(--line);padding-top:14px}
</style>'''

STORED_CSS = CSS  # Keep for later use

def md2html(md):
    """Simple Markdown to HTML converter."""
    lines = md.split('\n')
    out = []
    in_table = False
    for line in lines:
        if line.startswith('|'):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if not in_table:
                out.append('<table class="tbl"><thead><tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr></thead><tbody>')
                in_table = True
                continue
            if all(c.replace('-','').replace(':','') == '' for c in cells):
                continue
            out.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
        else:
            if in_table:
                out.append('</tbody></table>')
                in_table = False
            if line.startswith('# '): out.append(f'<h1>{line[2:]}</h1>')
            elif line.startswith('## '): out.append(f'<h2>{line[3:]}</h2>')
            elif line.startswith('### '): out.append(f'<h3>{line[4:]}</h3>')
            elif line.startswith('> '): out.append(f'<blockquote>{line[2:]}</blockquote>')
            elif line.startswith('- ') or line.startswith('* '): out.append(f'<li>{line[2:]}</li>')
            elif line.strip() == '---': out.append('<hr>')
            elif line.strip():
                line2 = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
                out.append(f'<p>{line2}</p>')
    if in_table:
        out.append('</tbody></table>')
    return '\n'.join(out)

def gh_put(path, content_str, sha=None):
    """Push file to gh-pages branch via GitHub API."""
    b64 = base64.b64encode(content_str.encode('utf-8')).decode('ascii')
    payload = {'message': f'deploy {path}', 'content': b64, 'branch': BRANCH}
    if sha:
        payload['sha'] = sha
    url = f'{API}/{path}'
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=HEADERS, method='PUT')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        print(f'  HTTP {e.code} for {path}')
        return e.code

def gh_get_sha(path):
    """Get file SHA from gh-pages branch."""
    try:
        req = urllib.request.Request(f'{API}/{path}?ref={BRANCH}', headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get('sha')
    except:
        return None

def nearest_slot(tslot):
    """Map any HHMM time to the nearest predefined slot."""
    slots = ['0900', '0930', '1200', '1430', '1800']
    t = int(tslot[:2]) * 60 + int(tslot[2:])
    return min(slots, key=lambda s: abs((int(s[:2])*60 + int(s[2:])) - t))

def gh_list_files():
    """List all files on gh-pages branch."""
    try:
        req = urllib.request.Request(f'{API}?ref={BRANCH}', headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except:
        return []

def make_report_page(md_file, html_name, now_ts):
    """Convert MD to HTML and push to gh-pages."""
    with open(md_file, 'r', encoding='utf-8') as f:
        md = f.read()
    title = md.split('\n')[0].replace('# ', '').strip()
    body = md2html(md)
    html = f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>{title}</title>{STORED_CSS}</head><body><div class="back"><a href="index.html" title="首页">🏠</a> <a href="javascript:history.back()" title="返回">←</a></div><div class="wrap"><div class="module">{body}</div><footer>{now_ts} · DeepSeek AI + akshare · 以上分析基于公开数据，不构成投资建议</footer></div></body></html>'
    sha = gh_get_sha(html_name)
    return gh_put(html_name, html, sha)

def make_slot_page(tslot, time_label, slot_name, color, color_dark, today, reports_dict):
    """Generate and push slot_HHMM.html page for a time slot."""
    now_ts = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    date_disp = '今日'
    
    cards = []
    slot_data = reports_dict.get(tslot, {})
    
    # Stock card
    if 'stock' in slot_data:
        cards.append(f'<a class="card stock" href="{slot_data["stock"]}" style="background:#fff;border:1px solid #e5e7eb;border-left:4px solid {color};border-radius:11px;padding:18px 20px;margin:14px 0;text-decoration:none;color:inherit;display:block"><div style="font-size:17px;font-weight:700">📊 个股分析</div><div style="font-size:13px;color:#64748b;margin-top:6px">4 只持仓逐一深度分析 · 舆情/业绩/技术面/操作点位/信号归因</div></a>')
    else:
        cards.append(f'<div style="background:#fff;border:1px solid #e5e7eb;border-left:4px solid {color};border-radius:11px;padding:18px 20px;margin:14px 0;opacity:.5"><div style="font-size:17px;font-weight:700;color:#1e40af">⏳ 个股分析</div><div style="font-size:13px;color:#64748b;margin-top:6px">待 cron 触发自动生成</div></div>')
    
    # Market card
    if 'market' in slot_data:
        cards.append(f'<a class="card market" href="{slot_data["market"]}" style="background:#fff;border:1px solid #e5e7eb;border-left:4px solid #0d9488;border-radius:11px;padding:18px 20px;margin:14px 0;text-decoration:none;color:inherit;display:block"><div style="font-size:17px;font-weight:700">🌍 大盘复盘</div><div style="font-size:13px;color:#64748b;margin-top:6px">盘面总览 · 指数结构 · 板块主线 · 资金情绪 · 明日交易计划</div></a>')
    else:
        cards.append(f'<div style="background:#fff;border:1px solid #e5e7eb;border-left:4px solid #0d9488;border-radius:11px;padding:18px 20px;margin:14px 0;opacity:.5"><div style="font-size:17px;font-weight:700;color:#1e40af">⏳ 大盘复盘</div><div style="font-size:13px;color:#64748b;margin-top:6px">待 cron 触发自动生成</div></div>')
    
    # Quant/Vibe card
    if 'vibe' in slot_data:
        cards.append(f'<a class="card quant" href="{slot_data["vibe"]}" style="background:#fff;border:1px solid #e5e7eb;border-left:4px solid #7c3aed;border-radius:11px;padding:18px 20px;margin:14px 0;text-decoration:none;color:inherit;display:block"><div style="font-size:17px;font-weight:700">📈 量化分析 · Vibe-Trading</div><div style="font-size:13px;color:#64748b;margin-top:6px">多智能体辩论 · MCP 对接 · 策略回测</div></a>')
    else:
        cards.append(f'<a class="card quant" href="quant.html" style="background:#fff;border:1px solid #e5e7eb;border-left:4px solid #7c3aed;border-radius:11px;padding:18px 20px;margin:14px 0;text-decoration:none;color:inherit;display:block"><div style="font-size:17px;font-weight:700">📈 量化分析 · Vibe-Trading</div><div style="font-size:13px;color:#64748b;margin-top:6px">多智能体辩论 · MCP 对接 · 策略回测</div></a>')
    
    slot_html = f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>{time_label} · A股分析</title>{STORED_CSS}</head><body><div class="back"><a href="index.html" title="首页">🏠</a> <a href="javascript:history.back()" title="返回">←</a></div><div class="wrap"><header style="background:linear-gradient(135deg,{color_dark},{color});color:#fff;padding:20px 18px;border-radius:14px;margin-bottom:20px"><h1 style="margin:0 0 4px;font-size:22px">🕐 {time_label} · {slot_name}</h1><div style="opacity:.85;font-size:13px">{date_disp} · DeepSeek AI · 4 只持仓</div></header>{chr(10).join(cards)}<footer style="margin-top:40px;color:#64748b;font-size:12px;text-align:center">以上分析基于公开数据，不构成投资建议</footer></div></body></html>'''
    
    fn = f'slot_{tslot}.html'
    sha = gh_get_sha(fn)
    return gh_put(fn, slot_html, sha)

def make_index(reports_dict, today):
    """Generate and push index.html with time-slot cards."""
    now = datetime.now(timezone(timedelta(hours=8)))
    ts = now.strftime('%Y-%m-%d %H:%M')
    
    SLOTS = {
        '0900': ('09:00', '早盘分析', '#f59e0b', '#92400e'),
        '0930': ('09:30', '开盘追踪', '#ef4444', '#991b1b'),
        '1200': ('12:00', '午间复盘', '#8b5cf6', '#5b21b6'),
        '1430': ('14:30', '午盘追踪', '#3b82f6', '#1e40af'),
        '1800': ('18:00', '收盘复盘', '#10b981', '#065f46'),
    }
    
    cards = ['<a class="card live" href="dashboard.html" style="background:#fff;border:1px solid #e5e7eb;border-left:4px solid #ca8a04;border-radius:11px;padding:16px 18px;margin:12px 0;text-decoration:none;color:inherit;display:block"><div style="font-size:16px;font-weight:700;color:#1e40af">⚡ 实时盯盘</div><div style="font-size:13px;color:#64748b;margin-top:4px">30 秒自动刷新 · 4 只持仓 + 三大指数 + 板块 Top</div></a>']
    
    for tslot, (time_label, slot_name, color, _) in SLOTS.items():
        slot_data = reports_dict.get(tslot, {})
        has_data = bool(slot_data)
        opacity = '' if has_data else 'opacity:.55;'
        badge = '<span style="display:inline-block;background:#16a34a;color:#fff;padding:2px 8px;border-radius:6px;font-size:10px;font-weight:600;margin-left:6px">已生成</span>' if has_data else '<span style="display:inline-block;background:#94a3b8;color:#fff;padding:2px 8px;border-radius:6px;font-size:10px;font-weight:600;margin-left:6px">待生成</span>'
        cards.append(f'<a class="card" href="slot_{tslot}.html" style="background:#fff;border:1px solid #e5e7eb;border-left:4px solid {color};border-radius:11px;padding:16px 18px;margin:12px 0;text-decoration:none;color:inherit;display:block;{opacity}"><div style="font-size:16px;font-weight:700;color:#1e40af">🕐 {time_label} · {slot_name} {badge}</div><div style="font-size:13px;color:#64748b;margin-top:4px">个股分析 + 大盘复盘 + 量化分析 · 点击查看</div></a>')
    
    cards.append('<a class="card quant" href="quant.html" style="background:#fff;border:1px solid #e5e7eb;border-left:4px solid #7c3aed;border-radius:11px;padding:16px 18px;margin:12px 0;text-decoration:none;color:inherit;display:block"><div style="font-size:16px;font-weight:700;color:#1e40af">📈 量化分析 · Vibe-Trading</div><div style="font-size:13px;color:#64748b;margin-top:4px">多智能体辩论 · MCP 对接 · 策略回测</div></a>')
    
    date_disp = '今日'
    index_html = f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>A股智能分析 · 决策仪表盘</title><style>
body{{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f7fa;color:#1f2937}}
.wrap{{max-width:900px;margin:0 auto;padding:40px 20px}}
header{{background:linear-gradient(135deg,#1e3a5f,#1e40af);color:#fff;padding:24px 0 20px;border-radius:14px;text-align:center;margin-bottom:20px}}
header h1{{margin:0 0 6px;font-size:24px}}header .sub{{opacity:.92;font-size:13px}}
.topstat{{display:flex;gap:10px;justify-content:center;margin-top:10px;flex-wrap:wrap}}
.topstat div{{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);border-radius:14px;padding:3px 12px;font-size:12px}}
footer{{margin-top:30px;color:#64748b;font-size:12px;text-align:center}}
</style></head><body><div class="wrap">
<header><h1>&#127919; A股智能分析 · 决策仪表盘</h1><div class="sub">DeepSeek AI · 4 只持仓 · 5 时段/天</div><div class="topstat"><div><b>5次/天</b></div><div><b>4</b> 持仓</div><div><b>3</b> 报告类型</div><div><b>&asymp;0</b> 月成本</div></div></header>
<div style="font-size:14px;font-weight:700;color:#6b7280;margin:24px 0 10px;padding-bottom:6px;border-bottom:1px solid #e5e7eb">&#128197; 今日 {date_disp} · 5 时段分析</div>
{''.join(cards)}
<footer>Fork 自 daily_stock_analysis (49K stars)<br>时段: 09:00 早盘 / 09:30 开盘 / 12:00 午间 / 14:30 午盘 / 18:00 收盘<br>以上分析基于公开数据，不构成投资建议</footer>
</div></body></html>'''
    
    sha = gh_get_sha('index.html')
    return gh_put('index.html', index_html, sha)

def main():
    reports_dir = os.environ.get('REPORTS_DIR', 'reports')
    now = datetime.now(timezone(timedelta(hours=8)))
    today = now.strftime('%Y%m%d')
    now_ts = now.strftime('%Y-%m-%d %H:%M')
    
    # Scan reports/ for all MD files
    md_files = sorted(glob.glob(os.path.join(reports_dir, '*.md')))
    print(f'Found {len(md_files)} MD files in {reports_dir}/')
    
    # Parse reports: {HHMM: {'stock': 'report_HHMM_YYYYMMDD.html', 'market': ...}}
    reports_dict = {}
    for f in md_files:
        basename = os.path.basename(f)
        m = re.match(r'report_(\d{4})_(\d{8})\.md', basename)
        mr = re.match(r'market_review_(\d{4})_(\d{8})\.md', basename)
        vb = re.match(r'vibe_(\d{4})_(\d{8})\.md', basename)
        if m:
            tslot_raw, date = m.group(1), m.group(2)
            tslot = nearest_slot(tslot_raw)
            html_name = basename.replace('.md', '.html')
            reports_dict.setdefault(tslot, {})['stock'] = html_name
            status = make_report_page(f, html_name, now_ts)
            print(f'  {status} {html_name}')
        elif mr:
            tslot_raw, date = mr.group(1), mr.group(2)
            tslot = nearest_slot(tslot_raw)
            html_name = basename.replace('.md', '.html')
            reports_dict.setdefault(tslot, {})['market'] = html_name
            status = make_report_page(f, html_name, now_ts)
            print(f'  {status} {html_name}')
        elif vb:
            tslot_raw, date = vb.group(1), vb.group(2)
            tslot = nearest_slot(tslot_raw)
            html_name = basename.replace('.md', '.html')
            reports_dict.setdefault(tslot, {})['vibe'] = html_name
            status = make_report_page(f, html_name, now_ts)
            print(f'  {status} {html_name}')
        else:
            print(f'  skip (no match): {basename}')
    
    # Generate slot pages for each time slot
    SLOTS = {
        '0900': ('09:00', '早盘分析', '#f59e0b', '#92400e'),
        '0930': ('09:30', '开盘追踪', '#ef4444', '#991b1b'),
        '1200': ('12:00', '午间复盘', '#8b5cf6', '#5b21b6'),
        '1430': ('14:30', '午盘追踪', '#3b82f6', '#1e40af'),
        '1800': ('18:00', '收盘复盘', '#10b981', '#065f46'),
    }
    
    for tslot, (time_label, slot_name, color, color_dark) in SLOTS.items():
        status = make_slot_page(tslot, time_label, slot_name, color, color_dark, today, reports_dict)
        print(f'  {status} slot_{tslot}.html')
    
    # Generate index.html
    status = make_index(reports_dict, today)
    print(f'  {status} index.html')
    
    # Push debug info
    import json as _json
    debug_info = {
        'reports_dir': reports_dir,
        'md_files_found': len(md_files),
        'md_file_names': [os.path.basename(f) for f in md_files],
        'cwd': os.getcwd(),
        'reports_dict_keys': list(reports_dict.keys()),
    }
    _json_str = _json.dumps(debug_info, indent=2)
    gh_put('debug.json', _json_str)
    print(f'  debug.json pushed')
    
    print('deploy done')

if __name__ == '__main__':
    main()
