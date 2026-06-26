from __future__ import annotations

from conftest import PLUGIN_ROOT


def test_plugin_does_not_mention_deprecated_deduplication_fields():
    checked_suffixes = {".md", ".py", ".yaml", ".json"}
    deprecated_camel = "idempotency" + "Key"
    deprecated_snake = "idempotency" + "_key"
    offenders: list[str] = []
    for path in PLUGIN_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in checked_suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        if deprecated_camel in text or deprecated_snake in text:
            offenders.append(str(path.relative_to(PLUGIN_ROOT)))

    assert offenders == []
