# -*- coding: utf-8 -*-
import pytest

native_rpc_bridge = pytest.importorskip("native_rpc_bridge")


def test_create_request_header_returns_dict():
    header = native_rpc_bridge.create_request_header(42, 128)
    assert header["method_id"] == 42
    assert header["payload_size"] == 128
    assert isinstance(header["request_id"], int)
    assert header["flags"] == 0


def test_serialize_request_preserves_payload_reference():
    payload = {"symbol": "000001", "action": "query"}
    serialized = native_rpc_bridge.serialize_request(7, payload)
    assert serialized["method_id"] == 7
    assert serialized["payload"] is payload

