from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "frontend/app/page.tsx").read_text(encoding="utf-8")


def test_web_shell_always_uses_standard_authentication_gate():
    assert "if(!enterpriseBadge) return <AuthenticationGate" in PAGE
    assert "!authStatus?.local_dev_enabled" not in PAGE


def test_governance_no_longer_embeds_a_second_login_form():
    assert "Connexion DataVision Entreprise" not in PAGE
    assert "Connexion d’entreprise" not in PAGE
    assert "La gouvernance utilise exclusivement la session DataVision ouverte depuis l’écran standard Connexion / Inscription." in PAGE
    assert "Session expirée" in PAGE


def test_standard_auth_screen_remains_bidirectional():
    for needle in (
        'role="tab"',
        ">Connexion</button>",
        ">Inscription</button>",
        "Pas encore de compte ?",
        "Vous avez déjà un compte ?",
    ):
        assert needle in PAGE
