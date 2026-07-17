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
    site = tmp_path / "brand-site" / "tests"
    site.mkdir(parents=True)
    tf = site / "test_content.py"
    tf.write_text("def test_ok(): assert True\n", encoding="utf-8")
    targets = select_pytest_targets(
        files_to_create=["brand-site/index.html", "brand-site/tests/test_content.py"],
        artifact=CodeArtifact(
            files={
                "brand-site/index.html": "<html></html>",
                "brand-site/tests/test_content.py": "def test_ok(): assert True\n",
            },
            summary="site",
        ),
        repo_root=tmp_path,
    )
    assert targets == ["brand-site/tests/test_content.py"]


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
