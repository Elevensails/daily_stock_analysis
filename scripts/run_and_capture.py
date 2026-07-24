#!/usr/bin/env python3
"""Run main.py, capture output to reports/ directory."""
import os, sys, subprocess
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone(timedelta(hours=8)))
tslot = os.environ.get('TIME_SLOT', now.strftime('%H%M'))
today = now.strftime('%Y%m%d')
os.makedirs('reports', exist_ok=True)

# Run main.py and capture output
result = subprocess.run([sys.executable, 'main.py'], capture_output=True, text=True, timeout=600)
output = result.stdout
if result.stderr:
    output += '
' + result.stderr

# Save to reports/
report_path = f'reports/report_{tslot}_{today}.md'
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(output)
print(f'Saved {len(output)} chars to {report_path}')
print(f'main.py exit code: {result.returncode}')
