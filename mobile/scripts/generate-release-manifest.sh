#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
command -v node >/dev/null 2>&1 || { echo "HIBA: Node.js szükséges" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "HIBA: python3 szükséges" >&2; exit 1; }
VERSION=$(node -p "require('./package.json').version")
APP_ID=$(node --input-type=module - <<'NODE'
import config from './capacitor.config.js'
console.log(config.appId)
NODE
)
DIST=${MUNKALAP_NATIVE_DIST:-native-dist}
[ -s "$DIST/SHA256SUMS.txt" ] || { echo "HIBA: SHA256SUMS.txt hiányzik" >&2; exit 1; }
API_URL=$(grep '^VITE_API_BASE_URL=' .env | cut -d= -f2- || true)
PROJECT=${MUNKALAP_FIREBASE_PROJECT_ID:-}
CERT=${MUNKALAP_EXPECTED_SIGNING_CERT_SHA256:-}
python3 - "$DIST" "$VERSION" "$APP_ID" "$API_URL" "$PROJECT" "$CERT" <<'PY'
import datetime, hashlib, json, os, pathlib, sys
root = pathlib.Path(sys.argv[1])
version, app_id, api_url, project, cert = sys.argv[2:]
artifacts=[]
for path in sorted(root.glob(f'Munkalap-Technikus-{version}-release.*')):
    if path.suffix not in {'.apk', '.aab'}:
        continue
    h=hashlib.sha256(path.read_bytes()).hexdigest()
    artifacts.append({'name': path.name, 'size_bytes': path.stat().st_size, 'sha256': h})
if not artifacts:
    raise SystemExit('HIBA: nincs release APK/AAB artifact')
manifest={
    'schema_version': 1,
    'application': 'Munkalap Technikus',
    'package_id': app_id,
    'version': version,
    'api_base_url': api_url,
    'firebase_project_id': project or None,
    'expected_signing_cert_sha256': cert or None,
    'generated_at_utc': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
    'artifacts': artifacts,
}
(root/'release-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(root/'release-manifest.json')
PY
