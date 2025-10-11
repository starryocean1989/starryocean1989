# 策略启动问题完整解决方案

## 核心问题

**问题**：策略成功部署到策略池，但无法启动

**根本原因**：VnPy策略启动有严格的前置条件

---

## ⭐ 策略启动必须满足的条件

### 1️⃣ 网关必须已连接

**检查方法**：网关卡片显示"已连接"状态

**如何连接**：
- 真实网关：点击"连接"→ 输入密码 → 等待连接成功
- PaperAccount：创建后自动"连接"

### 2️⃣ 合约数据必须可用 ⭐⭐⭐ 最关键

**检查方法**：
```python
contract = main_engine.get_contract("600000.SSE")
# 必须返回ContractData对象，不能是None
```

**为什么重要**：
策略初始化时会执行：
```python
# vnpy_ctastrategy/engine.py 第693行
contract = self.main_engine.get_contract(strategy.vt_symbol)
if contract:
    # 订阅行情
    self.main_engine.subscribe(req, contract.gateway_name)
else:
    self.write_log("行情订阅失败，找不到合约")
    # 初始化失败 → 无法启动
```

**如何获取合约数据**：

| 网关类型 | 合约数据来源 | 是否自动 |
|---------|-------------|---------|
| CTP | 连接后自动推送 | ✅ 自动 |
| IB | 连接后自动推送 | ✅ 自动 |
| TTS | 连接后自动推送 | ✅ 自动 |
| **PaperAccount** | **无自动推送** | ❌ 需要手动 |

### 3️⃣ 策略类已注册到引擎

**检查方法**：
```python
strategy_class = cta_engine.classes.get("MyStrategy")
# 必须返回策略类，不能是None
```

**如何注册**：
- vnpy会自动扫描策略目录
- 策略必须继承正确的模板类
- 策略文件必须在正确的文件夹中

---

## 🔴 PaperAccount启动策略的问题

### 问题根因

PaperAccount是**纯本地模拟网关**，特点：
- ✅ 不需要连接真实服务器
- ✅ 不需要真实账号密码
- ✅ 提供虚拟资金账户
- ❌ **不提供合约数据**
- ❌ **不提供行情数据**

因此：
```python
# PaperAccount连接后
contract = main_engine.get_contract("600000.SSE")
# 返回 None ❌

# 策略初始化失败
# → 无法启动策略
```

### 解决方案

#### 方案1：混合使用网关（推荐）

**配置**：
- **行情网关**：CTP/TTS等真实网关（只用于接收行情和合约数据）
- **交易网关**：PaperAccount（用于模拟交易，零风险）

**操作步骤**：

1. **创建CTP行情网关**
   ```
   网关名称：CTP_行情
   网关类型：CTP
   用途：仅用于获取行情和合约数据
   ```

2. **连接CTP行情网关**
   ```
   → 网关连接成功
   → 自动获取所有可用合约
   → main_engine.contracts中填充数据
   ```

3. **创建PaperAccount交易网关**
   ```
   网关名称：PaperAccount_1
   网关类型：PaperAccount
   初始资金：1000000
   ```

4. **在PaperAccount上部署策略**
   ```
   → 使用CTP网关提供的合约数据
   → 订阅行情成功
   → 策略初始化成功
   → 可以启动策略
   ```

5. **策略交易流程**
   ```
   行情来源：CTP网关（真实行情）
   交易执行：PaperAccount（模拟成交，无风险）
   ```

**优势**：
- ✅ 真实合约数据
- ✅ 真实行情数据
- ✅ 无资金风险
- ✅ 完整的测试环境

---

#### 方案2：为PaperAccount预加载合约数据

**实现方式**：修改代码，在PaperAccount连接时加载本地合约数据库。

**代码位置**：`backend/services/trading_gateway_service.py`

```python
def connect_gateway(self, gateway_name: str, password: Optional[str] = None):
    # ... 连接网关 ...

    # 如果是PaperAccount，加载本地合约数据
    if gateway_type == "paperaccount":
        self._load_local_contracts_for_paper_account()

    return result

def _load_local_contracts_for_paper_account(self):
    """为PaperAccount加载本地合约数据."""
    # 从数据库或配置文件加载合约列表
    contracts = load_contracts_from_db()

    # 添加到main_engine
    for contract_data in contracts:
        self.main_engine.add_contract(contract_data)

    self.logger.info("✅ 已为PaperAccount加载 %d 个合约", len(contracts))
```

**优势**：
- ✅ 纯本地测试
- ✅ 不需要真实网关

**劣势**：
- ⚠️ 需要维护本地合约数据库
- ⚠️ 没有真实行情（需要另外的数据源）

