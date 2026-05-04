Run this bash command to regenerate and open the VibeGuard health dashboard:

```bash
python3 -c "
import sys
sys.path.insert(0, '.claude/hooks/lib')
from pathlib import Path
import health_report
health_report.generate_report(Path('.'))
print('Health report updated: .vibeguard/health-report.html')
" && open .vibeguard/health-report.html
```

If `open` doesn't work on this OS, tell the user to open `.vibeguard/health-report.html` manually in their browser.
