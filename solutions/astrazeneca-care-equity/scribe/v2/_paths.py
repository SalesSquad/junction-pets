"""Import path set-up shared by the version-2 modules.

Version 2 lives in scribe/v2/ and reuses version-1 modules from scribe/ (metrics, prompts, sample).
After this module is imported, scribe/v2 comes first on sys.path and scribe second, so that
`import evaluate` and `import config` resolve to version 2 while `import metrics` resolves to version 1.
"""

import pathlib
import sys

V2 = pathlib.Path(__file__).resolve().parent
SCRIBE = V2.parent
ROOT = SCRIBE.parent

for _p in (str(SCRIBE), str(V2)):
    while _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)
