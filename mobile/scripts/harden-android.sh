#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
MANIFEST=android/app/src/main/AndroidManifest.xml
[ -f "$MANIFEST" ] || { echo "HIBA: Android projekt még nincs generálva. Futtasd: npx cap add android" >&2; exit 1; }
python3 - "$MANIFEST" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); s=p.read_text(encoding='utf-8')
start=s.find('<application')
end=s.find('>', start)
if start < 0 or end < 0: raise SystemExit('Nem található <application> az AndroidManifest.xml-ben')
tag=s[start:end+1]
for attr,val in [('android:allowBackup','false'),('android:usesCleartextTraffic','false')]:
    import re
    if re.search(rf'{re.escape(attr)}="[^"]*"', tag):
        tag=re.sub(rf'{re.escape(attr)}="[^"]*"', f'{attr}="{val}"', tag)
    else:
        tag=tag[:-1]+f' {attr}="{val}">'
s=s[:start]+tag+s[end+1:]
p.write_text(s,encoding='utf-8')
PY
echo "Android hardening alkalmazva: allowBackup=false, usesCleartextTraffic=false"
