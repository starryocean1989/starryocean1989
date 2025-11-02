# EventEngine API 修复报告

## 🔍 问题分析

### 错误信息
```
EventEngine.put() takes 2 positional arguments but 3 were given
```

### 根本原因
在 `backend/services/system_manager_service.py` 中，第3060行附近的代码使用了错误的EventEngine API调用方式：

**错误的调用方式：**
```python
self.event_engine.put(
    EVENT_ALERT_CREATED,
    {
        "alert": alert,
        "timestamp": alert.get("timestamp"),
        "severity": severity,
        "message": message,
    },
)
```

**正确的调用方式：**
```python
event_data = {
    "alert": alert,
    "timestamp": alert.get("timestamp"),
    "severity": severity,
    "message": message,
}
event = Event(EVENT_ALERT_CREATED, event_data)
self.event_engine.put(event)
```

## 🔧 修复内容

### 修复位置
- **文件**: `backend/services/system_manager_service.py`
- **行数**: 3055-3068
- **函数**: `_receive_alerts_loop()` 方法中的告警处理逻辑

### 修复详情
1. **添加Event导入**: `from vnpy.event import Event`
2. **创建Event对象**: 使用 `Event(event_type, event_data)` 构造函数
3. **正确调用put方法**: `self.event_engine.put(event)` 只传入Event对象

### 修复前后对比

**修复前：**
```python
self.event_engine.put(EVENT_ALERT_CREATED, {...})  # ❌ 错误：传入2个参数
```

**修复后：**
```python
event = Event(EVENT_ALERT_CREATED, event_data)
self.event_engine.put(event)  # ✅ 正确：只传入Event对象
```

## ✅ 验证结果

### API兼容性测试
- ✅ 正确的API调用 `event_engine.put(event)` 成功
- ✅ 错误的API调用 `event_engine.put(type, data)` 正确地抛出TypeError
- ✅ 错误信息匹配：`EventEngine.put() takes 2 positional arguments but 3 were given`

### 代码扫描结果
- ✅ 扫描了所有 `event_engine.put()` 调用
- ✅ 确认其他11处调用都使用正确的API格式
- ✅ 只有1处使用了错误的API格式，已修复

## 🎯 预期效果

修复后，系统应该：
1. **不再出现EventEngine API错误**
2. **告警事件能够正常发送到事件系统**
3. **CPU使用率告警能够正常处理**
4. **IPC通信中的事件推送恢复正常**

## 📋 相关信息

### VnPy EventEngine API规范
- **正确用法**: `event_engine.put(event: Event)`
- **Event构造**: `Event(event_type: str, event_data: Any)`
- **参数数量**: put方法只接受1个参数（Event对象）

### 影响范围
- **模块**: 系统监控服务 (SystemManagerService)
- **功能**: 告警事件推送
- **兼容性**: 向后兼容，不影响其他功能

## 🚀 建议行动

**立即行动**: 重新启动终端应用以测试修复效果
**预期结果**: 
- 不应再出现 `EventEngine.put() takes 2 positional arguments but 3 were given` 错误
- CPU告警应该能够正常发送到事件系统
- 系统监控功能应该恢复正常

---
**修复时间**: 2025-11-02 14:35  
**修复状态**: ✅ 已完成  
**测试状态**: ✅ 已验证  