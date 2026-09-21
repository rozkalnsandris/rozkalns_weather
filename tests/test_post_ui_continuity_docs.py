from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DOCS = (
    ROOT / "README.md",
    ROOT / "docs" / "ROADMAP.md",
    ROOT / "docs" / "IMPLEMENTATION_STATUS.md",
    ROOT / "docs" / "RPI5_PUBLIC_RUNTIME_HANDOFF.md",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_current_docs_pin_05480_and_fixed_common_window() -> None:
    for path in CANONICAL_DOCS:
        text = _text(path)
        assert "station_05480" in text, path
        assert "2026-08-13..2026-08-26" in text, path
        assert "SIMPLE-DEPLOY" in text, path


def test_10416_and_old_window_are_only_legacy_or_historical() -> None:
    allowed_markers = ("legacy", "histor", "old", "stale", "migrat")
    for path in CANONICAL_DOCS:
        for line in _text(path).splitlines():
            lowered = line.lower()
            if "station_10416" in line:
                assert any(marker in lowered for marker in allowed_markers), (path, line)
            if "2026-04-02..2026-09-10" in line:
                assert any(marker in lowered for marker in ("histor", "old")), (path, line)


def test_stale_pre_cutover_claims_do_not_return() -> None:
    joined = "\n".join(_text(path) for path in CANONICAL_DOCS)
    forbidden = (
        "target `rozkalns-weather-public-rpi5` remains inactive",
        "canary adoption in progress; host cutover is not active",
        "one-time rpi5 install/target activation remains a separate exact live cutover",
        "production corpus bootstrap/backfill and recurring public ingest remain separate data/host operations",
    )
    lowered = joined.lower()
    for phrase in forbidden:
        assert phrase not in lowered


def test_post_ui_milestones_and_weathernext_sequence_are_explicit() -> None:
    readme = _text(ROOT / "README.md")
    roadmap = _text(ROOT / "docs" / "ROADMAP.md")
    status = _text(ROOT / "docs" / "IMPLEMENTATION_STATUS.md")
    handoff = _text(ROOT / "docs" / "RPI5_PUBLIC_RUNTIME_HANDOFF.md")

    assert "#136" in readme and "pabeigts" in readme
    assert "#146" in roadmap and "[x]" in roadmap
    assert "#148" in status and "completed" in status
    assert "recurring public ingest" in handoff.lower()

    for text in (readme, roadmap, status, handoff):
        assert "#168" in text
        assert "#122" in text
        assert text.index("#168") < text.index("#122")