---

## 启动失败的完整诊断流程

### 步骤1：检查网关状态

```
问题：网关显示"未连接"
解决：点击连接按钮
```

### 步骤2：检查合约数据

```python
# 在Python控制台执行
from backend.core.base import get_main_engine
main_engine = get_main_engine()

# 检查合约
contract = main_engine.get_contract("600000.SSE")
print(f"合约数据: {contract}")

# 如果返回None，说明合约数据不可用
```

**解决方案**：
- 真实网关：重新连接，等待合约数据推送
- PaperAccount：使用方案1（混合网关）

### 步骤3：查看初始化日志

```
正在初始化策略 'my_strategy'...
⚠️ 找不到合约数据: ['600000.SSE']
行情订阅失败，找不到合约600000.SSE
```

**解决方案**：参考步骤2

### 步骤4：检查策略类注册

```python
cta_engine = main_engine.get_engine("CtaStrategy")
print(f"已注册策略类: {list(cta_engine.classes.keys())}")
```

**解决方案**：
- 确认策略文件在正确位置
- 重启交易终端

---

## 推荐的测试配置

### 配置A：完整测试环境（推荐）

```
网关1：CTP_行情
  类型：CTP
  用途：获取合约和行情
  配置：使用真实的CTP账号
  连接：是

网关2：PaperAccount_交易
  类型：PaperAccount
  用途：模拟交易
  初始资金：1000000
  连接：是

策略：部署在PaperAccount_交易上
  引擎：CTA策略
  合约：600000.SSE（从CTP获取）
  状态：可以正常启动 ✅
```

### 配置B：纯本地测试（需要增强）

```
网关：PaperAccount_1
  类型：PaperAccount
  用途：纯本地模拟
  初始资金：1000000
  连接：是

问题：无合约数据
  → 策略初始化失败
  → 无法启动策略 ❌

需要：实现方案2（预加载合约数据）
```

---

## 修改的代码

### 1. 前置条件检查

**文件**：`backend/services/trading_gateway_service.py`

**方法**：`_check_strategy_start_preconditions()`

**功能**：
- 检查网关连接状态
- 检查合约数据可用性
- 返回友好的错误提示和解决方案

### 2. 引擎类型识别

**新增常量**：`STRATEGY_POOL_SUPPORTED_ENGINES`

**支持的引擎**：
- CtaStrategy
- PortfolioStrategy
- SpreadTrading

**明确不支持**：
- OptionMaster（期权分析工具）
- AlgoTrading（一次性算法）
- ScriptTrader（临时脚本）

### 3. 错误提示优化

对于不支持策略池的引擎，提供详细说明：
```
期权分析引擎不支持通过策略池部署。

期权引擎（OptionMaster）是专业的期权分析和对冲工具，提供：
  • 期权T型报价展示
  • 希腊字母计算和监控
  • 期权定价算法
  • 期权对冲算法
  • 隐含波动率分析

它不是传统的策略引擎，无法通过策略池部署。
如需进行期权交易策略，建议使用CTA策略引擎，
在策略代码中调用期权相关的交易逻辑。
```

---

## 快速测试指南

### 最简单的成功路径

1. **创建真实行情网关**（如CTP）
2. **连接行情网关** → 获取合约数据
3. **创建PaperAccount** → 模拟交易
4. **部署CTA策略** → 选择cta_strategies文件夹
5. **填写参数**：
   - 合约：600000.SSE
   - 其他参数按策略要求填写
6. **启动策略** → 成功 ✅

**预期日志**：
```
✅ 策略应用 CTA策略 已按需加载
✅ CTA策略 'test_001' 已部署，合约: 600000.SSE
正在初始化策略 'test_001'...
✅ 策略 'test_001' 初始化完成
正在启动策略 'test_001'...
✅ 策略 'test_001' 已启动
```

---

## 总结

**策略启动的两大关键**：

1. **网关已连接** - 提供交易通道
2. **合约数据可用** - 这是最容易被忽略但最重要的条件

**PaperAccount的特殊性**：
- 是纯本地模拟
- 不提供合约数据
- 建议与真实行情网关配合使用

**支持策略池的引擎**：
- ✅ CTA策略
- ✅ 组合策略
- ✅ 价差交易

**不支持策略池的引擎**：
- ❌ 期权分析（分析工具）
- ❌ 算法交易（一次性算法）
- ❌ 脚本交易（临时脚本）

---

**文档创建日期**：2025-10-10
**问题严重级别**：🟡 中等
**解决状态**：✅ 已完成
**后续优化**：为PaperAccount添加本地合约数据加载功能

