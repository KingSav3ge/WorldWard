"""Preview or import committed Engine/App/Catalog snapshots; never push."""
import argparse
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
from check_integration_gate import from_file, require_ready

ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATHS = ('IRGS_3_3', 'engine', 'provenance', 'ROADMAP.md', 'CONTINUATION_STATUS.md', 'DEVELOPMENT_LIST.md')
APP_PATHS = ('IRGS_Web', 'Start-IRGS.cmd')
CATALOG_PATHS = ('IRGS_Catalog',)
JOINED_EVIDENCE = {'engine/qualification/operation_register.json', 'engine/OPERATION_COVERAGE.md'}


def joined_owned_path(name):
    return name.startswith(('provenance/qa/', 'provenance/coordination/')) or name in JOINED_EVIDENCE


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def clean(repo):
    if git(repo, 'status', '--porcelain').strip():
        raise ValueError('Commit or preserve local changes before syncing: ' + str(repo))


def snapshot(repo, prefixes):
    clean(repo)
    commit = git(repo, 'rev-parse', 'HEAD').decode().strip()
    tracked = git(repo, 'ls-tree', '-r', '--name-only', commit).decode().splitlines()
    selected = [p for p in prefixes if any(name == p or name.startswith(p + '/') for name in tracked)]
    if not selected:
        raise ValueError('The checkout contains no expected component source: ' + str(repo))
    files = {}
    with tarfile.open(fileobj=io.BytesIO(git(repo, 'archive', commit, '--', *selected))) as archive:
        for member in archive:
            if member.isdir():
                continue
            if joined_owned_path(member.name):
                continue  # Current QA reports belong to joined integration.
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or '..' in path.parts
                    or '\\' in member.name or member.size > 100 * 1024 * 1024
                    or not any(member.name == p or member.name.startswith(p + '/') for p in selected)):
                raise ValueError('Unsafe component entry: ' + member.name)
            files[member.name] = archive.extractfile(member).read()
    return commit, files


def sync(engine, app, catalog, apply=False):
    clean(ROOT)
    engine_commit, engine_files = snapshot(engine, ENGINE_PATHS)
    app_commit, app_files = snapshot(app, APP_PATHS)
    catalog_commit, catalog_files = snapshot(catalog, CATALOG_PATHS)
    commits = {'engine': engine_commit, 'app': app_commit, 'catalog': catalog_commit}
    pins = {name: git(app, 'rev-parse', 'HEAD:' + name.title()).decode().strip()
            for name in ('engine', 'catalog')}
    gate = from_file(ROOT, commits, pins)
    if git(app, 'rev-parse', 'HEAD:Engine').decode().strip() != engine_commit:
        raise ValueError('Selected Engine commit differs from the App pin')
    if git(app, 'rev-parse', 'HEAD:Catalog').decode().strip() != catalog_commit:
        raise ValueError('Selected Catalog commit differs from the App pin')
    if apply:
        require_ready(ROOT, commits, pins)
    sources = engine_files | app_files | catalog_files
    old = {name for name in git(ROOT, 'ls-files', '--', *ENGINE_PATHS, *APP_PATHS, *CATALOG_PATHS).decode().splitlines()
           if not joined_owned_path(name)}
    changed = sorted(name for name, data in sources.items()
        if not (ROOT / name).exists() or (ROOT / name).read_bytes() != data)
    removed = sorted(old - sources.keys())
    if apply:
        # Validate the complete mutation set before writing any destination.
        for name in changed + removed:
            path = ROOT / name
            if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != ROOT.parent):
                raise ValueError('Refusing a linked destination: ' + name)
        for name in changed:
            path = ROOT / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(sources[name])
        for name in removed:
            (ROOT / name).unlink()
        config = json.loads((ROOT / 'COMPONENTS.json').read_text())
        config['engine']['commit'], config['app']['commit'] = engine_commit, app_commit
        config['catalog']['commit'] = catalog_commit
        (ROOT / 'COMPONENTS.json').write_text(json.dumps(config, indent=2) + '\n')
    return {'applied': apply, 'engine_commit': engine_commit, 'app_commit': app_commit,
        'catalog_commit': catalog_commit,
        'changed_paths': changed, 'removed_paths': removed, 'integration_gate': gate,
        'committed': False, 'pushed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(sync(args.engine.resolve(), args.app.resolve(), args.catalog.resolve(), args.apply), indent=2))
