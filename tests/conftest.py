"""Keep tests off the real parts list and the developer settings folder."""

import pytest


@pytest.fixture(autouse=True)
def isolated_user_data(tmp_path, monkeypatch):
    data = tmp_path / "data"
    search = tmp_path / "search"
    data.mkdir()
    search.mkdir()
    monkeypatch.setenv("PARTS_LABEL_DATA_DIR", str(data))
    monkeypatch.setenv("PARTS_LABEL_SEARCH_DIR", str(search))
    return data, search
