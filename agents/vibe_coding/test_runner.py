"""
Select and run tests for System A (Vibe Coding).

The Test Executor must NOT run the host monorepo's ``tests/`` suite when the
Coder generated a marketing site or a small feature without local tests.
It also must not expect Jest/npm when the runtime only has pytest.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from schemas.vibe_coding import CodeArtifact, TechnicalSpec

# Host product test tree — never run this as the vibe suite by default
_HOST_TEST_DIR_NAMES = frozenset({"tests", "test"})
_PYTEST_NAME_RE = re.compile(
    r"(?:^|/)(?:test_[^/]+\.py|[^/]+_test\.py)$", re.I
)
_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_WA_RE = re.compile(r"(?:wa\.me/|whatsapp).*?(\d{8,15})", re.I)


def is_pytest_path(path: str) -> bool:
    p = (path or "").replace("\\", "/")
    return bool(_PYTEST_NAME_RE.search(p))


def select_pytest_targets(
    *,
    files_to_create: Optional[list[str]] = None,
    artifact: Optional[CodeArtifact] = None,
    repo_root: Optional[Path] = None,
) -> list[str]:
    """Return relative pytest file paths safe to run for this vibe run only.

    Never returns a bare ``tests/`` that would execute the MultiAgent monorepo
    suite. Only concrete ``test_*.py`` / ``*_test.py`` paths from the architect
    list or the artifact file set, and only if they exist on disk when
    *repo_root* is provided.
    """
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        p = (raw or "").strip().replace("\\", "/")
        if not p or p in seen:
            return
        # Reject monorepo-wide catch-alls
        if p in ("tests", "tests/", "test", "test/", "./tests", "./tests/"):
            return
        if not is_pytest_path(p):
            # allow directory only if it is NOT the host tests/ and looks nested
            # e.g. credental-site/tests/ — still too broad; require files
            return
        seen.add(p)
        candidates.append(p)

    for f in files_to_create or []:
        _add(f)
    if artifact and artifact.files:
        for f in artifact.files:
            _add(f)

    if repo_root is None:
        return candidates

    existing: list[str] = []
    root = Path(repo_root)
    for p in candidates:
        full = (root / p).resolve()
        try:
            full.relative_to(root.resolve())
        except ValueError:
            continue
        if full.is_file():
            existing.append(p)
    return existing


def artifact_is_static_site(artifact: Optional[CodeArtifact]) -> bool:
    if not artifact or not artifact.files:
        return False
    paths = [p.replace("\\", "/").lower() for p in artifact.files]
    has_html = any(p.endswith(".html") or p.endswith(".htm") for p in paths)
    has_css_or_js = any(
        p.endswith(".css") or p.endswith(".js") for p in paths
    )
    has_next = any(
        "next.config" in p
        or p.endswith("package.json")
        or "/app/" in f"/{p}/"
        or p.startswith("app/")
        for p in paths
    )
    has_jest = any("jest.config" in p for p in paths)
    return has_html and not has_next and not has_jest


def artifact_looks_like_node_project(artifact: Optional[CodeArtifact]) -> bool:
    if not artifact or not artifact.files:
        return False
    paths = [p.replace("\\", "/").lower() for p in artifact.files]
    return any(
        p.endswith("package.json")
        or "next.config" in p
        or "jest.config" in p
        or p.endswith("tsconfig.json")
        for p in paths
    )


def _idea_must_strings(idea: str) -> list[str]:
    """Strings from grounded research that static sites should include when present."""
    idea = idea or ""
    must: list[str] = []
    for m in _HEX_RE.findall(idea):
        if m.lower() not in ("#000", "#000000", "#fff", "#ffffff"):
            must.append(m)
    for m in _WA_RE.finditer(idea):
        must.append(m.group(1))
        must.append(f"wa.me/{m.group(1)}")
    for pat in (
        r"https?://[^\s\)\]\"']+\.(?:png|jpe?g|svg|webp)",
        r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9._]+",
    ):
        for m in re.finditer(pat, idea, re.I):
            must.append(m.group(0).rstrip(".,);"))
    # de-dupe preserve order, cap
    out: list[str] = []
    seen: set[str] = set()
    for s in must:
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
        if len(out) >= 20:
            break
    return out


def run_static_content_checks(
    artifact: CodeArtifact,
    idea: str = "",
) -> tuple[bool, str]:
    """Lightweight pass/fail without Selenium/Jest: scan HTML/CSS/JS bodies."""
    bodies: list[str] = []
    for path, code in (artifact.files or {}).items():
        pl = path.lower()
        if pl.endswith((".html", ".htm", ".css", ".js", ".tsx", ".jsx", ".ts")):
            bodies.append(code or "")
    blob = "\n".join(bodies)
    if not blob.strip():
        return False, "STATIC CHECK FAIL: no HTML/CSS/JS content in artifact."

    issues: list[str] = []
    # Invented wrong-city map heuristic
    if "empire state" in blob.lower() or (
        "maps/embed" in blob.lower()
        and "honduras" not in blob.lower()
        and "san pedro" not in blob.lower()
        and "trejo" not in blob.lower()
        and not re.search(r"maps\.google\.[^\"']+q=", blob, re.I)
    ):
        # Only flag classic NYC embed fingerprint
        if "-73.98" in blob or "40.748" in blob or "empire" in blob.lower():
            issues.append(
                "Map embed looks like a wrong-city placeholder (e.g. NYC). "
                "Use verified address text or a maps search URL from research."
            )

    must = _idea_must_strings(idea)
    missing = [s for s in must if s.lower() not in blob.lower()]
    # Soft: only require if we found brand signals in idea
    if must:
        # Require at least half of grounded strings when many, else all
        need = max(1, (len(must) + 1) // 2) if len(must) > 4 else len(must)
        found = len(must) - len(missing)
        if found < need:
            issues.append(
                f"Missing grounded brand/contact strings in site content "
                f"({found}/{len(must)} present). Missing examples: "
                + ", ".join(missing[:8])
            )

    # Fake image placeholders that are not real assets
    for path, code in (artifact.files or {}).items():
        pl = path.lower()
        if pl.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            # Binary files as text content are a smell if very short and ascii
            if code and len(code) < 200 and code.isascii() and "PNG" not in code[:20]:
                issues.append(
                    f"Suspicious non-binary image file {path!r} — use remote "
                    "logo URL from research or inline SVG, not a text stub."
                )

    if issues:
        log = "STATIC CONTENT CHECKS FAILED\n" + "\n".join(f"- {i}" for i in issues)
        return False, log
    log = (
        "STATIC CONTENT CHECKS PASSED\n"
        f"- Scanned {len(bodies)} front-end file(s)\n"
        f"- Grounded strings checked: {len(must)}\n"
    )
    return True, log


def _pytest_python_candidates(repo_root: Path) -> list[str]:
    """Prefer repo venv, then the running interpreter (usually MultiAgent venv)."""
    import sys

    cands: list[str] = []
    for p in (
        repo_root / "venv" / "bin" / "python",
        repo_root / ".venv" / "bin" / "python",
        # Install root may differ from git worktree cwd in rare layouts
        Path(__file__).resolve().parents[2] / "venv" / "bin" / "python",
    ):
        if p.is_file():
            cands.append(str(p))
    if sys.executable:
        cands.append(sys.executable)
    # de-dupe preserve order
    out: list[str] = []
    seen: set[str] = set()
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def run_pytest_on_targets(
    targets: list[str],
    *,
    repo_root: Path,
    timeout: int = 45,
) -> tuple[int, str]:
    """Run pytest on *targets* only. Returns (exit_code, combined_log)."""
    if not targets:
        return 0, "No pytest targets selected (skipped monorepo tests/).\n"

    last_err = ""
    for py in _pytest_python_candidates(repo_root):
        cmd = [py, "-m", "pytest", *targets, "-v", "--tb=short"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(repo_root),
            )
            log = (
                f"CMD: {' '.join(cmd)}\n"
                f"EXIT: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
            )
            return result.returncode, log
        except subprocess.TimeoutExpired as exc:
            return 124, f"pytest timed out after {timeout}s: {exc}"
        except FileNotFoundError as exc:
            last_err = str(exc)
            continue
        except Exception as exc:
            return 1, f"pytest execution error: {exc}"

    # Last resort: bare pytest on PATH
    try:
        cmd = ["pytest", *targets, "-v", "--tb=short"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(repo_root),
        )
        log = (
            f"CMD: {' '.join(cmd)}\n"
            f"EXIT: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        )
        return result.returncode, log
    except FileNotFoundError:
        return 127, f"pytest not found in environment. ({last_err})"
    except Exception as exc:
        return 1, f"pytest execution error: {exc}"


def execute_vibe_tests(
    *,
    spec: TechnicalSpec,
    artifact: Optional[CodeArtifact],
    idea: str,
    repo_root: Path,
) -> str:
    """Full test strategy for a vibe run; returns logs for the Debugger."""
    parts: list[str] = []
    overall_ok = True

    if artifact and artifact_looks_like_node_project(artifact):
        parts.append(
            "NODE/JEST PROJECT DETECTED\n"
            "- This environment's Test Executor runs pytest only.\n"
            "- Next.js / React / Jest / npm test are NOT executed here.\n"
            "- Prefer static HTML/CSS/JS + pytest file checks for marketing sites\n"
            "  unless the user explicitly required a Node stack and local npm.\n"
            "RESULT: FAIL (stack mismatch with test runtime)\n"
        )
        overall_ok = False

    targets = select_pytest_targets(
        files_to_create=list(spec.files_to_create or []),
        artifact=artifact,
        repo_root=repo_root,
    )
    if targets:
        code, log = run_pytest_on_targets(targets, repo_root=repo_root)
        parts.append(log)
        if code != 0:
            overall_ok = False
    else:
        parts.append(
            "No project-local pytest files in the artifact "
            "(did not run monorepo tests/).\n"
        )

    if artifact and (
        artifact_is_static_site(artifact)
        or (not targets and not artifact_looks_like_node_project(artifact))
    ):
        # Always content-check static sites; also when there are no pytest files
        # and the artifact is mostly front-end text files
        ok, slog = run_static_content_checks(artifact, idea)
        parts.append(slog)
        if not ok:
            overall_ok = False
    elif artifact and not targets and not artifact_looks_like_node_project(artifact):
        # Generic: if no tests at all, pass with warning only if files exist
        if artifact.files:
            parts.append(
                "WARNING: no runnable tests for this artifact. "
                "Debugger should treat as incomplete unless static checks apply.\n"
            )
            # Don't hard-fail pure library code with no tests — leave to debugger
        else:
            overall_ok = False
            parts.append("FAIL: empty artifact.\n")

    header = "OVERALL: PASS\n" if overall_ok else "OVERALL: FAIL\n"
    return header + "\n".join(parts)
