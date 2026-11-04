"""Guard against ``t("project.<key>")`` usages missing from some locale.

``Project.tsx`` renders strings through ``t("project.<key>")``; the four
locale objects in ``frontend/src/i18n/translations.ts`` must each define
every one of those keys.  A key missing from one locale silently falls back
(or renders the raw key), which is how this bug has shipped twice.

The check is pure Python regex/brace-scanning: no JS tooling required.
Pre-existing duplicate keys in ``translations.ts`` are tolerated (the file
already has TS1117 errors); only *missing* keys fail.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROJECT_TSX = ROOT / "frontend" / "src" / "pages" / "Project.tsx"
TRANSLATIONS_TS = ROOT / "frontend" / "src" / "i18n" / "translations.ts"

LOCALES = ("en", "es", "de", "pt")

# ``Project.tsx`` never builds these keys dynamically; verified by searching
# for template literals / concatenation (``t(`project.${...}`)`` etc.).
DYNAMIC_KEY_ALLOWLIST: set[str] = set()

USED_KEY_RE = re.compile(r"""t\(\s*["']project\.([A-Za-z0-9_]+)["']""")
LOCALE_DECL_RE = re.compile(r"const (en|es|de|pt): Translations = \{")
PROJECT_BLOCK_RE = re.compile(r"^ {2}project: \{", re.MULTILINE)
PROJECT_KEY_RE = re.compile(r"^ {4}([A-Za-z0-9_]+)\s*:", re.MULTILINE)
STATUS_VALUE_RE = re.compile(
    r'^ {4}statusInProgress:\s*(?:"([^"]*)"|\'([^\']*)\')', re.MULTILINE
)


def _read(path: Path) -> str:
    assert path.is_file(), f"expected source file at {path}"
    return path.read_text(encoding="utf-8")


def _matching_brace(src: str, open_index: int) -> int:
    """Return the index of the ``}`` matching ``src[open_index] == "{"``.

    String literals (single, double and template quotes) are skipped so
    braces or quotes embedded in translated text do not corrupt the scan.
    """
    assert src[open_index] == "{", f"expected '{{' at {open_index}"
    depth = 0
    quote: str | None = None
    i = open_index
    while i < len(src):
        ch = src[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise AssertionError(f"unbalanced braces starting at {open_index}")


def _locale_blocks(src: str) -> dict[str, str]:
    """Split the source into one segment per ``const <locale>: Translations``."""
    matches = list(LOCALE_DECL_RE.finditer(src))
    assert len(matches) == len(LOCALES), (
        f"expected {len(LOCALES)} locale declarations, found {len(matches)}"
    )
    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(src)
        blocks[match.group(1)] = src[match.start() : end]
    return blocks


def _project_blocks(src: str) -> dict[str, str]:
    """Extract the text of the ``project: { ... }`` sub-object per locale."""
    result: dict[str, str] = {}
    for locale, block in _locale_blocks(src).items():
        match = PROJECT_BLOCK_RE.search(block)
        assert match, f"no `project: {{` block in locale {locale!r}"
        open_index = match.end() - 1
        close_index = _matching_brace(block, open_index)
        result[locale] = block[open_index : close_index + 1]
    return result


def project_keys_by_locale() -> dict[str, set[str]]:
    src = _read(TRANSLATIONS_TS)
    return {
        locale: set(PROJECT_KEY_RE.findall(block))
        for locale, block in _project_blocks(src).items()
    }


def used_project_keys() -> set[str]:
    src = _read(PROJECT_TSX)
    return set(USED_KEY_RE.findall(src))


def status_in_progress_value(locale: str) -> str | None:
    block = _project_blocks(_read(TRANSLATIONS_TS))[locale]
    match = STATUS_VALUE_RE.search(block)
    if not match:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def test_project_i18n_keys_exist_in_all_locales():
    """Every key used by ``Project.tsx`` exists in en, es, de and pt."""
    used = used_project_keys() - DYNAMIC_KEY_ALLOWLIST
    assert used, "parser found no t('project.*') usages - regex is broken"

    keys_by_locale = project_keys_by_locale()
    missing: dict[str, list[str]] = {}
    for key in sorted(used):
        absent = [locale for locale in LOCALES if key not in keys_by_locale[locale]]
        if absent:
            missing[key] = absent

    detail = ", ".join(f"{key} -> {locales}" for key, locales in missing.items())

    assert not missing, f"keys missing from locale(s): {detail}"


def test_status_in_progress_key_present():
    """The recently added ``statusInProgress`` badge exists everywhere."""
    keys_by_locale = project_keys_by_locale()
    for locale in LOCALES:
        assert "statusInProgress" in keys_by_locale[locale], (
            f"statusInProgress missing from locale {locale!r}"
        )

        value = status_in_progress_value(locale)
        assert value is not None, (
            f"could not parse statusInProgress value for {locale!r}"
        )
        assert value.strip(), f"statusInProgress is empty for locale {locale!r}"


def test_locales_have_same_project_keys():
    """The four locales define exactly the same set of project keys."""
    keys_by_locale = project_keys_by_locale()
    reference = keys_by_locale["en"]

    drift: dict[str, set[str]] = {}
    for locale in LOCALES[1:]:
        symmetric = reference ^ keys_by_locale[locale]
        if symmetric:
            drift[locale] = symmetric

    detail = "; ".join(
        f"en vs {locale}: {sorted(keys)}" for locale, keys in drift.items()
    )

    assert not drift, f"project key drift between locales -> {detail}"


def test_parse_found_enough_keys():
    """Sanity guard: a broken parser must fail loudly, not pass vacuously."""
    keys_by_locale = project_keys_by_locale()
    for locale in LOCALES:
        assert len(keys_by_locale[locale]) >= 20, (
            f"only {len(keys_by_locale[locale])} project keys parsed for "
            f"locale {locale!r} - parser or source layout changed"
        )

    used = used_project_keys()
    assert len(used) >= 10, (
        f"only {len(used)} t('project.*') usages found in Project.tsx - "
        "regex or call style changed"
    )
