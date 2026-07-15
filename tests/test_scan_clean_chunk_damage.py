"""Tests for the pre-generation clean-chunk damage scan.

Damaged chunks used to be caught only downstream -- an empty chunk as a per-book
contract error, a word-dropped chunk (pte_chunk_053) as a per-chapter
SOURCE_DAMAGED verdict, and that only by luck. The scan surfaces both up front.
"""

import json

import pytest

import scan_clean_chunk_damage as scan


def chunk(node_id, text):
    return {"id": node_id, "text": text}


def test_empty_chunk_is_reported_and_fails_the_scan():
    result = scan.scan_chunks([chunk("c1", "Real text here."), chunk("c2", "   ")])

    assert result["empty_count"] == 1
    assert result["empty"][0]["node_id"] == "c2"
    assert result["suspected_gap_count"] == 0


def test_missing_text_counts_as_empty():
    result = scan.scan_chunks([{"id": "c1"}])
    assert result["empty_count"] == 1


def test_word_drop_signature_is_flagged():
    # The pte_chunk_053 shape: a number dropped, leaving two spaces between words.
    result = scan.scan_chunks(
        [chunk("c1", "a reading text with  to five blanks in it")]
    )

    assert result["suspected_gap_count"] == 1
    found = result["suspected_gap"][0]
    assert found["node_id"] == "c1"
    assert found["gap_count"] >= 1
    assert any("with" in ex for ex in found["examples"])


def test_clean_text_is_not_flagged():
    result = scan.scan_chunks(
        [chunk("c1", "This item type has a reading text with three to five blanks.")]
    )

    assert result["empty_count"] == 0
    assert result["suspected_gap_count"] == 0


def test_single_spaced_prose_never_trips_the_gap_signal():
    # A normal sentence with ordinary single spacing must stay clean.
    result = scan.scan_chunks(
        [chunk("c1", "The box contains six to eight words so you have extra options.")]
    )
    assert result["suspected_gap_count"] == 0


def test_gap_between_long_words_is_ignored():
    # The signal targets short function-word joins; a wide gap between long words
    # (e.g. a column break) is not the dropped-content fingerprint.
    result = scan.scan_chunks(
        [chunk("c1", "comprehension  understanding are assessed")]
    )
    assert result["suspected_gap_count"] == 0


# --------------------------------------------------------------------------- #
# Exit code: definitive damage fails, heuristic gaps do not.
# --------------------------------------------------------------------------- #

def test_exit_nonzero_only_when_empty_chunks_exist(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps([chunk("c1", "Clean prose with three to five blanks.")]))
    assert scan.main(["--clean-chunks-file", str(good)]) == 0

    gaps_only = tmp_path / "gaps.json"
    gaps_only.write_text(json.dumps([chunk("c1", "text with  to five blanks")]))
    # A heuristic gap alone must not fail the scan -- it is advisory.
    assert scan.main(["--clean-chunks-file", str(gaps_only)]) == 0

    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps([chunk("c1", "  ")]))
    assert scan.main(["--clean-chunks-file", str(empty)]) == 1


def test_report_and_json_outputs_are_written(tmp_path):
    src = tmp_path / "chunks.json"
    src.write_text(json.dumps([chunk("c1", "text with  to five blanks"), chunk("c2", "")]))
    report = tmp_path / "report.txt"
    js = tmp_path / "out.json"

    scan.main(
        [
            "--clean-chunks-file", str(src),
            "--report", str(report),
            "--json-out", str(js),
        ]
    )

    assert "CLEAN CHUNK DAMAGE SCAN" in report.read_text()
    data = json.loads(js.read_text())
    assert data["empty_count"] == 1
    assert data["suspected_gap_count"] == 1


def test_scan_catches_both_known_defects_in_the_real_pte_index():
    # Guards the two chunks that actually bit us: an empty one and a word-dropped
    # one. Skips cleanly if the (gitignored) prepared index is not present.
    from pathlib import Path

    index = Path("extracted/pte.section_clean_chunks.json")
    if not index.exists():
        pytest.skip("prepared PTE index not present")

    chunks = scan.load_clean_chunk_collection(index)
    result = scan.scan_chunks(chunks)

    empty_ids = {item["node_id"] for item in result["empty"]}
    gap_ids = {item["node_id"] for item in result["suspected_gap"]}
    assert "pte_chunk_249" in empty_ids
    assert "pte_chunk_053" in gap_ids
