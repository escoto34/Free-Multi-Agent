"""Vibe test runner: scoped pytest targets + static grounded checks."""

from __future__ import annotations

from pathlib import Path

from agents.vibe_coding.test_runner import (
    artifact_is_static_site,
    artifact_looks_like_node_project,
    execute_vibe_tests,
    run_static_content_checks,
    select_pytest_targets,
)
from agents.vibe_coding.web_quality import (
    lint_content_test_source,
    lint_vibe_web_artifact,
)
from schemas.vibe_coding import CodeArtifact, TechnicalSpec


def test_select_pytest_never_uses_monorepo_tests():
    targets = select_pytest_targets(
        files_to_create=["tests/", "app/page.tsx", "jest.config.js"],
        artifact=CodeArtifact(
            files={"app/page.tsx": "x", "package.json": "{}"},
            summary="next",
        ),
    )
    assert targets == []
    assert "tests/" not in targets


def test_select_pytest_local_site_tests(tmp_path: Path):
    site = tmp_path / "site" / "tests"
    site.mkdir(parents=True)
    tf = site / "test_content.py"
    tf.write_text("def test_ok(): assert True\n", encoding="utf-8")
    targets = select_pytest_targets(
        files_to_create=["site/index.html", "site/tests/test_content.py"],
        artifact=CodeArtifact(
            files={
                "site/index.html": "<html></html>",
                "site/tests/test_content.py": "def test_ok(): assert True\n",
            },
            summary="site",
        ),
        repo_root=tmp_path,
    )
    assert targets == ["site/tests/test_content.py"]


def test_static_checks_require_grounded_colors_and_wa():
    idea = "GROUNDED FACTS colors #004aad #cb6ce6 WhatsApp https://wa.me/15551234567"
    bad = CodeArtifact(
        files={
            "site/index.html": "<html><body>Hello clinic</body></html>",
            "site/css/style.css": "body{color:#4CAF50}",
        },
        summary="bad",
    )
    ok, log = run_static_content_checks(bad, idea)
    assert ok is False
    assert "Missing grounded" in log or "FAIL" in log

    good = CodeArtifact(
        files={
            "site/index.html": (
                '<html><a href="https://wa.me/15551234567">WA</a>'
                '<img src="https://acme.test.com/logo.png"></html>'
            ),
            "site/css/style.css": ":root{--p:#004aad;--a:#cb6ce6}",
        },
        summary="good",
    )
    ok2, log2 = run_static_content_checks(
        good,
        idea + " logo https://acme.test.com/logo.png",
    )
    assert ok2 is True, log2


def test_node_project_fails_execute_vibe_tests(tmp_path: Path):
    art = CodeArtifact(
        files={
            "package.json": '{"name":"x"}',
            "next.config.js": "module.exports={}",
            "app/page.tsx": "export default function P(){return null}",
            "jest.config.js": "module.exports={}",
        },
        summary="next",
    )
    assert artifact_looks_like_node_project(art)
    assert not artifact_is_static_site(art)
    logs = execute_vibe_tests(
        spec=TechnicalSpec(
            architecture="next",
            test_cases=["t"],
            files_to_create=list(art.files.keys()),
        ),
        artifact=art,
        idea="brand site",
        repo_root=tmp_path,
    )
    assert logs.startswith("OVERALL: FAIL")
    assert "NODE/JEST" in logs or "Next" in logs or "pytest only" in logs


def test_lint_flags_bare_at_content_test():
    issues = lint_content_test_source(
        'def test_no_email(html):\n    assert "@" not in html\n',
        path="site/tests/test_content.py",
    )
    assert issues
    assert any("@" in i and "media" in i.lower() for i in issues)


def test_lint_flags_invented_email_form_when_research_has_gap():
    art = CodeArtifact(
        files={
            "site/index.html": (
                "<html><style>@media (max-width:768px){nav{}}</style>"
                '<form><input type="email" name="email"></form></html>'
            ),
            "site/tests/test_content.py": (
                'def test_no_email(html):\n    assert "@" not in html\n'
            ),
        },
        summary="bad brand site",
    )
    idea = (
        "=== GROUNDED FACTS ===\n"
        "EMAILS: (none found in research — do not invent)\n"
        "WHATSAPP: https://wa.me/15551234567\n"
        "colors #004aad\n"
    )
    ok, log = lint_vibe_web_artifact(art, idea)
    assert ok is False
    assert "bare" in log.lower() or "media" in log.lower() or "fragile" in log.lower()
    assert "email" in log.lower()


def test_execute_vibe_fails_on_fragile_email_test(tmp_path: Path):
    site = tmp_path / "site"
    tests = site / "tests"
    tests.mkdir(parents=True)
    (site / "index.html").write_text(
        "<html><style>@media (max-width:768px){}</style>"
        '<a href="https://wa.me/15551234567">WA</a>'
        "<body style='color:#004aad'>ok</body></html>",
        encoding="utf-8",
    )
    test_src = (
        "def test_no_email():\n"
        "    html = open('site/index.html').read()\n"
        "    assert '@' not in html\n"
    )
    (tests / "test_content.py").write_text(test_src, encoding="utf-8")
    art = CodeArtifact(
        files={
            "site/index.html": (site / "index.html").read_text(encoding="utf-8"),
            "site/tests/test_content.py": test_src,
        },
        summary="fragile",
    )
    logs = execute_vibe_tests(
        spec=TechnicalSpec(
            architecture="static landing",
            test_cases=["no bare at"],
            files_to_create=list(art.files.keys()),
        ),
        artifact=art,
        idea="EMAILS: (none found in research) #004aad https://wa.me/15551234567",
        repo_root=tmp_path,
    )
    assert logs.startswith("OVERALL: FAIL")
    assert "WEB QUALITY LINT FAILED" in logs
