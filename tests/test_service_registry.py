# -*- coding: utf-8 -*-
"""ServiceRegistry 单元测试."""

import pytest

from backend.startup.service_registry import (
    ServiceRegistry,
    ServiceRegistrationError,
    ServiceResolutionError,
)
from backend.startup.context import StartupContext


class _Counter:
    def __init__(self):
        self.count = 0

    def inc(self):
        self.count += 1
        return self.count


def test_register_instance_and_resolve():
    registry = ServiceRegistry()
    sentinel = object()
    registry.register_instance("sentinel", sentinel)

    resolved = registry.resolve("sentinel")
    assert resolved is sentinel


def test_register_factory_singleton_scope():
    registry = ServiceRegistry()
    counter = _Counter()

    def factory():
        counter.inc()
        return object()

    registry.register_factory("singleton", factory, scope="singleton")

    first = registry.resolve("singleton")
    second = registry.resolve("singleton")
    assert first is second
    # 工厂仅被调用一次
    assert counter.count == 1


def test_register_factory_transient_scope():
    registry = ServiceRegistry()

    registry.register_factory("transient", object, scope="transient")

    values = {registry.resolve("transient") for _ in range(3)}
    # 三次解析得到三个不同实例
    assert len(values) == 3


def test_register_alias():
    registry = ServiceRegistry()
    sentinel = object()
    registry.register_instance("original", sentinel)
    registry.register_alias("alias", "original")

    assert registry.resolve("alias") is sentinel


def test_register_factory_duplicate_without_replace():
    registry = ServiceRegistry()
    registry.register_factory("dup", object)

    with pytest.raises(ServiceRegistrationError):
        registry.register_factory("dup", object)


def test_resolve_missing_service_raises():
    registry = ServiceRegistry()
    with pytest.raises(ServiceResolutionError):
        registry.resolve("missing")


@pytest.mark.parametrize("replace", [True, False])
def test_replace_binding_behavior(replace):
    registry = ServiceRegistry()
    registry.register_instance("svc", object())

    if replace:
        registry.register_instance("svc", object(), replace=True)
        assert registry.resolve("svc") is registry.resolve("svc")
    else:
        with pytest.raises(ServiceRegistrationError):
            registry.register_instance("svc", object())


def test_startup_context_installs_default_bindings():
    context = StartupContext()

    # 默认绑定只需存在即可，不立即解析以避免昂贵初始化
    expected = {
        "data_center_service",
        "trading_gateway_service",
        "strategy_center_service",
        "portfolio_service",
        "market_board_service",
        "system_manager_service",
        "ai_assistant_service",
    }

    for name in expected:
        assert context.service_registry.has_binding(name), f"默认绑定缺失: {name}"


def test_service_manager_backfills_after_registry_resolve():
    registry = ServiceRegistry()
    sentinel = object()
    registry.register_instance("svc", sentinel)

    context = StartupContext()
    context.service_registry = registry
    context.service_manager.services.clear()

    assert context.get_service("svc") is sentinel
    # 调用 get_service 后应自动回填到老的 ServiceManager
    assert context.service_manager.get_service("svc") is sentinel
