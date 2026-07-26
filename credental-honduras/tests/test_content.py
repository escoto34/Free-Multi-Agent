from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture(scope="module")
def html():
    path = ROOT / "index.html"
    return path.read_text(encoding="utf-8")

def test_index_html_exists():
    assert (ROOT / 'index.html').exists()

def test_spanish_content(html: str):
    assert 'Credenciales' in html
    assert 'Seguridad' in html
    assert 'Antifalsificación' in html
    assert 'San Pedro Sula' in html

def test_services_section(html: str):
    assert 'Identidad Corporativa' in html
    assert 'Imprenta de Seguridad' in html
    assert 'Protección Antifalsificación' in html

def test_cta_button(html: str):
    assert 'Solicitar Cotización' in html

def test_no_email_input(html: str):
    assert 'type="email"' not in html

def test_form_submission_script(html: str):
    assert 'script.js' in html
    assert 'contact-form' in html
    assert 'success-message' in html
