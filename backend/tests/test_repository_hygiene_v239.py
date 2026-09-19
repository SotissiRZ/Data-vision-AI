from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'repository_hygiene.py'


def load_module():
    spec = importlib.util.spec_from_file_location('repository_hygiene', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_repository_hygiene_current_tree_is_clean():
    module = load_module()
    assert module.check(ROOT) == []


def test_historical_manifests_are_not_in_root():
    assert not list(ROOT.glob('MERGE_MANIFEST_V*.json'))
    manifests = list((ROOT / 'docs' / 'history' / 'manifests').glob('MERGE_MANIFEST_V*.json'))
    assert len(manifests) >= 35


def test_migration_history_is_archived():
    assert not (ROOT / 'MIGRATION_FROM_V212.md').exists()
    assert (ROOT / 'docs' / 'history' / 'migrations' / 'MIGRATION_FROM_V212.md').is_file()


def test_operational_files_remain_at_root():
    for name in ('README.md', 'SECURITY.md', 'VERSION', 'docker-compose.yml', 'preflight-windows.ps1'):
        assert (ROOT / name).is_file(), name
