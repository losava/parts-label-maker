"""CSV lookup, updates, and printer-path behavior. No printer required."""

import csv
import os
import sys

import pytest

import make_parts_label as eng


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_sources_compile():
    import py_compile
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in (
        "parts_label_app.py",
        "make_parts_label.py",
        "version.py",
        "updater.py",
    ):
        py_compile.compile(str(root / name), doraise=True)


def test_normalize_part_number_strips_invisible_and_fancy_dashes():
    raw = "ab\u2013c\u200b\ufeff 12"
    assert eng.normalize_part_number(raw) == "AB-C 12"
    assert eng.normalize_part_number("  demo-1001  ") == "DEMO-1001"


def test_parse_header_or_price_examples():
    assert eng.parse_header_or_price("$12.99") == ("", "$12.99")
    assert eng.parse_header_or_price("12.99") == ("", "$12.99")
    assert eng.parse_header_or_price("Amazon $12") == ("Amazon", "$12.00")
    assert eng.parse_header_or_price("Shop Stock $4.5") == ("Shop Stock", "$4.50")
    assert eng.parse_header_or_price("PARTS LABEL") == ("PARTS LABEL", "")
    assert eng.parse_header_or_price("") == ("", "")


def test_wrap_text_lines_breaks_long_words():
    assert eng.wrap_text_lines("AIR FILTER PRIMARY", 10) == ["AIR FILTER", "PRIMARY"]
    assert eng.wrap_text_lines("ABCDEFGHIJ", 4) == ["ABCD", "EFGH", "IJ"]
    assert eng.wrap_text_lines("  ", 10) == []


def test_load_clean_csv_columns(isolated_user_data):
    _data, search = isolated_user_data
    _write(
        search / "parts_list_clean.csv",
        "PartNo,Description,Price,Header\n"
        "DEMO-1001,AIR FILTER - PRIMARY,$45.00,SHELF A\n"
        "demo-1002,OIL FILTER,12.50,SHELF B\n",
    )
    lookup = eng.load_parts_lookup()
    assert set(lookup) == {"DEMO-1001", "DEMO-1002"}
    assert lookup["DEMO-1001"]["description"] == "AIR FILTER - PRIMARY"
    assert lookup["DEMO-1001"]["price"] == "$45.00"
    assert lookup["DEMO-1001"]["header"] == "SHELF A"
    assert lookup["DEMO-1002"]["price"] == "12.50"
    # Finding the shop file remembers it so a later install keeps the same path.
    assert eng.configured_parts_csv() == os.path.abspath(search / "parts_list_clean.csv")


def test_load_legacy_par_format(isolated_user_data):
    _data, search = isolated_user_data
    _write(
        search / "FULL PARTS LIST",
        'PAR:PartNo,PAR:Description\n"abc-9","WIDGET CLAMP"\n',
    )
    lookup = eng.load_parts_lookup()
    assert lookup["ABC-9"]["description"] == "WIDGET CLAMP"
    assert lookup["ABC-9"]["price"] == ""
    # The legacy export is not remembered, and updates still target the clean csv.
    assert eng.configured_parts_csv() == ""
    assert os.path.basename(eng.get_clean_csv_path()) == "parts_list_clean.csv"
    assert eng.get_clean_csv_path().startswith(str(search))


def test_missing_remembered_file_does_not_switch(isolated_user_data):
    _data, search = isolated_user_data
    _write(
        search / "parts_list_clean.csv",
        "PartNo,Description,Price,Header\nOTHER,SPARE,$1.00,BIN\n",
    )
    missing = search / "gone" / "parts_list_clean.csv"
    eng.set_parts_csv(str(missing))
    assert eng.find_parts_csv() is None
    assert eng.load_parts_lookup() == {}
    assert eng.get_clean_csv_path() == os.path.abspath(missing)


def test_explicit_choice_beats_a_nearby_file(isolated_user_data):
    _data, search = isolated_user_data
    nearby = _write(
        search / "parts_list_clean.csv",
        "PartNo,Description,Price,Header\nNEAR,NEAR PART,$1.00,A\n",
    )
    chosen = _write(
        search / "shop" / "parts_list_clean.csv",
        "PartNo,Description,Price,Header\nSHOP,SHOP PART,$2.00,B\n",
    )
    eng.set_parts_csv(str(chosen))
    found = eng.find_parts_csv()
    assert found == os.path.abspath(chosen)
    assert os.path.basename(nearby) == "parts_list_clean.csv"


