"""Keep the suite hermetic: tests must never write into the developer's data."""

import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    # Playback tests exercise the real player, which logs listening history on
    # success. Without this override those entries land in <checkout>/logs or
    # ~/.local/share and pollute real user history.
    monkeypatch.setenv("KIOSKTUNES_DATA_DIR", str(tmp_path / "data"))
