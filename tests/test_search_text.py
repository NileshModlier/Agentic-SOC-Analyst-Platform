"""Full-text folding does not need PostgreSQL."""

from soc_platform.search.text import fts_document, prepare_fts_query


def test_identifiers_fold_to_the_same_token_as_the_query() -> None:
    document = fts_document(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "10.0.0.8")
    assert "powershellexe" in document.split()
    assert "10008" in document.split()
    assert prepare_fts_query("powershell.exe") == "powershellexe"
    assert prepare_fts_query("10.0.0.8") == "10008"
    assert prepare_fts_query("encoded powershell") == "encoded powershell"


def test_punctuation_only_query_matches_nothing() -> None:
    assert prepare_fts_query("...") == ""
    assert prepare_fts_query("   ") == ""
