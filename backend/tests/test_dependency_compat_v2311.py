from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_snowflake_cryptography_pin_is_compatible():
    requirements = (ROOT / "backend/requirements.txt").read_text()
    assert "snowflake-connector-python==4.7.4" in requirements
    assert "cryptography==46.0.5" in requirements
    assert "cryptography==46.0.4" not in requirements


def test_compose_project_name_is_stable():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert compose.startswith("name: datavision\n")


def test_windows_reset_script_preserves_volumes():
    script = (ROOT / "reset-docker.ps1").read_text()
    assert "docker compose down --remove-orphans" in script
    assert "docker rm -f" in script
    assert "docker volume rm" not in script
    assert "postgres_data" in script
