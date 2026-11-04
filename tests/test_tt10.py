from datetime import datetime
import pytest
from qtlink import tt10

T = datetime(2026, 11, 4, 18, 35, 0)

def test_file_name():
    assert tt10.file_name("BN", "GULB", "NUOXA1", T) == "BN_GULB_NUOXA1_20261104183500.txt"

def test_content_tab_5_columns():
    recs = [tt10.Record("pH", 7.354, "-", T), tt10.Record("COD", 45.2, "mg/L", T, "01"),
            tt10.Record("TSS", None, "mg/L", T, "02")]
    txt = tt10.build_content(recs)
    lines = txt.split("\r\n")
    assert lines[0] == "pH\t7.35\t-\t20261104183500\t00"
    assert lines[1] == "COD\t45.20\tmg/L\t20261104183500\t01"
    assert lines[2].endswith("\t02")
    assert all(len(l.split("\t")) == 5 for l in lines if l)
    assert [r.parameter for r in tt10.parse_content(txt)] == ["pH", "COD", "TSS"]

def test_param_with_space_allowed():
    assert tt10.build_content([tt10.Record("Flow out 1", 1, "m3/h", T)], newline="\n") == "Flow out 1\t1.00\tm3/h\t20261104183500\t00\n"

def test_invalid_status():
    with pytest.raises(ValueError):
        tt10.build_content([tt10.Record("pH", 7, "-", T, "04")])

def test_remote_dir():
    assert tt10.remote_dir("", "NUOXA1", T) == "/NUOXA1/2026/11/04"
    assert tt10.remote_dir("/data/", "NUOXA1", T) == "/data/NUOXA1/2026/11/04"

def test_validate_ids():
    assert tt10.validate_ids("BN", "GULB", "NUOXA1") == []
    w = tt10.validate_ids("XX", "Gò Vấp", "ABC")
    assert len(w) >= 3
