"""Build a private claude.ai artifact that plays WorldWard in the browser.

The verified joined checkout is trimmed to its playable sources (no historical
archive, reference documents, images, tests or evidence), zipped, and paired
with a pinned Pyodide runtime. The page runs the unchanged App host and Engine
in Pyodide and routes the interface's /api/ calls to it in-process.
Never includes saves, settings, keys or provenance.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'claude_artifact'
PYODIDE_VERSION = '0.29.3'
# Exact Pyodide files published beside the page (npm pyodide@0.29.3 and the
# sqlite3 wheel from its GitHub release; wheel hash matches pyodide-lock.json).
PYODIDE_FILES = {
    'pyodide.asm.js': '1263f02b5b26099b96112378156f242dd98b39a8201ba7765e5fe3d455c5ce91',
    'pyodide.asm.wasm': 'e2f4ee75b325e35eb31bfb8c613d4dd5098f5502c156a97847686875b5025480',
    'python_stdlib.zip': '4298b6ee445cb724c3973437da47789752b9e6ff4e26619026b283ec801fc46b',
    'pyodide-lock.json': '3256ffc76388de0e37f4b34d42ab484268d1afc675179ff97b2a5bb14f84ccac',
    'pyodide.js': '718d40f1c015dd25ec724cc8fc4e2325d6a45a92ae225121ff6953f224a16f72',
    'sqlite3-1.0.0-cp313-cp313-pyodide_2025_0_wasm32.whl':
        'aab7214b987a3803fca283a8221e4b9d3274abc05d0cf506ea1a2ae7e09e3bf0',
}
# Published beside the page; the two scripts load from the jsDelivr npm CDN.
PUBLISHED_PYODIDE = ('pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json',
                     'sqlite3-1.0.0-cp313-cp313-pyodide_2025_0_wasm32.whl')
APP_STYLES = ('fonts.css', 'style.css', 'themes.css', 'preview.css')
ASSET_TYPES = {'.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.jpg': 'image/jpeg'}
INCLUDE_ROOTS = ('IRGS_3_3', 'IRGS_Web', 'IRGS_Catalog')
TOP_FILES = ('VERSION.json', 'COMPONENTS.json')
EXCLUDED_DIRS = {'tests', '__pycache__', 'results', 'historical_details', 'static', 'saves', 'trash',
                 'live', 'cache', 'source_documents', 'provenance', 'qualification', 'evidence'}
EXCLUDED_SUFFIXES = {'.pdf', '.docx', '.zip', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.woff2',
                     '.pyc', '.log', '.tmp', '.bak', '.md', '.ps1', '.cmd', '.sha256', '.patch'}
KEEP_MD = re.compile(r'^IRGS_3_3/catalog/campaigns/[^/]+/.*\.md$')


def wanted(relative: str) -> bool:
    path = PurePosixPath(relative)
    if set(path.parts[:-1]) & EXCLUDED_DIRS:
        return False
    if path.name.startswith('test_') and path.suffix == '.py':
        return False
    if path.suffix.lower() == '.md':
        return bool(KEEP_MD.match(relative))
    if path.suffix.lower() in EXCLUDED_SUFFIXES or '.part' in path.suffix:
        return False
    return True


def source_files():
    for name in TOP_FILES:
        yield name, ROOT / name
    for top in INCLUDE_ROOTS:
        for path in sorted((ROOT / top).rglob('*')):
            if path.is_file() and not path.is_symlink():
                relative = path.relative_to(ROOT).as_posix()
                if wanted(relative):
                    yield relative, path


def build_bundle(output: Path) -> dict:
    manifest = {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, path in source_files():
            data = path.read_bytes()
            manifest[relative] = hashlib.sha256(data).hexdigest()
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
        info = zipfile.ZipInfo('BUNDLE_MANIFEST.json', date_time=(2026, 1, 1, 0, 0, 0))
        archive.writestr(info, json.dumps(manifest, sort_keys=True, indent=0))
    data = buffer.getvalue()
    output.write_bytes(data)
    return {'files': len(manifest), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def copy_pyodide(source: Path, output: Path) -> dict:
    found = {}
    for name, expected in PYODIDE_FILES.items():
        candidates = [p for p in (source / name, source / 'pyodide' / name, source / 'x' / 'package' / name) if p.is_file()]
        if not candidates:
            raise SystemExit('Missing Pyodide file: ' + name)
        data = candidates[0].read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit('Pyodide file does not match its pinned hash: ' + name)
        found[name] = data
    (output / 'pyodide').mkdir(exist_ok=True)
    for name in PUBLISHED_PYODIDE:
        if name.endswith(('.zip', '.whl')):
            (output / 'pyodide' / (name + '.txt')).write_text(base64.b64encode(found[name]).decode())
        else:
            (output / 'pyodide' / name).write_bytes(found[name])
    return found


def _sri(data: bytes) -> str:
    return 'sha384-' + base64.b64encode(hashlib.sha384(data).digest()).decode()


def _inline_assets(text: str, static: Path) -> str:
    def data_uri(match):
        name = match.group(2)
        path = static / name
        mime = ASSET_TYPES[path.suffix]
        return match.group(1) + 'data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode()
    return re.sub(r'''(url\(["']?)/([a-z0-9-]+\.(?:woff2|svg|jpg))''', data_uri, text)


def _script_safe(text: str) -> str:
    return text.replace('</script', '<\\/script').replace('<!--', '<\\!--')


def build_page(output: Path, bundle: dict, pyodide: dict) -> dict:
    static = ROOT / 'IRGS_Web' / 'static'
    index = (static / 'index.html').read_text(encoding='utf-8')
    body = re.search(r'<body[^>]*>(.*)</body>', index, re.S).group(1)
    body = re.sub(r'<script\b[^>]*>.*?</script>', '', body, flags=re.S)
    scripts = re.findall(r'<script defer src="/([a-z.]+\.js)"></script>', index)
    if 'app.js' not in scripts:
        raise SystemExit('Unexpected App page structure')
    styles = '\n'.join(_inline_assets((static / name).read_text(encoding='utf-8'), static) for name in APP_STYLES)
    app_scripts = '\n'.join('<script>' + _script_safe((static / name).read_text(encoding='utf-8')) + '</script>'
                             for name in scripts)
    config = {'pyodideIndex': 'pyodide/', 'sqliteWheel': 'sqlite3-1.0.0-cp313-cp313-pyodide_2025_0_wasm32.whl',
              'bundle': 'worldward.zip', 'bundleSha256': bundle['sha256'], 'pyodideVersion': PYODIDE_VERSION}
    page = (TEMPLATE / 'page.html').read_text(encoding='utf-8')
    values = {'APP_STYLES': styles.replace('</style', '<\\/style'), 'APP_BODY': body,
              'CONFIG': _script_safe(json.dumps(config)),
              'BRIDGE_PY': _script_safe((TEMPLATE / 'bridge.py').read_text(encoding='utf-8')),
              'ASSIST_PY': _script_safe((TEMPLATE / 'claude_assist.py').read_text(encoding='utf-8')),
              'PYODIDE_VERSION': PYODIDE_VERSION, 'ASM_SRI': _sri(pyodide['pyodide.asm.js']),
              'LOADER_SRI': _sri(pyodide['pyodide.js']),
              'BOOT_JS': _script_safe((TEMPLATE / 'boot.js').read_text(encoding='utf-8')),
              'APP_SCRIPTS': app_scripts}
    for key, value in values.items():
        page = page.replace('{{' + key + '}}', value)
    if '{{' in re.sub(r'<script>.*?</script>', '', page, flags=re.S).split('<style>', 2)[0]:
        raise SystemExit('Unfilled page placeholder')
    (output / 'index.html').write_text(page, encoding='utf-8')
    return {'bytes': len(page.encode()), 'app_scripts': scripts}


def verify_checkout():
    sys.path.insert(0, str(ROOT / 'tools'))
    from verify_development import verify
    return verify()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bundle-only', action='store_true')
    parser.add_argument('--pyodide', type=Path, help='folder holding the pinned Pyodide files')
    parser.add_argument('--skip-verify', action='store_true', help='testing only')
    args = parser.parse_args()
    out = args.output.resolve()
    if out.is_relative_to(ROOT):
        raise SystemExit('Write the artifact outside the source checkout')
    out.mkdir(parents=True, exist_ok=True)
    if not args.skip_verify:
        verify_checkout()
    bundle = build_bundle(out / 'worldward.zip')
    # Artifacts serve no .zip files: publish the bundle as base64 text.
    (out / 'worldward.zip.txt').write_text(base64.b64encode((out / 'worldward.zip').read_bytes()).decode())
    (out / 'worldward.zip').unlink()
    result = {'bundle': bundle}
    if not args.bundle_only:
        if not args.pyodide:
            raise SystemExit('Pass --pyodide with the pinned Pyodide files')
        pyodide = copy_pyodide(args.pyodide.resolve(), out)
        result['page'] = build_page(out, bundle, pyodide)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
