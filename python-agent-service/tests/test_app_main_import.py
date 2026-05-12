import importlib


def test_app_main_importable():
    module = importlib.import_module("app.main")
    assert getattr(module, "app", None) is not None