def test_update_adds_and_edits_without_dropping_rows(isolated_user_data):
    _data, search = isolated_user_data
    path = search / "parts_list_clean.csv"
    _write(
        path,
        "PartNo,Description,Price,Header\n"
        "DEMO-1001,AIR FILTER - PRIMARY,$45.00,SHELF A\n"
        "DEMO-1002,OIL FILTER,$12.50,SHELF B\n",
    )
    lookup = eng.load_parts_lookup()
    eng.update_parts_list(
        "DEMO-1001", "AIR FILTER - PRIMARY", lookup, price="$45.00", header="SHELF A"
    )
    # Unchanged rows are left alone.
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["PartNo"] for row in rows] == ["DEMO-1001", "DEMO-1002"]

    eng.update_parts_list(
        "DEMO-1002", "OIL FILTER ELEMENT", lookup, price="$13.00", header="SHELF B"
    )
    eng.update_parts_list(
        "DEMO-2044", "HYDRAULIC HOSE 1/2 IN", lookup, price="28", header="BIN 3"
    )
    lookup = eng.load_parts_lookup()
    assert lookup["DEMO-1002"]["description"] == "OIL FILTER ELEMENT"
    assert lookup["DEMO-1002"]["price"] == "$13.00"
    assert lookup["DEMO-2044"]["price"] == "$28.00"
    assert lookup["DEMO-2044"]["header"] == "BIN 3"
    assert lookup["DEMO-1001"]["description"] == "AIR FILTER - PRIMARY"
    with path.open(encoding="utf-8", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert [row["PartNo"] for row in written] == ["DEMO-1001", "DEMO-1002", "DEMO-2044"]


def test_sample_csv_is_demo_data_only():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sample = os.path.join(root, "parts_list_sample.csv")
    with open(sample, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(row["PartNo"].startswith("DEMO-") for row in rows)
    assert {row["PartNo"] for row in rows} >= {"DEMO-1001", "DEMO-1002", "DEMO-2044"}


def test_printer_choice_is_stored_in_user_data(isolated_user_data):
    data, search = isolated_user_data
    eng.save_printer_choice("ZDesigner GC420d (EPL)")
    assert eng.read_saved_printer() == "ZDesigner GC420d (EPL)"
    assert (data / "settings.json").is_file()
    assert (data / "printer_name.txt").read_text(encoding="utf-8") == "ZDesigner GC420d (EPL)"
    # Running from the scripts still mirrors the old file beside them.
    assert (search / "printer_name.txt").read_text(encoding="utf-8") == "ZDesigner GC420d (EPL)"
    names = ["Office Laser", "ZDesigner GC420d (EPL)"]
    assert eng.pick_default_printer(names) == "ZDesigner GC420d (EPL)"


def test_legacy_printer_file_is_read_when_settings_are_empty(isolated_user_data):
    _data, search = isolated_user_data
    (search / "printer_name.txt").write_text("Shop Zebra\n", encoding="utf-8")
    assert eng.read_saved_printer() == "Shop Zebra"
    assert eng.pick_default_printer(["Other"]) == "Shop Zebra"


def test_linux_default_does_not_invent_a_queue(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert eng.pick_default_printer(["Label-Raw"]) == "Label-Raw"
    assert eng.pick_default_printer(["office", "Zebra-GC420d"]) == "Zebra-GC420d"


def test_lpstat_parser():
    text = "\n".join([
        "printer GC420d is idle.  enabled since Mon",
        "printer Office_Laser disabled since Tue",
        "not a printer line",
    ])
    assert eng._parse_lpstat_printers(text) == ["GC420d", "Office_Laser"]


def test_list_printers_returns_a_list():
    names = eng.list_printers()
    assert isinstance(names, list)


def test_send_raw_without_a_real_printer_returns_false():
    if sys.platform.startswith("win"):
        pytest.skip("CUPS raw-print fallback is the Linux path")
    ok = eng.send_raw_to_printer(b"^XA^XZ", "DefinitelyNotARealPrinter")
    assert ok is False
    assert eng.send_raw_to_printer(b"^XA^XZ", "") is False


def test_build_zpl_contains_part_and_copies():
    zpl = eng.build_zpl("DEMO-1001", "AIR FILTER - PRIMARY", "SHELF A", "$45.00", copies=2)
    assert zpl.startswith("^XA")
    assert "DEMO-1001" in zpl
    assert "SHELF A" in zpl
    assert "$45.00" in zpl
    assert "^PQ2" in zpl
    assert zpl.strip().endswith("^XZ")


def test_make_one_label_writes_pdf_without_printing(isolated_user_data):
    _data, search = isolated_user_data
    path = eng.make_one_label(
        "DEMO-1001",
        "AIR FILTER - PRIMARY",
        "SHELF A $45.00",
        auto_print=False,
    )
    assert os.path.isfile(path)
    assert path.endswith(".pdf")
    assert os.path.basename(os.path.dirname(path)) == "Parts List"
    assert path.startswith(str(search))


def test_startup_update_setting_roundtrip():
    assert eng.updates_on_startup() is True
    eng.set_updates_on_startup(False)
    assert eng.updates_on_startup() is False
    eng.set_skipped_version("v9.9.9")
    assert eng.skipped_version() == "v9.9.9"


def test_app_version_matches_version_module():
    import version

    assert eng.app_version() == version.__version__ == "1.0.0"
