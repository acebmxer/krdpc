import os

import pytest

# Tests draw windows without a screen; set before Qt loads.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    from krdpc.store import ProfileStore

    return ProfileStore(tmp_path / "krdpc")
