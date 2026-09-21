from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PAGE=(ROOT/'frontend/app/page.tsx').read_text(encoding='utf-8')
API=(ROOT/'frontend/lib/api.ts').read_text(encoding='utf-8')
CSS=(ROOT/'frontend/app/globals.css').read_text(encoding='utf-8')

def test_v255_frontend_exposes_unified_control_plane():
    for token in ['Governance Control Plane','Couverture des contrôles','Matrice d\'accès effective','Publication dataset','Capturer un snapshot']:
        assert token in PAGE
    assert 'getGovernanceControlPlane' in PAGE and 'captureGovernanceSnapshot' in PAGE

def test_v255_frontend_api_has_control_plane_and_snapshots():
    assert '/governance/control-plane' in API
    assert '/governance/snapshots' in API

def test_v255_control_plane_is_responsive_and_uses_global_typography():
    assert '.control-plane-grid' in CSS
    assert '@media(max-width:650px)' in CSS
    assert 'font-size:12.5px' in CSS
