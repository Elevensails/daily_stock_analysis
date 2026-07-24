#!/usr/bin/env python3
"""Run Vibe-Trading quant analysis and save output."""
import os, sys, subprocess, json
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone(timedelta(hours=8)))
tslot = os.environ.get('TIME_SLOT', now.strftime('%H%M'))
today = now.strftime('%Y%m%d')

# Install vibe-trading-ai
print('Installing vibe-trading-ai...')
subprocess.run([sys.executable, '-m', 'pip', 'install', 'vibe-trading-ai', '--quiet'], check=True)

# Setup .env for DeepSeek
os.makedirs('agent', exist_ok=True)
deepseek_key = os.environ.get('DEEPSEEK_API_KEY', '')
env_content = f"""LANGCHAIN_PROVIDER=deepseek
DEEPSEEK_API_KEY={deepseek_key}
DEEPSEEK_BASE_URL=https://api.deepseek.com
LANGCHAIN_MODEL_NAME=deepseek-chat
"""
with open('agent/.env', 'w') as f:
    f.write(env_content)

# Run vibe-trading analysis
prompt = (
    "Analyze these 4 A-share holdings for short-term trading signals: "
    "600036 招商银行, 159915 创业板ETF, 603823 百合花, 512400 有色金属ETF. "
    "For each, provide: technical indicators (MA, RSI, MACD), "
    "support/resistance levels, volume analysis, and a buy/sell/hold recommendation. "
    "Output as structured markdown."
)

print(f'Running vibe-trading with tslot={tslot}...')
result = subprocess.run(
    ['vibe-trading', 'run', '-p', prompt, '--json'],
    capture_output=True, text=True, timeout=600
)

# Save output
os.makedirs('reports', exist_ok=True)
json_path = f'reports/vibe_{tslot}_{today}.json'
with open(json_path, 'w', encoding='utf-8') as f:
    f.write(result.stdout)

# Also create markdown version for deploy_pages.py
md_path = f'reports/vibe_{tslot}_{today}.md'
with open(md_path, 'w', encoding='utf-8') as f:
    f.write('# Vibe-Trading 量化分析\n\n')
    f.write(f'> 运行时间: {now.strftime("%Y-%m-%d %H:%M")} | 模型: DeepSeek\n\n')
    try:
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            for key, value in data.items():
                f.write(f'## {key}\n\n{value}\n\n')
        else:
            f.write(str(data))
    except:
        f.write(f'```\n{result.stdout[:5000]}\n```')

print(f'Saved: {json_path} ({len(result.stdout)} chars)')
print(f'Saved: {md_path}')
