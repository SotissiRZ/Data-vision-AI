from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_notebook_ui_exposes_version_binding_run_all_and_promotion():
    source = (ROOT / "frontend/components/NotebookStudio.tsx").read_text(encoding="utf-8")
    client = (ROOT / "frontend/lib/notebook-client.ts").read_text(encoding="utf-8")

    assert "bindNotebookDataset" in source
    assert "getNotebookDatasetVersions" in source
    assert "▶ Tout exécuter" in source
    assert "Promouvoir en dataset" in source
    assert "promoteNotebookArtifact" in source
    assert "dataset_binding" in client
    assert "/bind" in client
    assert "/promote" in client


def test_workspace_ui_keeps_python_sql_r_and_artifact_download():
    source = (ROOT / "frontend/components/NotebookStudio.tsx").read_text(encoding="utf-8")
    assert '(["markdown", "python", "sql", "r"] as NotebookLanguage[])' in source
    assert "downloadNotebookArtifact" in source
    assert "Provenance" in source
