Run this bash command to regenerate and open the VibeCheck health dashboard:

```bash
python3 -c "
import sys
sys.path.insert(0, '.claude/hooks/lib')
from pathlib import Path
import health_report
health_report.generate_report(Path('.'))
print('Health report updated: .vibecheck/health-report.html')
" && open .vibecheck/health-report.html
```

If `open` doesn't work on this OS, tell the user to open `.vibecheck/health-report.html` manually in their browser.
