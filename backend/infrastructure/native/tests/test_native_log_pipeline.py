# -*- coding: utf-8 -*-
import pytest

native_log_pipeline = pytest.importorskip("native_log_pipeline")


def test_pipeline_batch_and_repeat_merging():
    captured = []

    def fallback(batch):
        captured.extend(list(batch))

    pipeline = native_log_pipeline.install(batch_size=2, flush_ms=0, fallback=fallback)

    try:
        assert pipeline.push({"message": "boot", "level": "INFO"}) is False
        assert pipeline.push({"message": "boot", "level": "INFO"}) in {False, True}
        pipeline.flush(force=True)

        assert captured, "fallback should receive merged batch"
        entry = captured[0]
        assert entry["_repeat"] == 2

        stats = pipeline.stats()
        assert stats["total_pushed"] >= 2
        assert stats["total_flushed"] >= 1
    finally:
        native_log_pipeline.flush_and_close(pipeline)

