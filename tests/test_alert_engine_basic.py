import pytest
from backend.services.alert_engine import AlertEngine

def test_alert_engine_basic():
    """测试基础告警功能"""
    # 初始化告警引擎
    engine = AlertEngine()
    
    # 设置告警规则
    rules = [
        {"id": "alert1", "field": "price", "op": ">", "value": 100},
        {"id": "alert2", "field": "volume", "op": "<", "value": 50}
    ]
    engine.set_rules(rules)
    
    # 测试数据
    records = [
        {"symbol": "000001.SZ", "price": 99, "volume": 30, "datetime": "2023-01-01 09:30:00"},
        {"symbol": "000002.SZ", "price": 101, "volume": 60, "datetime": "2023-01-01 09:31:00"},
        {"symbol": "000003.SZ", "price": 102, "volume": 40, "datetime": "2023-01-01 09:32:00"}
    ]
    
    # 执行告警检测
    alerts = engine.evaluate(records)
    
    # 验证结果
    assert len(alerts) == 2  # 应该触发两条告警
    assert any(a["id"] == "alert1" for a in alerts)  # 价格告警
    assert any(a["id"] == "alert2" for a in alerts)  # 成交量告警
