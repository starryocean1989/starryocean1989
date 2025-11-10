import importlib.util
import logging
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAZY_LOGGER_PATH = PROJECT_ROOT / "backend" / "infrastructure" / "system_vnpy" / "lazy_logger.py"

spec = importlib.util.spec_from_file_location("lazy_logger_test_module", LAZY_LOGGER_PATH)
if spec is None or spec.loader is None:  # pragma: no cover - defensive
    raise RuntimeError("Unable to load lazy_logger module for tests")
lazy_logger = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lazy_logger
spec.loader.exec_module(lazy_logger)


@pytest.fixture(autouse=True)
def _reset_lazy_logger():
    lazy_logger.reset_lazy_logging()
    yield
    lazy_logger.reset_lazy_logging()


def test_lazy_logger_initialize_basic():
    lazy_instance = lazy_logger.get_lazy_logger("tests.lazy.basic")
    logger = lazy_instance.get_logger()
    logger.info("message before initialization")

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    results = lazy_logger.initialize_lazy_logging({"level": logging.INFO}, handlers=[handler])

    print("sync results:", results)
    print("is_initialized:", lazy_instance.is_initialized())
    assert results.get("tests.lazy.basic") is True
    assert lazy_instance.is_initialized() is True


def test_lazy_logger_async_init():
    import asyncio

    lazy_instance = lazy_logger.get_lazy_logger("tests.lazy.async")
    logger = lazy_instance.get_logger()
    logger.warning("pre-init warning")

    async def _run():
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        return await lazy_logger.async_initialize_lazy_logging({"level": logging.DEBUG}, handlers=[handler])

    init_results = asyncio.run(_run())

    print("async results:", init_results)
    print("async is_initialized:", lazy_instance.is_initialized())
    assert init_results.get("tests.lazy.async") is True
    assert lazy_instance.is_initialized() is True
