# -*- coding: utf-8 -*-
# data_module_vnpy 新架构业务细节文档

**版本**: v3.1 (微观架构优化版)
**创建日期**: 2025-01-02
**最后更新**: 2025-01-02
**文档目标**: 定义新架构下的业务流程规则细节、实现逻辑和微观架构设计

> **📖 文档分工**:
> - **本文档**:专注于业务流程、规则细节、实现逻辑、算法描述、**微观架构设计**
> - **最佳实践文档**:专注于架构设计、技术选型、性能目标、组件设计
> 
> 两文档遵循单一事实原则,互相引用但不重复内容。
>
> **📌 v3.1更新**:
> - 新增微观架构设计章节,填补架构与细节规则之间的鸿沟
> - 为每个业务规则设计最佳实践的微观架构承载方案
> - 明确数据结构设计、状态管理、异常处理等微观实现细节

---

## 📋 目录

- [一、品种管理业务规则](#一品种管理业务规则)
  - [微观架构设计](#11-微观架构设计)
- [二、数据下载业务规则](#二数据下载业务规则)
  - [微观架构设计](#21-微观架构设计)
- [三、数据验证业务规则](#三数据验证业务规则)
  - [微观架构设计](#31-微观架构设计)
- [四、缓存管理业务规则](#四缓存管理业务规则)
  - [微观架构设计](#41-微观架构设计)
- [五、负载均衡业务规则](#五负载均衡业务规则)
  - [微观架构设计](#51-微观架构设计)
- [六、IPO日期管理业务规则](#六IPO日期管理业务规则)
  - [微观架构设计](#61-微观架构设计)
- [七、数据质量管理业务规则](#七数据质量管理业务规则)
  - [微观架构设计](#71-微观架构设计)
- [八、统一数据查询业务规则](#八统一数据查询业务规则)
  - [微观架构设计](#81-微观架构设计)
- [九、实时推送业务规则](#九实时推送业务规则)
  - [微观架构设计](#91-微观架构设计)
- [十、文件监控业务规则](#十文件监控业务规则)
  - [微观架构设计](#101-微观架构设计)
- [十一、native_iocp集成业务规则](#十一native_iocp集成业务规则)
  - [微观架构设计](#111-微观架构设计)
- [十二、子进程日志配置业务规则](#十二子进程日志配置业务规则)
  - [微观架构设计](#121-微观架构设计)
- [十三、背压控制与队列管理业务规则](#十三背压控制与队列管理业务规则)
  - [微观架构设计](#131-微观架构设计)

---

## 一、品种管理业务规则

> **架构设计参考**：组件设计和技术架构请参考 [最佳实践文档 - 2.2 data_acquisition.py](./data_module_vnpy新架构最佳实践cursor版.md#22-data_acquisitionpy---数据获取模块)

### 1.1 微观架构设计

#### 1.1.1 品种分类器架构

**设计目标**：
- 将品种分类逻辑模块化为独立的分类器类
- 每个分类器专注于一种品种类型的识别
- 支持灵活的分类规则扩展和修改
- 实现分类逻辑的可测试性和可维护性

**核心类设计**：

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any
import pandas as pd

class BaseClassifier(ABC):
    """品种分类器基类"""
    
    @abstractmethod
    def classify(self, complete_df: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """分类方法
        
        Args:
            complete_df: 完整的品种数据DataFrame（来自TDX API）
            **kwargs: 额外的分类参数（如配置解析器）
            
        Returns:
            分类结果列表，每个元素包含 code, name, market 字段
        """
        pass
    
    @abstractmethod
    def get_classifier_name(self) -> str:
        """获取分类器名称"""
        pass


class ShanghaiStockClassifier(BaseClassifier):
    """上证A股分类器"""
    
    def classify(self, complete_df: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """识别上证A股
        
        规则：
        - market == 1
        - code以688（科创板）或60开头
        - code长度为6位数字
        """
        filtered = complete_df[
            (complete_df['market'] == 1) & 
            (complete_df['code'].str.len() == 6) &
            (complete_df['code'].str.isdigit()) &
            (complete_df['code'].str.startswith('688') | 
             complete_df['code'].str.startswith('60'))
        ]
        
        return filtered[['code', 'name', 'market']].to_dict('records')
    
    def get_classifier_name(self) -> str:
        return "上证A股"


class ShenzhenStockClassifier(BaseClassifier):
    """深证A股分类器"""
    
    def classify(self, complete_df: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """识别深证A股
        
        规则：
        - market == 0
        - code以000/001/002（主板/中小板）或300/301（创业板）开头
        - code长度为6位数字
        """
        filtered = complete_df[
            (complete_df['market'] == 0) & 
            (complete_df['code'].str.len() == 6) &
            (complete_df['code'].str.isdigit()) &
            (complete_df['code'].str.startswith(('000', '001', '002', '300', '301')))
        ]
        
        return filtered[['code', 'name', 'market']].to_dict('records')
    
    def get_classifier_name(self) -> str:
        return "深证A股"


class BeijingStockClassifier(BaseClassifier):
    """北证A股分类器"""
    
    def classify(self, complete_df: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """识别北证A股
        
        数据来源：从addedcode_bj.cfg配置文件解析
        市场代码：2（硬编码值）
        
        注意：北证A股不从TDX API获取，从配置文件解析
        """
        config_parser = kwargs.get('config_parser')
        if not config_parser:
            logger.warning("北证A股分类器缺少config_parser参数，返回空列表")
            return []
        
        # 从配置文件解析北证品种
        beijing_stocks = config_parser.parse_addedcode_bj()
        
        # 添加固定市场代码2
        result = []
        for stock in beijing_stocks:
            result.append({
                "code": stock["code"],
                "name": stock["name"],
                "market": 2  # 硬编码值
            })
        
        return result
    
    def get_classifier_name(self) -> str:
        return "北证A股"


class T0FundClassifier(BaseClassifier):
    """T+0基金分类器"""
    
    def classify(self, complete_df: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """识别T+0基金
        
        数据来源：从spblock.dat配置文件获取市场+代码列表
        匹配逻辑：从complete_df中匹配名称
        过滤规则：API中不存在的品种会被过滤
        """
        block_parser = kwargs.get('block_parser')
        if not block_parser:
            logger.warning("T+0基金分类器缺少block_parser参数，返回空列表")
            return []
        
        # 从spblock.dat获取T+0基金代码列表
        t0_fund_codes = block_parser.get_t0_fund_codes()
        
        result = []
        for fund in t0_fund_codes:
            market = int(fund["market"])
            code = str(fund["code"]).zfill(6)
            
            # 从complete_df中匹配名称
            matched = complete_df[
                (complete_df["market"] == market) & 
                (complete_df["code"] == code)
            ]
            
            if len(matched) > 0:
                name = str(matched.iloc[0].get("name", ""))
                result.append({"code": code, "name": name, "market": market})
            # API中无匹配的品种视为不存在，直接跳过
        
        return result
    
    def get_classifier_name(self) -> str:
        return "T+0基金"


class ConvertibleBondClassifier(BaseClassifier):
    """可转债分类器"""
    
    def classify(self, complete_df: pd.DataFrame, **kwargs) -> List[Dict[str, Any]]:
        """识别可转债
        
        数据来源：从tdxstat2.cfg配置文件获取市场+代码列表
        匹配逻辑：从complete_df中匹配名称，支持市场代码容错（0↔1）
        过滤规则：如果有多个匹配，过滤掉指数和ETF
        """
        config_parser = kwargs.get('config_parser')
        if not config_parser:
            logger.warning("可转债分类器缺少config_parser参数，返回空列表")
            return []
        
        # 从tdxstat2.cfg获取可转债代码列表
        convertible_codes_by_market = config_parser.parse_tdxstat2()
        
        result = []
        for market, codes in convertible_codes_by_market.items():
            mkt = int(market)
            for raw_code in codes:
                code = str(raw_code).zfill(6)
                
                # 尝试原始市场代码匹配
                matched = complete_df[
                    (complete_df["market"] == mkt) & 
                    (complete_df["code"] == code)
                ]
                
                # 如果原始市场匹配不到，尝试交换市场代码（0↔1）
                if len(matched) == 0:
                    alt_mkt = 1 if mkt == 0 else 0
                    matched_alt = complete_df[
                        (complete_df["market"] == alt_mkt) & 
                        (complete_df["code"] == code)
                    ]
                    if len(matched_alt) > 0:
                        matched = matched_alt
                        mkt = alt_mkt  # 使用交换后的市场代码
                
                if len(matched) > 0:
                    # 如果有多个匹配，过滤掉指数和ETF
                    if len(matched) > 1:
                        non_index = matched[
                            ~matched["name"].str.contains("指数|ETF", na=False, regex=True)
                        ]
                        if len(non_index) > 0:
                            matched = non_index
                    
                    name = str(matched.iloc[0].get("name", ""))
                    result.append({"code": code, "name": name, "market": mkt})
                # API中无匹配的品种视为不存在，直接跳过
        
        return result
    
    def get_classifier_name(self) -> str:
        return "可转债"
```

**分类器注册表架构**：

```python
class ClassifierRegistry:
    """分类器注册表
    
    管理所有品种分类器的注册、查询和执行
    """
    
    def __init__(self):
        self._classifiers: Dict[str, BaseClassifier] = {}
        self._execution_order: List[str] = []
    
    def register(self, classifier: BaseClassifier, order: int = 999):
        """注册分类器
        
        Args:
            classifier: 分类器实例
            order: 执行顺序（数字越小越先执行）
        """
        name = classifier.get_classifier_name()
        self._classifiers[name] = classifier
        self._execution_order.append((order, name))
        self._execution_order.sort(key=lambda x: x[0])
    
    def classify_all(self, complete_df: pd.DataFrame, **kwargs) -> Dict[str, List[Dict]]:
        """执行所有分类器
        
        Returns:
            分类结果字典，key为分类器名称，value为分类结果列表
        """
        results = {}
        for order, name in self._execution_order:
            classifier = self._classifiers[name]
            try:
                classified = classifier.classify(complete_df, **kwargs)
                results[name] = classified
                logger.debug(f"分类器 {name} 完成，识别到 {len(classified)} 个品种")
            except Exception as e:
                logger.error(f"分类器 {name} 执行失败: {e}", exc_info=True)
                results[name] = []
        
        return results
    
    def get_classifier(self, name: str) -> BaseClassifier:
        """获取指定分类器"""
        return self._classifiers.get(name)
```

**使用示例**：

```python
# 在SymbolLoader中使用分类器注册表
class SymbolLoader:
    def __init__(self, event_engine: Optional[EventEngine] = None):
        self.event_engine = event_engine
        
        # 初始化分类器注册表
        self.classifier_registry = ClassifierRegistry()
        self._register_classifiers()
    
    def _register_classifiers(self):
        """注册所有分类器"""
        # 注册顺序决定执行顺序
        self.classifier_registry.register(ShanghaiStockClassifier(), order=1)
        self.classifier_registry.register(ShenzhenStockClassifier(), order=2)
        self.classifier_registry.register(BeijingStockClassifier(), order=3)
        self.classifier_registry.register(T0FundClassifier(), order=4)
        self.classifier_registry.register(ConvertibleBondClassifier(), order=5)
    
    async def reload_and_classify_async(self) -> Dict:
        """重新加载并分类"""
        # 1. 从API加载完整品种列表
        complete_df = await self.load_from_api_async()
        
        # 2. 准备分类参数
        config_parser = TdxConfigFileParser()
        block_parser = BlockParser()
        
        # 3. 执行所有分类器
        classified_results = self.classifier_registry.classify_all(
            complete_df,
            config_parser=config_parser,
            block_parser=block_parser
        )
        
        # 4. 后续处理（去重、验证、IPO日期集成等）
        # ...
```

**优势分析**：

1. **单一职责**：每个分类器只负责一种品种类型的识别
2. **易于扩展**：添加新品种类型只需实现新的分类器类
3. **便于测试**：每个分类器可独立测试
4. **解耦合**：分类逻辑与数据加载逻辑解耦
5. **灵活配置**：通过注册表控制执行顺序和启用状态

#### 1.1.2 品种过滤器架构

**设计目标**：
- 将品种过滤逻辑模块化为独立的过滤器类
- 支持链式过滤（Filter Chain Pattern）
- 便于添加、修改、禁用过滤规则

**核心类设计**：

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple

class BaseFilter(ABC):
    """品种过滤器基类"""
    
    @abstractmethod
    def filter(self, symbols: List[Dict[str, Any]], **kwargs) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """过滤方法
        
        Args:
            symbols: 待过滤的品种列表
            **kwargs: 额外的过滤参数（如IPO日期字典）
            
        Returns:
            (保留的品种列表, 过滤掉的品种列表)
        """
        pass
    
    @abstractmethod
    def get_filter_name(self) -> str:
        """获取过滤器名称"""
        pass


class UnlistedSymbolFilter(BaseFilter):
    """未上市品种过滤器"""
    
    def filter(self, symbols: List[Dict[str, Any]], **kwargs) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """过滤未上市品种
        
        规则：
        - IPO日期为None或无效日期的品种将被标记为未上市
        - IPO日期原始值 < 19900000（如70这种无效值）
        - IPO日期解析失败
        - IPO日期为0或None
        """
        ipo_dates = kwargs.get('ipo_dates', {})
        
        kept = []
        filtered = []
        
        for symbol in symbols:
            code = symbol['code']
            ipo_date = ipo_dates.get(code)
            
            # 判断是否未上市
            if ipo_date is None or not self._is_valid_ipo_date(ipo_date):
                filtered.append({
                    **symbol,
                    'filter_reason': f'未上市（IPO日期: {ipo_date})'
                })
            else:
                kept.append(symbol)
        
        logger.debug(f"{self.get_filter_name()}：保留{len(kept)}个，过滤{len(filtered)}个")
        return kept, filtered
    
    def _is_valid_ipo_date(self, ipo_date: Any) -> bool:
        """验证IPO日期有效性"""
        if ipo_date is None:
            return False
        
        # 检查日期范围
        try:
            if isinstance(ipo_date, (int, float)):
                # 原始整数值检查
                if ipo_date < 19900000:
                    return False
            elif isinstance(ipo_date, date):
                # date对象检查
                if ipo_date.year < 1990:
                    return False
            else:
                return False
            
            return True
        except Exception:
            return False
    
    def get_filter_name(self) -> str:
        return "未上市品种过滤器"


class DuplicateSymbolFilter(BaseFilter):
    """重复品种过滤器"""
    
    def filter(self, symbols: List[Dict[str, Any]], **kwargs) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """过滤重复品种
        
        规则：
        - 同一品种代码只保留一条记录
        - 按出现顺序，保留第一条
        """
        seen_codes = set()
        kept = []
        filtered = []
        
        for symbol in symbols:
            code = symbol['code']
            if code in seen_codes:
                filtered.append({
                    **symbol,
                    'filter_reason': f'重复品种（代码: {code})'
                })
            else:
                seen_codes.add(code)
                kept.append(symbol)
        
        logger.debug(f"{self.get_filter_name()}：保留{len(kept)}个，过滤{len(filtered)}个")
        return kept, filtered
    
    def get_filter_name(self) -> str:
        return "重复品种过滤器"


class InvalidDataFilter(BaseFilter):
    """无效数据过滤器"""
    
    def filter(self, symbols: List[Dict[str, Any]], **kwargs) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """过滤无效数据
        
        规则：
        - code和name都必须有效（非空且去除空格后不为空）
        """
        kept = []
        filtered = []
        
        for symbol in symbols:
            code = str(symbol.get('code', '')).strip()
            name = str(symbol.get('name', '')).strip()
            
            if not code or not name:
                filtered.append({
                    **symbol,
                    'filter_reason': f'无效数据（code={code}, name={name})'
                })
            else:
                kept.append(symbol)
        
        logger.debug(f"{self.get_filter_name()}：保留{len(kept)}个，过滤{len(filtered)}个")
        return kept, filtered
    
    def get_filter_name(self) -> str:
        return "无效数据过滤器"
```

**过滤器链架构**：

```python
class FilterChain:
    """过滤器链
    
    按顺序执行多个过滤器，支持中间结果统计
    """
    
    def __init__(self):
        self._filters: List[BaseFilter] = []
        self._filter_stats: Dict[str, Dict[str, int]] = {}
    
    def add_filter(self, filter_instance: BaseFilter):
        """添加过滤器到链中"""
        self._filters.append(filter_instance)
    
    def execute(self, symbols: List[Dict[str, Any]], **kwargs) -> Tuple[List[Dict[str, Any]], Dict]:
        """执行过滤器链
        
        Returns:
            (最终保留的品种列表, 过滤统计信息)
        """
        current_symbols = symbols
        total_filtered = []
        
        for filter_instance in self._filters:
            kept, filtered = filter_instance.filter(current_symbols, **kwargs)
            
            # 记录统计
            filter_name = filter_instance.get_filter_name()
            self._filter_stats[filter_name] = {
                'input': len(current_symbols),
                'kept': len(kept),
                'filtered': len(filtered)
            }
            
            # 更新当前品种列表
            current_symbols = kept
            total_filtered.extend(filtered)
        
        # 生成统计报告
        stats = self._generate_stats_report(len(symbols), len(current_symbols), total_filtered)
        
        return current_symbols, stats
    
    def _generate_stats_report(self, initial_count: int, final_count: int, 
                               filtered_symbols: List[Dict]) -> Dict:
        """生成统计报告"""
        return {
            'initial_count': initial_count,
            'final_count': final_count,
            'total_filtered': len(filtered_symbols),
            'filter_details': self._filter_stats,
            'filtered_symbols': filtered_symbols
        }
```

**使用示例**：

```python
class SymbolLoader:
    def __init__(self, event_engine: Optional[EventEngine] = None):
        self.event_engine = event_engine
        
        # 初始化过滤器链
        self.filter_chain = FilterChain()
        self._register_filters()
    
    def _register_filters(self):
        """注册所有过滤器"""
        # 顺序很重要：先去重，再过滤无效数据，最后过滤未上市品种
        self.filter_chain.add_filter(DuplicateSymbolFilter())
        self.filter_chain.add_filter(InvalidDataFilter())
        self.filter_chain.add_filter(UnlistedSymbolFilter())
    
    async def reload_and_classify_async(self) -> Dict:
        """重新加载并分类"""
        # 1. 分类
        classified_results = self.classifier_registry.classify_all(...)
        
        # 2. 合并所有分类结果
        all_symbols = []
        for category, symbols in classified_results.items():
            all_symbols.extend(symbols)
        
        # 3. 执行过滤器链
        ipo_dates = await self._load_ipo_dates()
        final_symbols, filter_stats = self.filter_chain.execute(
            all_symbols,
            ipo_dates=ipo_dates
        )
        
        # 4. 输出统计信息
        logger.info(f"品种过滤完成：初始{filter_stats['initial_count']}个，"
                   f"最终{filter_stats['final_count']}个，"
                   f"过滤{filter_stats['total_filtered']}个")
        
        return final_symbols
```

**优势分析**：

1. **链式处理**：多个过滤器顺序执行，便于管理复杂过滤逻辑
2. **可配置**：可动态添加、移除、调整过滤器顺序
3. **统计友好**：自动记录每个过滤器的执行结果
4. **可追溯**：记录每个被过滤品种的原因
5. **易于测试**：每个过滤器可独立测试

---

### 1.2 品种分类规则

#### 1.1.1 市场分类标准

**上证A股分类规则**：
```python
# 市场代码：market=1
# 代码规则：以688（科创板）或60开头的6位数字
def is_shanghai_a_stock(code: str, market: int) -> bool:
    return (market == 1 and
            len(code) == 6 and
            code.isdigit() and
            (code.startswith('688') or code.startswith('60')))
```

**深证A股分类规则**：
```python
# 市场代码：market=0
# 代码规则：以000（主板）、001/002（中小板）、300/301（创业板）开头的6位数字
def is_shenzhen_a_stock(code: str, market: int) -> bool:
    return (market == 0 and
            len(code) == 6 and
            code.isdigit() and
            (code.startswith('000') or
             code.startswith('001') or
             code.startswith('002') or
             code.startswith('300') or
             code.startswith('301')))
```

**北证A股分类规则**：
```python
# 市场代码：market=2（硬编码值，不从API获取）
# 数据来源：从addedcode_bj.cfg配置文件解析，不从TDX API获取
# 解析规则：从配置文件读取代码和简称，添加固定市场代码2
def _get_beijing_stocks(config_parser: TdxConfigFileParser) -> List[Dict]:
    """获取北证A股（集合B → 集合I）"""
    # 从addedcode_bj.cfg解析
    beijing_stocks = config_parser.parse_addedcode_bj()
    result = []
    for stock in beijing_stocks:
        result.append({
            "code": stock["code"],
            "name": stock["name"],
            "market": 2  # 市场代码2为硬编码值
        })
    return result
```

**T+0基金分类规则**：
```python
# 数据来源：从spblock.dat配置文件获取市场+代码列表，再从TDX API匹配名称
# 匹配规则：从完整缓存（API获取的品种列表）中匹配名称
# 过滤规则：API中不存在的品种会被过滤（视为已退市/到期）
def _get_t0_funds(complete_df: pd.DataFrame, block_parser: BlockParser) -> List[Dict]:
    """获取T+0基金（集合C → 集合H）"""
    # 从spblock.dat获取市场+代码列表
    t0_fund_codes = block_parser.get_t0_fund_codes()
    result = []

    for fund in t0_fund_codes:
        market = int(fund["market"])
        code = str(fund["code"]).zfill(6)

        # 从完整缓存中匹配名称
        matched = complete_df[
            (complete_df["market"] == market) & (complete_df["code"] == code)
        ]

        if len(matched) > 0:
            name = str(matched.iloc[0].get("name", ""))
            result.append({"code": code, "name": name, "market": market})
        # API中无匹配的品种视为不存在（已退市/到期），直接跳过

    return result
```

**可转债分类规则**：
```python
# 数据来源：从tdxstat2.cfg配置文件获取市场+代码列表，再从TDX API匹配名称
# 匹配规则：从完整缓存中匹配名称，支持市场代码容错（交换市场代码0↔1）
# 过滤规则：如果有多个匹配，过滤掉指数和ETF；API中不存在的品种会被过滤
def _get_convertible_bonds(complete_df: pd.DataFrame, config_parser: TdxConfigFileParser) -> List[Dict]:
    """获取可转债（集合A → 集合G）"""
    # 从tdxstat2.cfg获取市场+代码列表
    convertible_codes_by_market = config_parser.parse_tdxstat2()
    result = []

    for market, codes in convertible_codes_by_market.items():
        mkt = int(market)
        for raw_code in codes:
            code = str(raw_code).zfill(6)

            # 尝试原始市场代码匹配
            matched = complete_df[
                (complete_df["market"] == mkt) & (complete_df["code"] == code)
            ]

            # 如果原始市场匹配不到，尝试交换市场代码（0↔1）
            if len(matched) == 0:
                alt_mkt = 1 if mkt == 0 else 0
                matched_alt = complete_df[
                    (complete_df["market"] == alt_mkt) & (complete_df["code"] == code)
                ]
                if len(matched_alt) > 0:
                    matched = matched_alt
                    mkt = alt_mkt  # 使用交换后的市场代码

            if len(matched) > 0:
                # 如果有多个匹配，过滤掉指数和ETF
                if len(matched) > 1:
                    non_index = matched[
                        ~matched["name"].str.contains("指数|ETF", na=False, regex=True)
                    ]
                    if len(non_index) > 0:
                        matched = non_index

                name = str(matched.iloc[0].get("name", ""))
                result.append({"code": code, "name": name, "market": mkt})
            # API中无匹配的品种视为不存在（已退市/到期），直接跳过

    return result
```

#### 1.1.2 品种过滤规则

**未上市品种过滤**：
- **规则**：IPO日期为None或无效日期的品种将被标记为未上市
- **判断标准**：
  - IPO日期原始值 < 19900000（如70这种无效值）
  - IPO日期解析失败
  - IPO日期为0或None
- **处理方式**：从品种列表中移除，记录到unlisted_symbols.json

**重复品种去重规则**：
- **规则**：同一品种代码只保留一条记录
- **去重时机**：在每个市场数据合并之前进行
- **实现方式**：使用`drop_duplicates(subset=["code"], keep="first")`
- **字段选择**：基于code字段去重
- **优先级**：按API返回顺序，保留第一条
- **日志记录**：重复品种会记录DEBUG级别日志

#### 1.1.3 品种缓存规则

**缓存文件结构**：
```json
{
    "_meta": {
        "cache_date": "2025-01-02",
        "version": "2.1",
        "total_count": 5200
    },
    "classified": {
        "上证A股": [{"code": "600000", "name": "浦发银行", "market": 1}],
        "深证A股": [{"code": "000001", "name": "平安银行", "market": 0}],
        "北证A股": [{"code": "830799", "name": "艾融软件", "market": 2}],
        "T+0基金": [{"code": "511990", "name": "华宝添益", "market": 1}],
        "可转债": [{"code": "110001", "name": "中行转债", "market": 1}]
    }
}
```

**缓存失效规则**：
- **时间失效**：每日0时自动失效（基于网络时间）
- **强制刷新**：用户手动触发重新加载
- **版本检查**：缓存版本不匹配时失效

### 1.2 品种列表获取规则

#### 1.2.1 API调用规则

**调用顺序**：
1. 优先从本地缓存加载（如果当日有效）
2. 缓存失效时调用TDX API获取最新数据
3. API失败时使用过期缓存（降级策略）

**API参数配置**：
```python
# 获取所有市场的品种列表
markets = [
    (0, "深证A股"),  # 深圳市场
    (1, "上证A股"),  # 上海市场
    (2, "北证A股")   # 北京市场（不从API获取，从配置文件解析）
]
```

**API分页获取规则**：
- **分页机制**：每页最多1000条，使用`start`参数控制起始位置
- **获取方式**：串行分页请求，递增获取所有页
- **结束条件**：当返回数据少于1000条时，说明已获取完所有数据
- **重试机制**：每页请求最多重试3次
- **超时控制**：每次请求超时3秒，连接超时5秒

**服务器选择规则**：
- **服务器池分配**：每个市场有3个候选服务器（支持故障切换）
  - 深圳市场：使用服务器池索引[0, 2, 4]
  - 上海市场：使用服务器池索引[1, 3, 5]
- **故障切换机制**：当前服务器失败时自动切换到下一个候选服务器
- **错误处理**：所有服务器都失败时抛出异常

**并发获取规则**：
- **并发策略**：使用asyncio并发获取深圳和上海两个市场的数据
- **技术选型**：使用asyncio而非multiprocessing（避免Windows spawn死锁问题）
- **错误隔离**：单个市场失败不影响另一个市场（使用`return_exceptions=True`）
- **架构设计**：网络I/O密集型任务，asyncio比multiprocessing更高效

**错误处理规则**：
- **网络超时**：3秒超时，最多重试3次
- **API异常**：记录错误日志，使用缓存数据
- **数据格式错误**：跳过异常记录，继续处理其他数据
- **服务器故障**：自动切换到下一个候选服务器
- **所有服务器失败**：抛出异常，记录错误日志

#### 1.2.2 数据处理规则

**字段映射规则**：
```python
# TDX API返回字段 -> 内部字段映射
field_mapping = {
    'code': 'code',        # 品种代码
    'name': 'name',        # 品种名称
    'market': 'market'     # 市场代码
}
```

**数据清洗规则**：
- **代码标准化**：确保6位数字格式
  - **补齐方法**：使用`zfill(6)`左补0到6位
  - **补齐时机**：所有市场数据合并后进行
  - **类型转换**：代码需先转换为字符串类型才能使用zfill
- **名称清理**：去除特殊字符和多余空格
- **市场验证**：确保市场代码在有效范围内(0,1,2)

**数据验证规则**：
- **验证标准**：确保code和name都有效（非空且去除空格后不为空）
- **验证时机**：分类完成后对所有品种进行验证
- **过滤逻辑**：无效品种会被过滤，记录DEBUG级别日志
- **统计输出**：验证后会输出过滤统计信息（总过滤数、各类别统计）

**空集合检查规则**：
- **检查规则**：分类完成后检查每个分类是否为空集合
- **分类映射**：
  - "上证A股" → 集合E
  - "深证A股" → 集合F
  - "北证A股" → 集合I
  - "T+0基金" → 集合H
  - "可转债" → 集合G
- **警告日志**：空集合记录WARNING级别日志，提示排查问题
- **返回字段**：返回结果中包含`empty_categories`字段，列出为空的分类列表

### 1.3 品种管理实现细节

> **架构设计参考**：组件交互、状态管理、异步操作等架构设计请参考 [最佳实践文档 - 2.2 data_acquisition.py 详细设计](./data_module_vnpy新架构最佳实践cursor版.md#223-详细设计)

#### 1.3.1 业务流程实现

**品种加载完整流程**：
1. **缓存检查** → 检查本地缓存是否有效（基于日期）
2. **API调用** → 如缓存失效，调用TDX API获取最新数据
3. **数据分类** → 按市场规则分类品种
4. **缓存保存** → 保存分类结果到本地缓存
5. **事件发布** → 通知UI更新品种列表

#### 1.3.2 错误处理策略

**降级策略**：API失败 → 使用过期缓存 → 记录警告日志
**重试策略**：网络超时重试3次，每次3秒超时
**异常隔离**：单个品种分类失败不影响其他品种

---

## 二、数据下载业务规则

> **架构设计参考**:多进程架构、负载均衡等技术设计请参考 [最佳实践文档 - 2.2 data_acquisition.py](./data_module_vnpy新架构最佳实践cursor版.md#22-data_acquisitionpy---数据获取模块)

### 2.1 微观架构设计

#### 2.1.1 下载状态机架构

**设计目标**:
- 明确定义下载任务的所有可能状态
- 规范状态之间的流转规则和触发条件
- 支持暂停/恢复/取消等操作的状态管理
- 便于监控和调试下载流程

**核心类设计**:

```python
from enum import Enum, auto
from typing import Optional, Dict, Any
import threading
import time
from dataclasses import dataclass, field

class DownloadState(Enum):
    """下载状态枚举"""
    IDLE = auto()          # 空闲:未开始下载
    PREPARING = auto()     # 准备中:加载配置、初始化资源
    RUNNING = auto()       # 运行中:正在下载
    PAUSED = auto()        # 已暂停:用户暂停下载
    STOPPING = auto()      # 停止中:正在清理资源
    COMPLETED = auto()     # 已完成:所有任务成功
    FAILED = auto()        # 已失败:发生致命错误
    CANCELLED = auto()     # 已取消:用户取消下载

@dataclass
class DownloadStatistics:
    """下载统计信息"""
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100
    
    @property
    def elapsed_time(self) -> float:
        """已用时间(秒)"""
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.time()
        return end - self.start_time

class DownloadStateMachine:
    """下载状态机
    
    管理下载任务的状态流转,确保状态变更的合法性和一致性
    """
    
    # 定义合法的状态转换规则
    VALID_TRANSITIONS = {
        DownloadState.IDLE: [DownloadState.PREPARING],
        DownloadState.PREPARING: [DownloadState.RUNNING, DownloadState.FAILED],
        DownloadState.RUNNING: [DownloadState.PAUSED, DownloadState.STOPPING, 
                                DownloadState.COMPLETED, DownloadState.FAILED],
        DownloadState.PAUSED: [DownloadState.RUNNING, DownloadState.STOPPING, DownloadState.CANCELLED],
        DownloadState.STOPPING: [DownloadState.CANCELLED],
        DownloadState.COMPLETED: [DownloadState.IDLE],  # 可重新开始
        DownloadState.FAILED: [DownloadState.IDLE],     # 可重新开始
        DownloadState.CANCELLED: [DownloadState.IDLE],  # 可重新开始
    }
    
    def __init__(self):
        self._current_state = DownloadState.IDLE
        self._state_lock = threading.Lock()
        self._state_history: List[Tuple[DownloadState, float]] = []
        self._statistics = DownloadStatistics()
        self._event_callbacks: Dict[DownloadState, List[callable]] = {}
    
    @property
    def current_state(self) -> DownloadState:
        """获取当前状态(线程安全)"""
        with self._state_lock:
            return self._current_state
    
    def transition_to(self, new_state: DownloadState, force: bool = False) -> bool:
        """状态转换
        
        Args:
            new_state: 目标状态
            force: 是否强制转换(跳过合法性检查)
            
        Returns:
            转换是否成功
        """
        with self._state_lock:
            # 检查转换合法性
            if not force and new_state not in self.VALID_TRANSITIONS.get(self._current_state, []):
                logger.warning(
                    f"非法状态转换: {self._current_state.name} -> {new_state.name}"
                )
                return False
            
            old_state = self._current_state
            self._current_state = new_state
            
            # 记录状态历史
            self._state_history.append((new_state, time.time()))
            
            # 更新统计信息
            self._update_statistics(new_state)
            
            logger.info(f"状态转换: {old_state.name} -> {new_state.name}")
            
            # 触发状态变更回调
            self._trigger_callbacks(new_state)
            
            return True
    
    def _update_statistics(self, new_state: DownloadState):
        """更新统计信息"""
        if new_state == DownloadState.RUNNING and self._statistics.start_time is None:
            self._statistics.start_time = time.time()
        
        if new_state in [DownloadState.COMPLETED, DownloadState.FAILED, DownloadState.CANCELLED]:
            self._statistics.end_time = time.time()
    
    def register_callback(self, state: DownloadState, callback: callable):
        """注册状态变更回调"""
        if state not in self._event_callbacks:
            self._event_callbacks[state] = []
        self._event_callbacks[state].append(callback)
    
    def _trigger_callbacks(self, state: DownloadState):
        """触发状态变更回调"""
        callbacks = self._event_callbacks.get(state, [])
        for callback in callbacks:
            try:
                callback(state)
            except Exception as e:
                logger.error(f"状态回调执行失败: {e}", exc_info=True)
    
    def update_statistics(self, **kwargs):
        """更新统计信息"""
        with self._state_lock:
            for key, value in kwargs.items():
                if hasattr(self._statistics, key):
                    setattr(self._statistics, key, value)
    
    def get_statistics(self) -> DownloadStatistics:
        """获取统计信息副本"""
        with self._state_lock:
            return dataclass.replace(self._statistics)
    
    def reset(self):
        """重置状态机"""
        with self._state_lock:
            self._current_state = DownloadState.IDLE
            self._state_history.clear()
            self._statistics = DownloadStatistics()
```

**使用示例**:

```python
class MultiProcessStockFetcher:
    def __init__(self, event_engine: Optional[EventEngine] = None):
        self.event_engine = event_engine
        
        # 初始化状态机
        self.state_machine = DownloadStateMachine()
        
        # 注册状态变更回调
        self.state_machine.register_callback(
            DownloadState.RUNNING, 
            self._on_download_started
        )
        self.state_machine.register_callback(
            DownloadState.COMPLETED, 
            self._on_download_completed
        )
    
    async def download_incremental_kline_async(self, symbols, start_date, intervals):
        """异步增量下载"""
        try:
            # 状态转换: IDLE -> PREPARING
            if not self.state_machine.transition_to(DownloadState.PREPARING):
                raise RuntimeError("状态转换失败:无法开始准备")
            
            # 准备资源
            await self._prepare_download(symbols, intervals)
            
            # 状态转换: PREPARING -> RUNNING
            if not self.state_machine.transition_to(DownloadState.RUNNING):
                raise RuntimeError("状态转换失败:无法开始下载")
            
            # 执行下载
            result = await self._execute_download()
            
            # 状态转换: RUNNING -> COMPLETED
            self.state_machine.transition_to(DownloadState.COMPLETED)
            
            return result
            
        except Exception as e:
            # 状态转换: * -> FAILED
            self.state_machine.transition_to(DownloadState.FAILED, force=True)
            logger.error(f"下载失败: {e}", exc_info=True)
            raise
    
    def pause_download(self):
        """暂停下载"""
        if self.state_machine.current_state == DownloadState.RUNNING:
            self.state_machine.transition_to(DownloadState.PAUSED)
            # 设置暂停事件
            if self.pause_event:
                self.pause_event.clear()
    
    def resume_download(self):
        """恢复下载"""
        if self.state_machine.current_state == DownloadState.PAUSED:
            self.state_machine.transition_to(DownloadState.RUNNING)
            # 清除暂停事件
            if self.pause_event:
                self.pause_event.set()
    
    def stop_download(self):
        """停止下载"""
        if self.state_machine.current_state in [DownloadState.RUNNING, DownloadState.PAUSED]:
            self.state_machine.transition_to(DownloadState.STOPPING)
            # 设置停止事件
            if self.stop_event:
                self.stop_event.set()
```

**优势分析**:

1. **状态清晰**:明确定义所有可能状态,避免状态混乱
2. **转换规范**:通过VALID_TRANSITIONS限制非法转换
3. **线程安全**:使用锁保护状态变更
4. **可监控**:记录状态历史,便于调试
5. **可扩展**:支持注册回调,解耦状态变更逻辑

#### 2.1.2 任务队列管理器架构

**设计目标**:
- 统一管理下载任务的分发和调度
- 支持任务优先级和批次控制
- 实现背压控制,防止队列积压
- 提供任务统计和监控能力

**核心类设计**:

```python
from queue import Queue, Empty, Full
from dataclasses import dataclass
from typing import Optional, List, Tuple
import threading

@dataclass
class DownloadTask:
    """下载任务数据模型"""
    symbol: str
    interval: str
    priority: int = 0  # 优先级,数字越大越优先
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other):
        """支持优先级队列排序"""
        return self.priority > other.priority  # 优先级高的排在前面

class TaskQueueManager:
    """任务队列管理器
    
    管理多进程共享的任务队列,支持优先级、背压控制和统计监控
    """
    
    def __init__(self, max_queue_size: int = 10000, enable_priority: bool = False):
        from multiprocessing import Manager
        
        self.manager = Manager()
        self.enable_priority = enable_priority
        
        # 任务队列(使用Manager.Queue支持多进程)
        if enable_priority:
            # 优先级队列需要自己实现
            self.task_queue = self.manager.Queue(maxsize=max_queue_size)
            self._priority_lock = threading.Lock()
        else:
            self.task_queue = self.manager.Queue(maxsize=max_queue_size)
        
        # 统计信息
        self._stats_lock = threading.Lock()
        self._total_submitted = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_skipped = 0
    
    def submit_task(self, task: DownloadTask, timeout: float = 1.0) -> bool:
        """提交任务到队列
        
        Args:
            task: 下载任务
            timeout: 入队超时时间
            
        Returns:
            是否成功入队
        """
        try:
            self.task_queue.put(task, timeout=timeout)
            
            with self._stats_lock:
                self._total_submitted += 1
            
            return True
            
        except Full:
            logger.warning(f"任务队列已满,跳过任务: {task.symbol}_{task.interval}")
            
            with self._stats_lock:
                self._total_skipped += 1
            
            return False
    
    def submit_batch(self, tasks: List[DownloadTask], timeout: float = 1.0) -> int:
        """批量提交任务
        
        Returns:
            成功入队的任务数量
        """
        success_count = 0
        for task in tasks:
            if self.submit_task(task, timeout):
                success_count += 1
        return success_count
    
    def get_task(self, timeout: float = 0.1) -> Optional[DownloadTask]:
        """获取任务(阻塞)
        
        Args:
            timeout: 等待超时时间
            
        Returns:
            下载任务,如果队列为空则返回None
        """
        try:
            return self.task_queue.get(timeout=timeout)
        except Empty:
            return None
    
    def mark_completed(self, task: DownloadTask):
        """标记任务完成"""
        with self._stats_lock:
            self._total_completed += 1
    
    def mark_failed(self, task: DownloadTask, retry: bool = True) -> bool:
        """标记任务失败
        
        Returns:
            是否需要重试
        """
        with self._stats_lock:
            self._total_failed += 1
        
        # 检查是否需要重试
        if retry and task.retry_count < task.max_retries:
            task.retry_count += 1
            # 重新入队(降低优先级)
            task.priority -= 1
            self.submit_task(task)
            return True
        
        return False
    
    def get_queue_size(self) -> int:
        """获取队列大小"""
        try:
            return self.task_queue.qsize()
        except NotImplementedError:
            # 某些平台不支持qsize()
            return -1
    
    def get_statistics(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._stats_lock:
            return {
                'total_submitted': self._total_submitted,
                'total_completed': self._total_completed,
                'total_failed': self._total_failed,
                'total_skipped': self._total_skipped,
                'queue_size': self.get_queue_size(),
                'pending': self._total_submitted - self._total_completed - self._total_failed
            }
    
    def clear(self):
        """清空队列"""
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
            except Empty:
                break
```

#### 2.1.3 连接生命周期管理器架构

**设计目标**:
- 统一管理TDX连接的创建、复用和销毁
- 支持连接池和健康检查
- 自动处理连接失败和重连
- 确保资源正确释放

**核心类设计**:

```python
from typing import List, Optional, Tuple
import asyncio

class ConnectionLifecycleManager:
    """连接生命周期管理器
    
    管理TDX连接的完整生命周期,包括创建、健康检查、复用和销毁
    """
    
    def __init__(self, worker_id: int, logger):
        self.worker_id = worker_id
        self.logger = logger
        self._active_connections: List[Tuple[str, Any]] = []  # (server, client)
    
    async def create_connections(
        self,
        servers: List[Tuple[str, int]],
        timeout: float = 3.0,
        health_check: bool = True,
        max_retries: int = 2
    ) -> List[Any]:
        """批量创建连接
        
        Args:
            servers: 服务器列表 [(host, port), ...]
            timeout: 连接超时时间
            health_check: 是否进行健康检查
            max_retries: 最大重试次数
            
        Returns:
            连接对象列表
        """
        from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API
        
        connections = []
        
        for server in servers:
            host, port = server
            client = None
            
            # 重试机制
            for attempt in range(max_retries + 1):
                try:
                    # 创建连接
                    client = AsyncTdxHq_API()
                    await asyncio.wait_for(
                        client.connect(host, port),
                        timeout=timeout
                    )
                    
                    # 健康检查
                    if health_check:
                        if not await self._health_check(client):
                            await client.close()
                            client = None
                            continue
                    
                    # 记录活跃连接
                    self._active_connections.append((f"{host}:{port}", client))
                    connections.append(client)
                    
                    self.logger.debug(
                        f"Worker {self.worker_id} 成功连接服务器 {host}:{port}"
                    )
                    break
                    
                except asyncio.TimeoutError:
                    self.logger.debug(
                        f"Worker {self.worker_id} 连接服务器 {host}:{port} 超时 "
                        f"(尝试 {attempt + 1}/{max_retries + 1})"
                    )
                    if client:
                        await client.close()
                    client = None
                    
                except Exception as e:
                    self.logger.debug(
                        f"Worker {self.worker_id} 连接服务器 {host}:{port} 失败: {e} "
                        f"(尝试 {attempt + 1}/{max_retries + 1})"
                    )
                    if client:
                        await client.close()
                    client = None
            
            # 如果所有重试都失败,添加None占位
            if client is None:
                connections.append(None)
        
        successful_count = sum(1 for c in connections if c is not None)
        self.logger.info(
            f"Worker {self.worker_id} 连接创建完成: "
            f"{successful_count}/{len(servers)} 成功"
        )
        
        return connections
    
    async def _health_check(self, client) -> bool:
        """健康检查"""
        try:
            # 尝试获取市场数据验证连接
            result = await asyncio.wait_for(
                client.get_security_list(0, 0),
                timeout=2.0
            )
            return result is not None
        except Exception as e:
            self.logger.debug(f"健康检查失败: {e}")
            return False
    
    async def close_all(self):
        """关闭所有连接"""
        close_tasks = []
        
        for server, client in self._active_connections:
            if client:
                close_tasks.append(self._safe_close(client, server))
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        self._active_connections.clear()
        
        self.logger.info(f"Worker {self.worker_id} 所有连接已关闭")
    
    async def _safe_close(self, client, server: str):
        """安全关闭连接"""
        try:
            await client.close()
            self.logger.debug(f"Worker {self.worker_id} 关闭连接 {server}")
        except Exception as e:
            self.logger.debug(f"Worker {self.worker_id} 关闭连接 {server} 失败: {e}")
    
    def get_active_count(self) -> int:
        """获取活跃连接数"""
        return len(self._active_connections)
```

**优势分析**:

1. **统一管理**:集中管理连接生命周期,避免资源泄漏
2. **自动重试**:连接失败自动重试,提高成功率
3. **健康检查**:可选的健康检查,确保连接可用
4. **批量操作**:支持批量创建和关闭,提高效率
5. **异常安全**:确保即使异常也能正确释放资源

---

### 2.2 下载策略规则

#### 2.1.1 两段式下载策略

**第一阶段：IPv4池下载**：
- **适用场景**：绝大部分K线数据下载
- **服务器选择**：优先使用IPv4服务器池
- **并发控制**：根据负载均衡器动态调整
- **切换条件**：剩余任务数 ≤ 50时进入第二阶段

**第二阶段：IPv6池下载**：
- **适用场景**：剩余少量任务或IPv4池性能不佳时
- **服务器选择**：使用IPv6服务器池
- **降级策略**：IPv6不可用时自动回退到IPv4池
- **性能监控**：实时监控IPv6连接质量

**IPv6池降级机制详细说明**：

1. **降级触发条件**：
   - IPv6服务器池测速结果为空（所有IPv6服务器连接失败）
   - IPv6服务器池在运行时全部不可用
   - 调用`get_servers_shuffled(pool_type="ipv6", allow_fallback=True)`时自动检测

2. **降级执行逻辑**：
   ```python
   # 自动降级机制（在load_balancer.py中实现）
   if not selected_servers and allow_fallback:
       if pool_type == "ipv6" and self._sorted_servers_ipv4:
           self.logger.warning(
               "⚠️ IPv6服务器池为空，自动降级使用IPv4服务器池（%d个）",
               len(self._sorted_servers_ipv4)
           )
           selected_servers = self._sorted_servers_ipv4
   ```

3. **降级判定标准**：
   - **测速阶段**：IPv6服务器连接超时（2秒）或连接失败
   - **运行阶段**：IPv6池为空或所有IPv6服务器不可用
   - **自动检测**：每次获取服务器时实时检测池状态

4. **降级后行为**：
   - 自动使用IPv4服务器池继续下载
   - 记录降级日志，便于问题排查
   - 不影响下载任务的正常执行
   - 下次重启时重新测速IPv6池

**切换阈值设定**：
```python
# 固定阈值：剩余50个任务时切换到IPv6池
threshold = 50

# 切换逻辑：
# - 当剩余任务数 <= 50时，从IPv4池切换到IPv6池
# - 这个阈值是经过测试优化的固定值，不依赖总任务数
# - 确保IPv6池处理的是少量剩余任务，避免资源浪费
```

**切换检查实现**：
```python
# 第一阶段下载逻辑（检查任务队列大小）
async def phase1_download_loop(conn_id, client, server):
    while not stop_event.is_set():
        # 检查任务队列大小（每个协程独立检查）
        try:
            queue_size = task_queue.qsize()
            if queue_size <= threshold:
                logger.info(
                    "[Phase1] Worker %s 连接%s 达到阈值（剩余%s），停止",
                    worker_id, conn_id, queue_size
                )
                break
        except Exception:
            pass  # qsize() 可能在某些平台不可用（需要异常处理）
```

**切换规则说明**：
- **检查时机**：在每个连接的下载循环中进行切换检查（每个协程独立检查）
- **检查方式**：使用`task_queue.qsize()`检查剩余任务数
- **异常处理**：`qsize()`可能在某些平台不可用，需要异常处理（捕获异常后继续执行）
- **协程独立性**：每个协程独立判断是否切换到Phase2，无需全局协调
- **切换行为**：达到阈值后协程退出循环，Worker进程自动切换到Phase2

#### 2.1.2 服务器池管理规则

**服务器测速规则**：
- **测速频率**：每日首次启动时进行测速
- **缓存机制**：测速结果缓存到当日23:59:59
- **测速超时**：单个服务器测速超时2秒
- **并发测速**：3进程 × 50协程 = 150并发测速

**服务器排序规则**：
```python
def sort_servers_by_performance(test_results: Dict) -> List:
    """按性能排序服务器"""
    # 排序优先级：
    # 1. 连接成功的服务器优先
    # 2. 按响应时间升序排列
    # 3. 相同响应时间按IP字典序

    available_servers = []
    for server, response_time in test_results.items():
        if response_time > 0:  # 连接成功
            available_servers.append((server, response_time))

    # 按响应时间排序
    available_servers.sort(key=lambda x: (x[1], x[0]))
    return [server for server, _ in available_servers]
```

**服务器选择规则**：
- **最佳服务器**：选择响应时间最短的服务器
- **随机选择**：从前N个最佳服务器中随机选择（负载均衡）
- **故障转移**：服务器连接失败时自动切换到下一个

**服务器分配策略**：
```python
# 🔥 关键优化：使用随机起始位置，确保充分利用全部服务器
# 原问题：线性分配导致只使用前部分服务器，后续服务器从未被使用
import random

# 随机起始位置（确保不超出范围）
max_start = max(0, len(regular_servers) - connections_per_worker * 3)
start_idx = random.randint(0, max_start) if max_start > 0 else 0

# 准备3倍备用服务器（从随机位置开始轮询）
my_ipv4_servers = []
for i in range(connections_per_worker * 3):
    server_idx = (start_idx + i) % len(regular_servers)
    my_ipv4_servers.append(regular_servers[server_idx])
```

**服务器分配规则说明**：
- **随机起始位置**：每个worker使用随机起始位置分配服务器（避免线性分配导致的服务器使用不均）
- **备用机制**：每个worker分配3倍备用服务器（主用 + 备用），主用服务器失败时自动切换到备用
- **轮询方式**：从随机位置开始轮询，确保充分利用所有服务器（而非只使用前部分服务器）
- **负载均衡**：通过随机起始位置实现更好的负载均衡，避免所有worker集中在同一批服务器

#### 2.1.3 增量下载规则

**日期范围计算**：
```python
def calculate_download_range(start_date: str, symbol: str, interval: str) -> Tuple[date, date]:
    """计算增量下载的日期范围"""
    # 1. 解析起始日期
    start = datetime.strptime(start_date, "%Y-%m-%d").date()

    # 2. 获取品种的最新数据日期
    latest_date = get_latest_data_date(symbol, interval)

    # 3. 确定实际起始日期
    if latest_date and latest_date >= start:
        # 从最新数据的下一个交易日开始
        actual_start = get_next_trading_day(latest_date)
    else:
        # 从指定起始日期开始
        actual_start = start

    # 4. 结束日期为最新交易日
    end = get_latest_trading_day()

    return actual_start, end
```

**数据去重规则**：
- **时间戳去重**：相同时间戳的数据只保留最新的
- **合并策略**：新下载数据覆盖本地相同时间的数据
- **完整性检查**：确保数据连续性，发现缺失自动补全

### 2.2 并发控制规则

#### 2.2.1 动态并发调整

**基础并发配置**：
```python
# 默认并发配置
DEFAULT_CONFIG = {
    "max_processes": 16,        # 最大进程数
    "coroutines_per_process": 40,  # 每进程协程数
    "max_total_connections": 2000,  # 总连接数上限
    "batch_size": 100          # 批次大小
}
```

**负载均衡调整规则**：
- **CPU瓶颈**：减少进程数，增加每进程协程数
- **内存瓶颈**：减少批次大小，限制并发数
- **磁盘瓶颈**：减少总并发数，增加批次大小
- **网络瓶颈**：限制连接数，使用更保守的配置

#### 2.2.2 任务分配规则

**任务分片策略**：
```python
def split_tasks_for_processes(symbols: List[str], intervals: List[str], num_processes: int) -> List[List]:
    """将下载任务分配给多个进程"""
    # 1. 生成所有任务组合
    all_tasks = [(symbol, interval) for symbol in symbols for interval in intervals]

    # 2. 按品种代码哈希分配（确保同一品种的不同周期在同一进程）
    process_tasks = [[] for _ in range(num_processes)]
    for symbol, interval in all_tasks:
        process_idx = hash(symbol) % num_processes
        process_tasks[process_idx].append((symbol, interval))

    return process_tasks
```

**连接生命周期管理规则**：
```python
# 🆕 v3.7: 创建连接生命周期管理器
conn_manager = ConnectionLifecycleManager(worker_id, logger)

# 🆕 v3.7：使用ConnectionLifecycleManager批量创建连接
connection_list = await conn_manager.create_connections(
    servers=server_list_local,
    timeout=timeout,
    health_check=False,  # K线下载优先速度，不做健康检查
)

# 转换为字典（兼容现有代码）
connections = {server_list_local[i]: client for i, client in enumerate(connection_list)}
```

**连接管理规则说明**：
- **统一管理**：使用`ConnectionLifecycleManager`统一管理连接的创建和关闭
- **批量创建**：一次性批量创建所有连接（提高效率，减少连接建立时间）
- **健康检查**：K线下载不做健康检查（优先速度，健康检查会增加延迟）
- **错误处理**：连接创建失败时自动重试或跳过（记录DEBUG日志，不影响其他连接）
- **资源清理**：连接关闭时确保资源被正确释放（在finally块中处理）

**跨进程通信规则**：
```python
# 多进程共享对象（使用multiprocessing.Manager）
self.manager = Manager()
self.task_queue = self.manager.Queue()        # 任务队列
self.result_queue = self.manager.Queue()      # 结果队列
self.metrics_queue = self.manager.Queue()     # 监控指标队列（独立）
self.progress_queue = self.manager.Queue()    # 进度队列
self.stop_event = self.manager.Event()       # 停止事件
self.pause_event = self.manager.Event()      # 暂停事件
```

**通信规则说明**：
- **队列类型**：使用`multiprocessing.Manager.Queue`（而非native_ipc，Manager更成熟稳定）
- **队列分类**：
  - `task_queue`：待下载任务队列（主进程 → Worker进程）
  - `result_queue`：下载结果队列（Worker进程 → 主进程）
  - `metrics_queue`：监控指标队列（Worker进程 → 主进程，独立队列避免阻塞）
  - `progress_queue`：进度更新队列（Worker进程 → 主进程）
- **事件同步**：使用`Event`进行进程间同步（stop_event、pause_event）
- **背压控制**：队列满时使用`_safe_put_queue`跳过任务，记录为"skipped"（避免无限等待）

**监控指标收集规则**：
```python
# 🆕 v3.6: 启动lag监控（使用独立的metrics_queue）
lag_monitor_task = asyncio.create_task(
    LagMonitor.monitor_and_report(
        metrics_queue=metrics_queue,  # 使用独立的监控队列
        worker_id=worker_id,
        stop_event=stop_event,
        interval_seconds=0.3,  # 监控频率0.3秒
    )
)

# 主进程处理监控指标
while True:
    try:
        if self.metrics_queue:
            msg = self.metrics_queue.get_nowait()
            LagMonitor.process_lag_message(msg, self.load_balancer, self.logger)
    except queue.Empty:
        break
```

**监控规则说明**：
- **监控指标类型**：`event_loop_lag`（事件循环延迟），用于检测协程阻塞
- **收集频率**：0.3秒（高频监控，及时发现问题）
- **处理流程**：Worker进程收集 → metrics_queue → 主进程处理 → LoadBalancer动态调整
- **用途**：用于LoadBalancer动态调整并发数（根据event_loop_lag自动调整协程数）

**任务结果保存规则**：
```python
# 下载成功，保存结果
if data is not None and not data.empty:
    # 🆕 背压控制: 使用_safe_put_queue代替原来的无限等待
    success = await asyncio.to_thread(
        _safe_put_queue,
        result_queue,
        (f"{symbol}_{interval}", data.to_dict("records")),  # 结果格式
        timeout=1.0,
        queue_name="result_queue",
        worker_id=worker_id,
    )
    if success:
        await asyncio.to_thread(progress_queue.put, (symbol, interval, "success"))
        processed += 1
    else:
        # 队列满，跳过该任务
        await asyncio.to_thread(progress_queue.put, (symbol, interval, "skipped"))
```

**结果保存规则说明**：
- **结果格式**：`(symbol_interval, data_dict)`字典格式，主进程转换为DataFrame
- **保存时机**：主进程收集结果后保存到StorageManager（不在worker进程保存，避免多进程写冲突）
- **背压控制**：队列满时跳过任务，记录为"skipped"（避免无限等待，确保其他任务能继续执行）
- **主进程收集流程**：从result_queue收集结果 → 转换为DataFrame → 保存到Parquet文件（使用native_iocp异步写入）

**暂停/恢复机制规则**：
```python
# 等待暂停事件（每个协程循环检查）
while not pause_event.is_set():
    if stop_event.is_set():
        break
    await asyncio.sleep(0.1)  # 每0.1秒检查一次

def pause_download(self):
    """暂停当前下载任务"""
    if self.pause_event:
        self.pause_event.clear()  # 清除事件 = 暂停
        self.logger.info("已发送暂停信号")

def resume_download(self):
    """恢复暂停的下载任务"""
    if self.pause_event:
        self.pause_event.set()  # 设置事件 = 恢复
        self.logger.info("已发送恢复信号")
```

**暂停/恢复规则说明**：
- **暂停机制**：使用`pause_event.clear()`暂停所有协程（每个协程循环检查pause_event）
- **恢复机制**：使用`pause_event.set()`恢复所有协程（立即继续下载）
- **资源占用**：暂停时继续占用连接（不释放资源，恢复时无需重新创建连接）
- **检查频率**：每0.1秒检查一次pause_event（确保快速响应）
- **用户体验**：暂停时立即响应，恢复时立即继续下载（无需等待）

**停止机制规则**：
```python
def stop_download(self):
    """停止当前下载任务"""
    if self.stop_event:
        self.stop_event.set()  # 设置事件 = 停止
        self.logger.info("已发送停止信号")

# 在worker进程中检查停止事件
while not stop_event.is_set():
    # ... 下载逻辑 ...
    if stop_event.is_set():
        break
```

**停止规则说明**：
- **停止机制**：使用`stop_event.set()`停止所有协程（每个协程循环检查stop_event）
- **资源清理**：停止时确保连接被正确关闭（在finally块中处理），清理进程和队列
- **进程终止**：使用`terminate()`强制终止进程（每个进程join超时1秒，避免无限等待）
- **用户体验**：停止时立即响应，确保资源被正确释放

**错误处理和重试规则**：
```python
# 下载失败处理
except Exception as e:
    logger.debug(
        f"Worker {worker_id} 连接 {conn_id} 下载 {symbol}_{interval} 失败: {e}"
    )
    await asyncio.to_thread(progress_queue.put, (symbol, interval, "failed"))
    failed += 1

# 服务器连接失败，尝试下一个服务器
except Exception as e:
    logger.warning(
        "[Phase1] Worker %s 连接%s 服务器%s失败，尝试下一个服务器: %s",
        worker_id, conn_id, _current_server, e
    )
    # 切换到下一个备用服务器
    current_client = await _get_next_server_client(...)
```

**错误处理规则说明**：
- **错误类型**：下载失败、服务器连接失败、队列满
- **重试策略**：下载失败不重试（记录为failed，继续下一个任务），服务器连接失败自动切换到下一个备用服务器
- **故障切换**：自动切换到下一个备用服务器（无需人工干预）
- **日志记录**：错误日志记录为DEBUG级别（避免日志轰炸，只在必要时记录WARNING）

**进度监控超时规则**：
```python
def _monitor_progress_and_collect_results(self, total_tasks: int, progress_callback):
    """改进的监控和结果收集"""
    timeout_count = 0
    max_timeout_count = 600  # ✅ 60秒（600 * 0.1秒），给足时间下载

    while completed < total_tasks:
        try:
            progress_data = self.progress_queue.get(timeout=0.1)
            completed += 1
            timeout_count = 0  # 重置超时计数
        except queue.Empty:
            timeout_count += 1
            if timeout_count >= max_timeout_count:
                self.logger.warning(
                    f"进度监控超时（{max_timeout_count * 0.1}秒），已完成: {completed}/{total_tasks}"
                )
                # ✅ 检查所有进程状态并诊断
                alive_processes = [p for p in self.processes if p.is_alive()]
                if not alive_processes:
                    self.logger.warning("所有进程已结束，但任务未完成！强制退出监控")
                    break
                # ✅ 重置超时计数，继续等待（进程还在工作）
                timeout_count = 0
```

**进度监控规则说明**：
- **超时机制**：60秒无进度更新则检查进程状态（给足时间下载，避免误判）
- **进程状态检查**：超时后检查所有进程是否存活，如果全部死亡则退出监控
- **队列诊断**：超时时检查队列状态（task_queue、progress_queue、result_queue），帮助排查问题
- **错误处理**：进程仍在运行则重置超时计数，继续等待（避免误判为超时）

**任务详细日志记录规则**：
```python
# 初始化任务详细日志记录器
task_logger = TaskDetailLogger(worker_id=worker_id)

# 记录单个任务详情
task_logger.log_download_result(
    symbol=symbol,
    interval=interval,
    result=result,
    error=error,
    server=server,
    elapsed=elapsed_time,
    phase="Phase1",
)
```

**日志记录规则说明**：
- **日志格式**：CSV格式，包含symbol、interval、result、error、server、elapsed、phase等字段
- **保存位置**：按worker_id区分，保存到不同的日志文件（便于追踪不同进程的任务）
- **日志内容**：记录每个任务的详细信息（成功/失败、耗时、服务器、阶段等）
- **用途**：用于任务性能分析、错误排查、服务器质量评估（帮助优化下载策略）

**进度同步规则**：
- **进度报告频率**：每完成100个任务或每5秒报告一次
- **跨进程同步**：使用multiprocessing.Manager.Queue进行进度同步（而非native_ipc）
- **异常处理**：进程异常时其他进程继续执行（异常隔离）

### 2.3 数据下载实现细节

> **架构设计参考**：多进程架构、异步操作、错误处理等技术设计请参考 [最佳实践文档 - 2.2 data_acquisition.py 详细设计](./data_module_vnpy新架构最佳实践cursor版.md#223-详细设计)

#### 2.3.1 下载流程实现

**完整下载流程**：
1. **配置获取** → LoadBalancer获取最优并发配置
2. **任务分配** → 按品种哈希分配到不同进程
3. **两段式下载** → IPv4池主要下载，IPv6池处理剩余任务
4. **进度同步** → 跨进程实时同步下载进度
5. **结果收集** → 主进程收集并保存下载结果

#### 2.3.2 任务管理策略

**暂停/恢复机制**：通过共享事件控制所有协程的暂停和恢复
**停止机制**：优雅停止，确保资源正确释放
**进度监控**：60秒超时检查，避免无限等待

---

## 三、数据验证业务规则

> **架构设计参考**：验证器架构、多进程设计请参考 [最佳实践文档 - 2.4 data_quality.py](./data_module_vnpy新架构最佳实践cursor版.md#24-data_qualitypy---数据质量管理模块)

### 3.1 微观架构设计

#### 3.1.1 验证器组合架构

**设计目标**:
- 将数据验证逻辑模块化为多个独立验证器
- 每个验证器专注于一个验证维度
- 支持验证结果的聚合和评分计算
- 便于扩展和测试

**核心类设计**:

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import date
import pandas as pd

@dataclass
class ValidationError:
    """验证错误数据模型"""
    type: str  # 错误类型
    severity: str  # 严重程度: error/warning
    message: str  # 错误消息
    date: Optional[date] = None  # 相关日期
    column: Optional[str] = None  # 相关列
    value: Optional[Any] = None  # 错误值
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ValidationResult:
    """验证结果数据模型"""
    validator_name: str
    is_valid: bool
    score: float  # 0-100分
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)

class BaseValidator(ABC):
    """验证器基类"""
    
    @abstractmethod
    def validate(self, df: pd.DataFrame, context: 'ValidationContext') -> ValidationResult:
        """执行验证
        
        Args:
            df: 待验证的DataFrame
            context: 验证上下文(共享数据)
            
        Returns:
            验证结果
        """
        pass
    
    @abstractmethod
    def get_validator_name(self) -> str:
        """获取验证器名称"""
        pass
    
    @abstractmethod
    def get_weight(self) -> float:
        """获取验证器权重(0-1)"""
        pass

class FormatValidator(BaseValidator):
    """格式验证器"""
    
    def validate(self, df: pd.DataFrame, context: 'ValidationContext') -> ValidationResult:
        """验证DataFrame格式
        
        验证项:
        - 必需列是否存在
        - 数据类型是否正确
        - 是否存在空值
        """
        errors = []
        warnings = []
        
        # 1. 必需列检查
        required_columns = ['datetime', 'open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            errors.append(ValidationError(
                type="missing_columns",
                severity="error",
                message=f"缺少必需列: {missing_columns}"
            ))
        
        # 2. 数据类型检查
        if 'datetime' in df.columns:
            if not pd.api.types.is_datetime64_any_dtype(df['datetime']):
                errors.append(ValidationError(
                    type="invalid_datetime",
                    severity="error",
                    message="datetime列不是日期时间类型"
                ))
        
        # 3. 数值列检查
        numeric_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_columns:
            if col in df.columns:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    errors.append(ValidationError(
                        type="invalid_numeric",
                        severity="error",
                        column=col,
                        message=f"{col}列不是数值类型"
                    ))
                
                # 4. 空值检查
                elif df[col].isna().any():
                    na_count = df[col].isna().sum()
                    errors.append(ValidationError(
                        type="null_values",
                        severity="error",
                        column=col,
                        message=f"{col}列包含{na_count}个空值"
                    ))
        
        # 计算评分
        score = 100.0 if not errors else max(0, 100 - len(errors) * 20)
        
        return ValidationResult(
            validator_name=self.get_validator_name(),
            is_valid=len(errors) == 0,
            score=score,
            errors=errors,
            warnings=warnings,
            statistics={'total_columns': len(df.columns)}
        )
    
    def get_validator_name(self) -> str:
        return "格式验证器"
    
    def get_weight(self) -> float:
        return 0.3  # 30%权重

class LogicValidator(BaseValidator):
    """逻辑验证器"""
    
    def validate(self, df: pd.DataFrame, context: 'ValidationContext') -> ValidationResult:
        """验证OHLC逻辑关系
        
        验证项:
        - 最高价 >= 最低价
        - 最高价 >= 开盘价/收盘价
        - 最低价 <= 开盘价/收盘价
        - 价格合理性
        """
        errors = []
        warnings = []
        
        if all(col in df.columns for col in ['open', 'high', 'low', 'close']):
            # 1. 最高价 >= 最低价
            invalid_high_low = df[df['high'] < df['low']]
            for idx, row in invalid_high_low.iterrows():
                try:
                    idx_date = pd.Timestamp(idx).date() if pd.notna(idx) else None
                except (ValueError, TypeError):
                    idx_date = None
                
                errors.append(ValidationError(
                    type="high_low_error",
                    severity="error",
                    date=idx_date,
                    message=f"最高价小于最低价: high={row['high']}, low={row['low']}"
                ))
            
            # 2. 最高价 >= 开盘价/收盘价
            invalid_high_open = df[df['high'] < df['open']]
            invalid_high_close = df[df['high'] < df['close']]
            
            if not invalid_high_open.empty:
                errors.append(ValidationError(
                    type="high_less_than_open",
                    severity="error",
                    message=f"最高价小于开盘价,共{len(invalid_high_open)}条"
                ))
            
            # 3. 价格合理性检查(警告级别)
            invalid_open = df[df['open'] <= 0]
            invalid_close = df[df['close'] <= 0]
            
            if not invalid_open.empty:
                warnings.append(ValidationError(
                    type="invalid_price",
                    severity="warning",
                    message=f"存在开盘价<=0的情况,共{len(invalid_open)}条"
                ))
        
        # 计算评分
        total_errors = len(errors)
        score = 100.0 if total_errors == 0 else max(0, 100 - total_errors * 10)
        
        return ValidationResult(
            validator_name=self.get_validator_name(),
            is_valid=len(errors) == 0,
            score=score,
            errors=errors,
            warnings=warnings,
            statistics={'total_rows': len(df)}
        )
    
    def get_validator_name(self) -> str:
        return "逻辑验证器"
    
    def get_weight(self) -> float:
        return 0.2  # 20%权重

class CompletenessValidator(BaseValidator):
    """完整性验证器"""
    
    def validate(self, df: pd.DataFrame, context: 'ValidationContext') -> ValidationResult:
        """验证数据完整性
        
        验证项:
        - 交易日数据缺失
        - 数据记录数量
        """
        errors = []
        warnings = []
        
        # 1. 计算有效起始日期
        symbol = context.current_symbol
        effective_start = self._compute_effective_start_date(
            symbol=symbol,
            data_start=df['datetime'].min().date() if not df.empty else None,
            base_date=context.base_date,
            ipo_dates=context.ipo_dates
        )
        
        # 2. 获取期间内所有交易日
        check_end_date = min(df['datetime'].max().date() if not df.empty else date.today(),
                            context.latest_trading_day)
        
        if effective_start > check_end_date:
            # 日期范围异常
            return ValidationResult(
                validator_name=self.get_validator_name(),
                is_valid=False,
                score=0,
                errors=[ValidationError(
                    type="date_range_error",
                    severity="error",
                    message=f"日期范围异常: 有效起点({effective_start}) > 检测终点({check_end_date})"
                )]
            )
        
        expected_trading_days = context.get_trading_days_in_range(effective_start, check_end_date)
        actual_dates = set(df['datetime'].dt.date)
        
        # 3. 找出缺失的交易日
        missing_dates = [d for d in expected_trading_days if d not in actual_dates]
        
        if missing_dates:
            errors.append(ValidationError(
                type="missing_trading_days",
                severity="error",
                message=f"缺失{len(missing_dates)}个交易日"
            ))
        
        # 4. 计算完整性评分
        if expected_trading_days:
            completeness = ((len(expected_trading_days) - len(missing_dates)) / 
                          len(expected_trading_days)) * 100
        else:
            completeness = 0
        
        return ValidationResult(
            validator_name=self.get_validator_name(),
            is_valid=len(missing_dates) == 0,
            score=completeness,
            errors=errors,
            warnings=warnings,
            statistics={
                'expected_days': len(expected_trading_days),
                'actual_days': len(actual_dates),
                'missing_days': len(missing_dates)
            }
        )
    
    def _compute_effective_start_date(self, symbol, data_start, base_date, ipo_dates) -> date:
        """计算有效起始日期"""
        ipo_date = ipo_dates.get(symbol) if symbol else None
        
        candidates = []
        if ipo_date:
            candidates.append(ipo_date)
        if data_start:
            candidates.append(data_start)
        if base_date:
            candidates.append(base_date)
        
        return max(candidates) if candidates else date(2020, 1, 1)
    
    def get_validator_name(self) -> str:
        return "完整性验证器"
    
    def get_weight(self) -> float:
        return 0.3  # 30%权重

class FreshnessValidator(BaseValidator):
    """新鲜度验证器"""
    
    def validate(self, df: pd.DataFrame, context: 'ValidationContext') -> ValidationResult:
        """验证数据新鲜度
        
        验证项:
        - 数据最新日期与最新交易日的滞后天数
        """
        errors = []
        warnings = []
        
        if df.empty:
            return ValidationResult(
                validator_name=self.get_validator_name(),
                is_valid=False,
                score=0,
                errors=[ValidationError(
                    type="empty_data",
                    severity="error",
                    message="数据为空"
                )]
            )
        
        # 1. 获取数据最新日期
        latest_data_date = df['datetime'].dt.date.max()
        latest_trading_day = context.latest_trading_day
        
        # 2. 计算滞后天数(使用粗略估算)
        if latest_data_date >= latest_trading_day:
            gap_days = 0
        else:
            calendar_gap = (latest_trading_day - latest_data_date).days
            gap_days = max(0, int(calendar_gap / 1.4))  # 粗略估算
        
        # 3. 判断新鲜度
        is_fresh = gap_days <= 1  # 允许1个交易日延迟
        
        # 4. 计算评分
        if gap_days == 0:
            score = 100.0
        elif gap_days <= 1:
            score = 95.0
        elif gap_days <= context.freshness_days_warning:
            score = max(70.0, 95.0 - (gap_days - 1) * 5)
        elif gap_days <= context.freshness_days_error:
            score = max(30.0, 70.0 - (gap_days - context.freshness_days_warning) * 10)
        else:
            score = 0.0
        
        # 5. 生成错误/警告
        if gap_days > context.freshness_days_error:
            errors.append(ValidationError(
                type="stale_data",
                severity="error",
                message=f"数据过旧,滞后{gap_days}个交易日"
            ))
        elif gap_days > context.freshness_days_warning:
            warnings.append(ValidationError(
                type="outdated_data",
                severity="warning",
                message=f"数据较旧,滞后{gap_days}个交易日"
            ))
        
        return ValidationResult(
            validator_name=self.get_validator_name(),
            is_valid=is_fresh,
            score=score,
            errors=errors,
            warnings=warnings,
            statistics={
                'latest_data_date': str(latest_data_date),
                'latest_trading_day': str(latest_trading_day),
                'gap_days': gap_days
            }
        )
    
    def get_validator_name(self) -> str:
        return "新鲜度验证器"
    
    def get_weight(self) -> float:
        return 0.2  # 20%权重
```

#### 3.1.2 验证结果聚合器架构

**设计目标**:
- 聚合多个验证器的结果
- 计算木桶理论评分（取最短板）
- 生成统一的质量报告

**核心类设计**:

```python
@dataclass
class AggregatedValidationResult:
    """聚合验证结果"""
    symbol: str
    interval: str
    overall_score: float  # 0-100
    is_valid: bool
    validator_results: Dict[str, ValidationResult] = field(default_factory=dict)
    total_errors: int = 0
    total_warnings: int = 0
    statistics: Dict[str, Any] = field(default_factory=dict)

class ValidationResultAggregator:
    """验证结果聚合器
    
    聚合多个验证器的结果,计算木桶理论评分（取最短板）
    """
    
    def __init__(self, validators: List[BaseValidator]):
        self.validators = validators
        # 木桶理论不需要权重总和
    
    def aggregate(self, results: Dict[str, ValidationResult], 
                 symbol: str, interval: str) -> AggregatedValidationResult:
        """聚合验证结果
        
        Args:
            results: 验证器名称 -> 验证结果
            symbol: 品种代码
            interval: 周期
            
        Returns:
            聚合验证结果
        """
        # 1. 计算木桶理论评分（取最短板）
        scores = []
        total_errors = 0
        total_warnings = 0
        
        for validator in self.validators:
            validator_name = validator.get_validator_name()
            result = results.get(validator_name)
            
            if result:
                scores.append(result.score)
                total_errors += len(result.errors)
                total_warnings += len(result.warnings)
        
        # 木桶理论：只看最短板
        overall_score = min(scores) if scores else 0
        
        # 2. 判断总体是否有效
        is_valid = all(r.is_valid for r in results.values())
        
        # 3. 生成统计信息
        statistics = {
            'validator_count': len(results),
            'passed_validators': sum(1 for r in results.values() if r.is_valid),
            'failed_validators': sum(1 for r in results.values() if not r.is_valid)
        }
        
        return AggregatedValidationResult(
            symbol=symbol,
            interval=interval,
            overall_score=overall_score,
            is_valid=is_valid,
            validator_results=results,
            total_errors=total_errors,
            total_warnings=total_warnings,
            statistics=statistics
        )
```

**使用示例**:

```python
class StatelessValidator:
    def __init__(self):
        # 初始化验证器列表
        self.validators = [
            FormatValidator(),
            LogicValidator(),
            CompletenessValidator(),
            FreshnessValidator()
        ]
        
        # 初始化聚合器
        self.aggregator = ValidationResultAggregator(self.validators)
    
    @staticmethod
    def validate_symbol(symbol: str, interval: str, df: pd.DataFrame, 
                       context: ValidationContext) -> AggregatedValidationResult:
        """验证单个品种"""
        # 设置当前品种
        context.current_symbol = symbol
        
        # 执行所有验证器
        results = {}
        for validator in self.validators:
            result = validator.validate(df, context)
            results[validator.get_validator_name()] = result
        
        # 聚合结果
        return self.aggregator.aggregate(results, symbol, interval)
```

**优势分析**:

1. **模块化**: 每个验证维度独立实现,易于扩展
2. **木桶理论评分**: 只看最短的板（min操作）
3. **统一接口**: 所有验证器遵循相同的接口规范
4. **结果聚合**: 自动聚合多个验证结果,生成综合报告
5. **便于测试**: 每个验证器可独立单元测试

---

### 3.2 数据完整性验证

#### 3.1.1 格式验证规则

**DataFrame结构验证**：
```python
def validate_dataframe_format(df: pd.DataFrame) -> List[Dict]:
    """验证DataFrame格式"""
    errors = []

    # 1. 必需列检查
    required_columns = ['datetime', 'open', 'high', 'low', 'close', 'volume']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        errors.append({
            "type": "missing_columns",
            "message": f"缺少必需列: {missing_columns}",
            "severity": "error"
        })

    # 2. 数据类型检查
    if 'datetime' in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df['datetime']):
            errors.append({
                "type": "invalid_datetime",
                "message": "datetime列不是日期时间类型",
                "severity": "error"
            })

    # 3. 数值列检查
    numeric_columns = ['open', 'high', 'low', 'close', 'volume']
    for col in numeric_columns:
        if col in df.columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                errors.append({
                    "type": "invalid_numeric",
                    "message": f"{col}列不是数值类型",
                    "severity": "error"
                })
            # 4. 空值检查（补充遗漏规则）
            elif df[col].isna().any():
                # 记录每个包含空值的行的详细信息
                na_rows = df[df[col].isna()]
                for idx, row in na_rows.iterrows():
                    try:
                        idx_date = pd.Timestamp(idx).date() if pd.notna(idx) else None
                    except (ValueError, TypeError):
                        idx_date = None
                    errors.append({
                        "type": "format_error",
                        "column": col,
                        "date": idx_date,
                        "value": None,
                        "message": f"{col}列包含空值",
                        "severity": "error"
                    })

    return errors
```

**数据范围验证**：
```python
def validate_data_ranges(df: pd.DataFrame) -> List[Dict]:
    """验证数据范围合理性"""
    errors = []

    # 1. 价格合理性检查
    price_columns = ['open', 'high', 'low', 'close']
    for col in price_columns:
        if col in df.columns:
            # 价格不能为负数或零
            invalid_prices = df[df[col] <= 0]
            if not invalid_prices.empty:
                errors.append({
                    "type": "invalid_price_range",
                    "message": f"{col}列存在非正数价格，共{len(invalid_prices)}条",
                    "severity": "error"
                })

            # 价格不能超过合理上限（如10000元）
            extreme_prices = df[df[col] > 10000]
            if not extreme_prices.empty:
                errors.append({
                    "type": "extreme_price",
                    "message": f"{col}列存在极端价格(>10000)，共{len(extreme_prices)}条",
                    "severity": "warning"
                })

    # 2. 成交量检查
    if 'volume' in df.columns:
        negative_volume = df[df['volume'] < 0]
        if not negative_volume.empty:
            errors.append({
                "type": "negative_volume",
                "message": f"成交量存在负数，共{len(negative_volume)}条",
                "severity": "error"
            })

    return errors
```

#### 3.1.2 逻辑验证规则

**OHLC逻辑验证**：
```python
def validate_ohlc_logic(df: pd.DataFrame) -> List[Dict]:
    """验证OHLC价格逻辑关系"""
    errors = []

    if all(col in df.columns for col in ['open', 'high', 'low', 'close']):
        # 1. 最高价 >= 最低价
        invalid_high_low = df[df['high'] < df['low']]
        if not invalid_high_low.empty:
            # 记录每条错误的详细信息（补充遗漏规则）
            for idx, row in invalid_high_low.iterrows():
                try:
                    idx_date = pd.Timestamp(idx).date() if pd.notna(idx) else None
                except (ValueError, TypeError):
                    idx_date = None
                errors.append({
                    "type": "high_low_error",
                    "date": idx_date,
                    "high": row['high'],
                    "low": row['low'],
                    "message": f"最高价小于最低价: high={row['high']}, low={row['low']}",
                    "severity": "error"
                })

        # 2. 最高价 >= 开盘价和收盘价
        invalid_high_open = df[df['high'] < df['open']]
        invalid_high_close = df[df['high'] < df['close']]

        if not invalid_high_open.empty:
            errors.append({
                "type": "high_less_than_open",
                "message": f"最高价小于开盘价，共{len(invalid_high_open)}条",
                "severity": "error"
            })

        if not invalid_high_close.empty:
            errors.append({
                "type": "high_less_than_close",
                "message": f"最高价小于收盘价，共{len(invalid_high_close)}条",
                "severity": "error"
            })

        # 3. 最低价 <= 开盘价和收盘价
        invalid_low_open = df[df['low'] > df['open']]
        invalid_low_close = df[df['low'] > df['close']]

        if not invalid_low_open.empty:
            errors.append({
                "type": "low_greater_than_open",
                "message": f"最低价大于开盘价，共{len(invalid_low_open)}条",
                "severity": "error"
            })

        if not invalid_low_close.empty:
            errors.append({
                "type": "low_greater_than_close",
                "message": f"最低价大于收盘价，共{len(invalid_low_close)}条",
                "severity": "error"
            })

        # 4. 价格合理性检查（警告级别，补充遗漏规则）
        invalid_open = df[df['open'] <= 0]
        invalid_close = df[df['close'] <= 0]
        if not invalid_open.empty or not invalid_close.empty:
            warnings = []
            if not invalid_open.empty:
                warnings.append(f"存在开盘价<=0的情况，共{len(invalid_open)}条")
            if not invalid_close.empty:
                warnings.append(f"存在收盘价<=0的情况，共{len(invalid_close)}条")
            # 注意：此规则在新架构中应返回warnings列表，而非errors

    return errors
```

### 3.2 数据完整性验证

#### 3.2.1 时间连续性验证

**交易日缺失检查**：
```python
def validate_trading_day_completeness(df: pd.DataFrame, symbol: str,
                                    date_range: Tuple[date, date],
                                    context: ValidationContext) -> Tuple[List[date], List[str]]:
    """检查交易日数据完整性"""
    start_date, end_date = date_range

    # 1. 计算有效起始日期（智能起点计算算法，补充遗漏规则）
    effective_start = compute_effective_start_date(
        symbol=symbol,
        data_start=start_date,
        base_date=context.base_date,
        ipo_dates=context.ipo_dates
    )
    # 智能起点计算逻辑：
    # - 如果IPO日期可用，使用IPO日期
    # - 否则使用max(数据起点, 基准日期)
    # - 如果都不可用，使用默认值2020-01-01

    # 2. 确定检测终点（不能超过最近一个交易日）
    check_end_date = min(end_date, context.latest_trading_day)

    # 3. 验证日期范围（补充遗漏规则）
    if effective_start > check_end_date:
        # 日期范围异常，统计并记录（每1000个任务输出一次汇总）
        return [], ["日期范围异常: 有效起点大于检测终点"]

    # 4. 获取期间内所有交易日
    expected_trading_days = get_trading_days_in_range(effective_start, check_end_date, context.trading_days)

    # 5. 获取实际数据日期
    if df.empty:
        return list(expected_trading_days), ["数据为空"]

    actual_dates = set(df['datetime'].dt.date)

    # 6. 过滤停牌日期：通过成交量识别停牌（有价无量，补充遗漏规则）
    # 停牌特征：有价无量（价格存在但成交量为0或极低）
    # 停牌判断逻辑：
    # - 成交量 < 100股
    # - 前后交易日有正常成交量（>= 100股）
    # - 从expected_dates中排除，避免被统计为数据缺失
    if 'volume' in df.columns and expected_trading_days:
        zero_volume_dates = set()
        trading_dates_list = sorted(expected_trading_days)

        for date_val in actual_dates:
            if date_val not in expected_trading_days:
                continue

            # 查找该日期的成交量
            date_mask = df['datetime'].dt.date == date_val
            date_rows = df[date_mask]

            if not date_rows.empty:
                max_volume = date_rows['volume'].max()

                # 如果成交量 < 100股，检查前后交易日
                if max_volume < 100:
                    try:
                        date_idx = trading_dates_list.index(date_val)
                        has_normal_prev_volume = False
                        has_normal_next_volume = False

                        # 检查前一个交易日
                        if date_idx > 0:
                            prev_date = trading_dates_list[date_idx - 1]
                            if prev_date in actual_dates:
                                prev_mask = df['datetime'].dt.date == prev_date
                                prev_volume = df[prev_mask]['volume'].max()
                                if prev_volume >= 100:
                                    has_normal_prev_volume = True

                        # 检查后一个交易日
                        if date_idx < len(trading_dates_list) - 1:
                            next_date = trading_dates_list[date_idx + 1]
                            if next_date in actual_dates:
                                next_mask = df['datetime'].dt.date == next_date
                                next_volume = df[next_mask]['volume'].max()
                                if next_volume >= 100:
                                    has_normal_next_volume = True

                        # 如果前后交易日有正常成交量，当前日期可能是停牌
                        if has_normal_prev_volume or has_normal_next_volume:
                            zero_volume_dates.add(date_val)
                    except (ValueError, IndexError):
                        pass

        # 从expected_dates中排除有价无量的日期
        if zero_volume_dates:
            expected_trading_days = set(expected_trading_days) - zero_volume_dates
            expected_trading_days = sorted(expected_trading_days)

    # 7. 找出缺失的交易日
    missing_dates = [d for d in expected_trading_days if d not in actual_dates]

    # 8. 生成缺失原因分析
    missing_reasons = []
    if missing_dates:
        # 检查是否是IPO后的缺失
        ipo_date = context.ipo_dates.get(symbol)
        if ipo_date:
            pre_ipo_missing = [d for d in missing_dates if d < ipo_date]
            post_ipo_missing = [d for d in missing_dates if d >= ipo_date]

            if pre_ipo_missing:
                missing_reasons.append(f"IPO前缺失{len(pre_ipo_missing)}个交易日")
            if post_ipo_missing:
                missing_reasons.append(f"IPO后缺失{len(post_ipo_missing)}个交易日")
        else:
            missing_reasons.append(f"缺失{len(missing_dates)}个交易日")

    return missing_dates, missing_reasons
```

#### 3.2.2 数据新鲜度验证

**滞后天数计算**：
```python
def calculate_data_freshness(df: pd.DataFrame, context: ValidationContext) -> Dict[str, Any]:
    """计算数据新鲜度"""
    if df.empty:
        return {
            "gap_days": -1,
            "latest_date": None,
            "is_fresh": False,
            "freshness_score": 0.0
        }

    # 1. 获取数据最新日期
    latest_data_date = df['datetime'].dt.date.max()

    # 2. 获取最新交易日（使用网络时间）
    latest_trading_day = context.latest_trading_day

    # 3. 计算滞后天数
    if latest_data_date >= latest_trading_day:
        gap_days = 0  # 数据是最新的
    else:
        # 计算交易日滞后（性能优化版，补充遗漏规则）
        # 优化算法：使用日历天数 / 1.4 估算交易日天数
        # 这个估算对于判断数据是否过时（>1天）已经足够准确，避免每次都创建事件循环
        calendar_gap = (latest_trading_day - latest_data_date).days
        trading_gap = int(calendar_gap / 1.4)  # 粗略估算：日历天数 / 1.4 ≈ 交易日天数
        gap_days = max(0, trading_gap)

        # 注意：如果需要精确计算，可以使用count_trading_days_between，但性能较差

    # 4. 判断新鲜度（补充遗漏规则：允许1个交易日的延迟）
    # gap_days <= 1 为最新（允许1个交易日的延迟）
    is_fresh = gap_days <= 1

    # 5. 计算新鲜度评分
    if gap_days == 0:
        freshness_score = 100.0
    elif gap_days <= 1:  # 更新阈值，允许1个交易日延迟
        freshness_score = 95.0
    elif gap_days <= context.freshness_days_warning:
        freshness_score = max(70.0, 95.0 - (gap_days - 1) * 5)
    elif gap_days <= context.freshness_days_error:
        freshness_score = max(30.0, 70.0 - (gap_days - context.freshness_days_warning) * 10)
    else:
        freshness_score = 0.0

    return {
        "gap_days": gap_days,
        "latest_date": latest_data_date,
        "is_fresh": is_fresh,
        "freshness_score": freshness_score
    }
```

### 3.3 验证上下文管理

#### 3.3.1 共享数据准备

**ValidationContext构建规则**：
```python
def build_validation_context() -> ValidationContext:
    """构建验证上下文"""
    # 1. 获取IPO日期数据（补充遗漏规则：IPO日期验证）
    ipo_cache = get_ipo_cache()
    ipo_dates = {}
    today = get_real_date()  # 使用网络时间作为基准

    for symbol in get_all_symbols():
        ipo_date, _ = ipo_cache.get(symbol)
        if ipo_date:
            # IPO日期合法性验证（补充遗漏规则）
            # 规则1：不能超过今天+30天
            if ipo_date > today + timedelta(days=30):
                logger.warning(f"品种 {symbol} IPO日期异常（未来日期）: {ipo_date}，跳过")
                continue

            # 规则2：不能早于1990年
            if ipo_date.year < 1990:
                logger.warning(f"品种 {symbol} IPO日期异常（过早）: {ipo_date}，跳过")
                continue

            ipo_dates[symbol] = ipo_date

    # 2. 获取交易日历
    trading_days = get_trading_calendar()

    # 3. 获取最新交易日（使用网络时间）
    latest_trading_day = get_latest_trading_day()

    # 4. 设置基准日期
    base_date = get_real_date()  # 使用网络时间

    return ValidationContext(
        ipo_dates=ipo_dates,
        trading_days=set(trading_days),
        latest_trading_day=latest_trading_day,
        base_date=base_date,
        min_records_threshold=100,
        freshness_days_warning=7,
        freshness_days_error=30
    )
```

**智能起点计算算法**（补充遗漏规则）：
```python
def compute_effective_start_date(
    symbol: Optional[str],
    data_start: Optional[date],
    base_date: Optional[date],
    ipo_dates: Dict[str, date]
) -> date:
    """计算有效起始日期（智能起点计算算法）

    不使用推测，通过逻辑计算得出唯一正确值。

    逻辑：
    1. 如果IPO日期可用，使用IPO日期
    2. 否则使用max(数据起点, 基准日期)
    3. 如果都不可用，使用默认值2020-01-01

    Args:
        symbol: 品种代码（可选）
        data_start: 本地数据起点
        base_date: 配置的基准日期
        ipo_dates: IPO日期字典

    Returns:
        有效起始日期
    """
    # 1. 尝试获取IPO日期
    ipo_date = ipo_dates.get(symbol) if symbol else None

    # 2. 计算有效起点
    candidates = []

    if ipo_date:
        candidates.append(ipo_date)

    if data_start:
        candidates.append(data_start)

    if base_date:
        candidates.append(base_date)

    # 3. 选择最大值（最近的日期）
    if candidates:
        effective_start = max(candidates)
        return effective_start
    else:
        # 4. 所有都不可用，使用默认值
        default_date = date(2020, 1, 1)
        return default_date
```

**日期范围异常处理**（补充遗漏规则）：
```python
class DateRangeExceptionHandler:
    """日期范围异常处理器

    用于统计和记录日期范围异常，避免批量扫描时日志刷屏。
    规则：每1000个任务输出一次汇总信息。
    """
    def __init__(self):
        self.exception_count = 0
        self.exception_symbols = []

    def reset(self):
        """重置统计（在新的扫描任务开始时调用）"""
        self.exception_count = 0
        self.exception_symbols = []

    def record_exception(self, symbol: str):
        """记录异常"""
        self.exception_count += 1
        self.exception_symbols.append(symbol)

        # 每1000个任务输出一次汇总
        if self.exception_count % 1000 == 0:
            unique_symbols = len(set(self.exception_symbols[-1000:]))
            logger.warning(
                "日期范围异常统计: 已处理 %d 个任务，最近1000个任务中有 %d 个唯一品种异常",
                self.exception_count,
                unique_symbols
            )

    def log_final_stats(self):
        """输出最终的日期范围异常统计"""
        if self.exception_count > 0:
            unique_symbols = len(set(self.exception_symbols))
            logger.info(
                "日期范围异常最终统计: 共 %d 个任务异常，涉及 %d 个唯一品种",
                self.exception_count,
                unique_symbols
            )
            self.reset()

### 3.4 数据验证实现细节

> **架构设计参考**：组件交互、状态管理、多进程验证等架构设计请参考 [最佳实践文档 - 2.4 data_quality.py 详细设计](./data_module_vnpy新架构最佳实践cursor版.md#243-详细设计要点)

#### 3.4.1 验证流程实现

**完整验证流程**：
1. **扫描阶段** → 扫描所有数据文件，生成验证任务列表
2. **验证阶段** → 多进程并发验证数据质量
3. **结果汇总** → 收集验证结果，生成质量报告
4. **缓存更新** → 缓存验证结果，避免重复验证
5. **事件发布** → 通知UI更新质量看板

#### 3.4.2 验证状态管理

**验证状态流转**：空闲 → 扫描 → 验证 → 完成
**暂停/恢复**：支持验证过程中的暂停和恢复操作
**进度跟踪**：实时跟踪验证进度和错误统计

---

## 四、缓存管理业务规则

> **架构设计参考**：缓存管理器架构请参考 [最佳实践文档 - 2.1 data_module.py - DailyCacheManager](./data_module_vnpy新架构最佳实践cursor版.md#21-data_modulepy---核心模块)

### 4.1 微观架构设计

#### 4.1.1 缓存策略架构

**设计目标**：
- 支持多种缓存失效策略（日期失效、LRU、TTL）
- 策略可组合、可替换
- 统一的缓存接口，隔离底层实现
- 支持性能监控和统计

**核心类设计**：

```python
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Optional, Dict
from pathlib import Path
import time
import logging

logger = logging.getLogger(__name__)

# ==================== 缓存策略抽象 ====================

class CacheStrategy(ABC):
    """缓存失效策略基类"""
    
    @abstractmethod
    def is_valid(self, cache_metadata: Dict[str, Any]) -> bool:
        """判断缓存是否有效
        
        Args:
            cache_metadata: 缓存元数据（包含创建时间、访问时间等）
            
        Returns:
            True表示缓存有效，False表示已失效
        """
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        pass


class DateBasedStrategy(CacheStrategy):
    """日期失效策略：次日0时失效"""
    
    def is_valid(self, cache_metadata: Dict[str, Any]) -> bool:
        """检查缓存日期是否为今天
        
        规则：
        - 缓存日期 = 今天 → 有效
        - 缓存日期 < 今天 → 失效
        - 缓存日期 > 今天 → 失效（异常情况）
        """
        cache_date_str = cache_metadata.get("cache_date")
        if not cache_date_str:
            return False
        
        try:
            cache_date = datetime.strptime(cache_date_str, "%Y-%m-%d").date()
            today = date.today()
            
            if cache_date == today:
                return True
            elif cache_date < today:
                logger.debug(f"缓存已过期: cache_date={cache_date}, today={today}")
                return False
            else:
                logger.warning(f"缓存日期异常（未来日期）: cache_date={cache_date}, today={today}")
                return False
                
        except ValueError as e:
            logger.error(f"缓存日期格式错误: {cache_date_str}, error={e}")
            return False
    
    def get_strategy_name(self) -> str:
        return "DateBasedStrategy"


class TTLStrategy(CacheStrategy):
    """TTL失效策略：超过指定时间失效"""
    
    def __init__(self, ttl_seconds: float):
        """初始化TTL策略
        
        Args:
            ttl_seconds: 缓存生存时间（秒）
        """
        self.ttl_seconds = ttl_seconds
    
    def is_valid(self, cache_metadata: Dict[str, Any]) -> bool:
        """检查缓存是否在TTL时间内
        
        规则：
        - (当前时间 - 创建时间) <= TTL → 有效
        - (当前时间 - 创建时间) > TTL → 失效
        """
        created_at = cache_metadata.get("created_at")
        if not created_at:
            return False
        
        elapsed = time.time() - created_at
        is_valid = elapsed <= self.ttl_seconds
        
        if not is_valid:
            logger.debug(
                f"TTL缓存已过期: elapsed={elapsed:.2f}s, ttl={self.ttl_seconds}s"
            )
        
        return is_valid
    
    def get_strategy_name(self) -> str:
        return f"TTLStrategy({self.ttl_seconds}s)"


class LRUStrategy(CacheStrategy):
    """LRU失效策略：最近最少使用"""
    
    def __init__(self, max_capacity: int):
        """初始化LRU策略
        
        Args:
            max_capacity: 最大缓存容量
        """
        self.max_capacity = max_capacity
        self.access_order = []  # 访问顺序列表
    
    def is_valid(self, cache_metadata: Dict[str, Any]) -> bool:
        """LRU策略不直接判定有效性，由CacheManager调用should_evict"""
        return True  # 默认有效，由容量控制淘汰
    
    def should_evict(self, current_size: int, cache_key: str) -> bool:
        """判断是否应该淘汰
        
        Args:
            current_size: 当前缓存大小
            cache_key: 缓存键
            
        Returns:
            True表示应该淘汰，False表示保留
        """
        if current_size <= self.max_capacity:
            return False
        
        # 检查是否是最少使用的
        if cache_key in self.access_order:
            # 如果是队列前部（最少使用），应该淘汰
            lru_key = self.access_order[0]
            return cache_key == lru_key
        
        return False
    
    def mark_accessed(self, cache_key: str):
        """标记缓存被访问
        
        规则：
        - 如果key已存在，移动到队尾（最近使用）
        - 如果key不存在，添加到队尾
        """
        if cache_key in self.access_order:
            self.access_order.remove(cache_key)
        self.access_order.append(cache_key)
    
    def get_lru_key(self) -> Optional[str]:
        """获取最少使用的key"""
        return self.access_order[0] if self.access_order else None
    
    def remove_key(self, cache_key: str):
        """从访问列表中移除key"""
        if cache_key in self.access_order:
            self.access_order.remove(cache_key)
    
    def get_strategy_name(self) -> str:
        return f"LRUStrategy(max={self.max_capacity})"


class CompositeStrategy(CacheStrategy):
    """组合策略：同时满足多个策略才有效"""
    
    def __init__(self, strategies: list[CacheStrategy]):
        """初始化组合策略
        
        Args:
            strategies: 策略列表
        """
        self.strategies = strategies
    
    def is_valid(self, cache_metadata: Dict[str, Any]) -> bool:
        """所有策略都有效才返回True"""
        for strategy in self.strategies:
            if not strategy.is_valid(cache_metadata):
                logger.debug(
                    f"组合策略失败于: {strategy.get_strategy_name()}"
                )
                return False
        return True
    
    def get_strategy_name(self) -> str:
        names = [s.get_strategy_name() for s in self.strategies]
        return f"CompositeStrategy({', '.join(names)})"


# ==================== 缓存存储抽象 ====================

class CacheStorage(ABC):
    """缓存存储抽象接口"""
    
    @abstractmethod
    def load(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """加载缓存数据
        
        Args:
            cache_key: 缓存键
            
        Returns:
            缓存对象（包含data和metadata），不存在返回None
        """
        pass
    
    @abstractmethod
    def save(self, cache_key: str, data: Any, metadata: Dict[str, Any]) -> bool:
        """保存缓存数据
        
        Args:
            cache_key: 缓存键
            data: 缓存数据
            metadata: 缓存元数据
            
        Returns:
            True表示保存成功
        """
        pass
    
    @abstractmethod
    def exists(self, cache_key: str) -> bool:
        """检查缓存是否存在"""
        pass
    
    @abstractmethod
    def delete(self, cache_key: str) -> bool:
        """删除缓存"""
        pass
    
    @abstractmethod
    def clear(self) -> int:
        """清空所有缓存
        
        Returns:
            清理的缓存数量
        """
        pass


class FileBasedStorage(CacheStorage):
    """文件存储实现"""
    
    def __init__(self, cache_dir: Path):
        """初始化文件存储
        
        Args:
            cache_dir: 缓存目录
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """获取缓存文件路径"""
        # 使用cache_key的hash作为文件名（避免特殊字符）
        import hashlib
        key_hash = hashlib.md5(cache_key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.json"
    
    def load(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """从文件加载缓存"""
        cache_path = self._get_cache_path(cache_key)
        
        if not cache_path.exists():
            return None
        
        try:
            import json
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_obj = json.load(f)
            return cache_obj
        except Exception as e:
            logger.error(f"加载缓存文件失败 ({cache_path}): {e}")
            return None
    
    def save(self, cache_key: str, data: Any, metadata: Dict[str, Any]) -> bool:
        """保存缓存到文件"""
        cache_path = self._get_cache_path(cache_key)
        
        try:
            import json
            cache_obj = {
                "data": data,
                "metadata": metadata
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_obj, f, ensure_ascii=False, indent=2, default=str)
            
            return True
        except Exception as e:
            logger.error(f"保存缓存文件失败 ({cache_path}): {e}")
            return False
    
    def exists(self, cache_key: str) -> bool:
        """检查缓存文件是否存在"""
        cache_path = self._get_cache_path(cache_key)
        return cache_path.exists()
    
    def delete(self, cache_key: str) -> bool:
        """删除缓存文件"""
        cache_path = self._get_cache_path(cache_key)
        
        try:
            if cache_path.exists():
                cache_path.unlink()
                return True
            return False
        except Exception as e:
            logger.error(f"删除缓存文件失败 ({cache_path}): {e}")
            return False
    
    def clear(self) -> int:
        """清空缓存目录"""
        count = 0
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
                count += 1
            logger.info(f"已清空缓存目录，删除 {count} 个文件")
            return count
        except Exception as e:
            logger.error(f"清空缓存目录失败: {e}")
            return count


class MemoryBasedStorage(CacheStorage):
    """内存存储实现"""
    
    def __init__(self):
        """初始化内存存储"""
        self._cache: Dict[str, Dict[str, Any]] = {}
        from threading import Lock
        self._lock = Lock()
    
    def load(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """从内存加载缓存"""
        with self._lock:
            return self._cache.get(cache_key)
    
    def save(self, cache_key: str, data: Any, metadata: Dict[str, Any]) -> bool:
        """保存缓存到内存"""
        with self._lock:
            self._cache[cache_key] = {
                "data": data,
                "metadata": metadata
            }
            return True
    
    def exists(self, cache_key: str) -> bool:
        """检查缓存是否存在"""
        with self._lock:
            return cache_key in self._cache
    
    def delete(self, cache_key: str) -> bool:
        """删除缓存"""
        with self._lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                return True
            return False
    
    def clear(self) -> int:
        """清空缓存"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"已清空内存缓存，删除 {count} 条记录")
            return count


# ==================== 统一缓存管理器 ====================

class UnifiedCacheManager:
    """统一缓存管理器
    
    组合策略模式和存储适配器模式，提供灵活的缓存管理。
    
    使用示例：
        # 创建日期失效缓存
        manager = UnifiedCacheManager(
            storage=FileBasedStorage(cache_dir),
            strategy=DateBasedStrategy()
        )
        
        # 保存缓存
        manager.set("stock_list", stock_data)
        
        # 加载缓存（自动验证有效性）
        data = manager.get("stock_list")
        
        # 创建LRU+TTL组合缓存
        lru_ttl_manager = UnifiedCacheManager(
            storage=MemoryBasedStorage(),
            strategy=CompositeStrategy([
                LRUStrategy(max_capacity=100),
                TTLStrategy(ttl_seconds=3600)
            ])
        )
    """
    
    def __init__(self, storage: CacheStorage, strategy: CacheStrategy):
        """初始化缓存管理器
        
        Args:
            storage: 缓存存储实现
            strategy: 缓存失效策略
        """
        self.storage = storage
        self.strategy = strategy
        
        # 统计信息
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "saves": 0
        }
    
    def get(self, cache_key: str, default: Any = None) -> Optional[Any]:
        """获取缓存数据（带有效性验证）
        
        Args:
            cache_key: 缓存键
            default: 默认值
            
        Returns:
            缓存数据，失效或不存在返回default
        """
        # 加载缓存对象
        cache_obj = self.storage.load(cache_key)
        
        if cache_obj is None:
            self._stats["misses"] += 1
            logger.debug(f"缓存未命中: {cache_key}")
            return default
        
        # 验证缓存有效性
        metadata = cache_obj.get("metadata", {})
        if not self.strategy.is_valid(metadata):
            self._stats["misses"] += 1
            logger.debug(f"缓存已失效: {cache_key}")
            # 删除失效缓存
            self.storage.delete(cache_key)
            return default
        
        # 缓存命中
        self._stats["hits"] += 1
        
        # LRU策略：标记访问
        if isinstance(self.strategy, LRUStrategy):
            self.strategy.mark_accessed(cache_key)
        elif isinstance(self.strategy, CompositeStrategy):
            for s in self.strategy.strategies:
                if isinstance(s, LRUStrategy):
                    s.mark_accessed(cache_key)
        
        return cache_obj.get("data")
    
    def set(self, cache_key: str, data: Any, extra_metadata: Optional[Dict] = None) -> bool:
        """设置缓存数据
        
        Args:
            cache_key: 缓存键
            data: 缓存数据
            extra_metadata: 额外的元数据
            
        Returns:
            True表示保存成功
        """
        # 构建元数据
        metadata = {
            "cache_date": date.today().strftime("%Y-%m-%d"),
            "created_at": time.time(),
            "accessed_at": time.time()
        }
        
        if extra_metadata:
            metadata.update(extra_metadata)
        
        # 保存缓存
        success = self.storage.save(cache_key, data, metadata)
        
        if success:
            self._stats["saves"] += 1
            
            # LRU策略：标记访问
            if isinstance(self.strategy, LRUStrategy):
                self.strategy.mark_accessed(cache_key)
            elif isinstance(self.strategy, CompositeStrategy):
                for s in self.strategy.strategies:
                    if isinstance(s, LRUStrategy):
                        s.mark_accessed(cache_key)
        
        return success
    
    def delete(self, cache_key: str) -> bool:
        """删除缓存"""
        success = self.storage.delete(cache_key)
        if success:
            self._stats["evictions"] += 1
            
            # LRU策略：从访问列表移除
            if isinstance(self.strategy, LRUStrategy):
                self.strategy.remove_key(cache_key)
            elif isinstance(self.strategy, CompositeStrategy):
                for s in self.strategy.strategies:
                    if isinstance(s, LRUStrategy):
                        s.remove_key(cache_key)
        
        return success
    
    def clear(self) -> int:
        """清空所有缓存"""
        count = self.storage.clear()
        self._stats["evictions"] += count
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0.0
        
        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "evictions": self._stats["evictions"],
            "saves": self._stats["saves"],
            "hit_rate": round(hit_rate, 2)
        }
```

**架构优势**：

1. **策略可替换**：
   - 轻松切换日期失效、LRU、TTL等策略
   - 支持策略组合（例如：LRU + TTL）
   - 新增策略只需实现`CacheStrategy`接口

2. **存储可适配**：
   - 支持文件存储、内存存储
   - 未来可扩展：Redis存储、数据库存储
   - 新增存储只需实现`CacheStorage`接口

3. **统一管理**：
   - 统一的get/set/delete接口
   - 自动处理缓存验证和淘汰
   - 内置统计功能，便于监控

4. **易于测试**：
   - 策略和存储可独立单元测试
   - 可注入Mock对象进行测试
   - 统计数据便于验证行为

#### 4.1.2 使用示例

**场景1：品种列表缓存（日期失效）**：
```python
from pathlib import Path

# 创建日期失效缓存管理器
cache_dir = Path("./cache")
stock_cache = UnifiedCacheManager(
    storage=FileBasedStorage(cache_dir),
    strategy=DateBasedStrategy()
)

# 保存品种列表
stock_list = fetch_stock_list_from_tdx()
stock_cache.set("stock_list_classified", stock_list)

# 加载品种列表（次日自动失效）
cached_list = stock_cache.get("stock_list_classified")
if cached_list is None:
    # 缓存失效，重新获取
    cached_list = fetch_stock_list_from_tdx()
    stock_cache.set("stock_list_classified", cached_list)
```

**场景2：DataFrame缓存（LRU + TTL组合）**：
```python
# 创建组合策略缓存
df_cache = UnifiedCacheManager(
    storage=MemoryBasedStorage(),
    strategy=CompositeStrategy([
        LRUStrategy(max_capacity=64),  # 最多缓存64个DataFrame
        TTLStrategy(ttl_seconds=3600)  # 1小时TTL
    ])
)

# 缓存DataFrame
df_cache.set("000001.SZ_1d", dataframe)

# 获取DataFrame（自动验证LRU和TTL）
df = df_cache.get("000001.SZ_1d")
```

**场景3：服务器池缓存（仅日期失效）**：
```python
server_cache = UnifiedCacheManager(
    storage=FileBasedStorage(cache_dir / "server_pool"),
    strategy=DateBasedStrategy()
)

# 缓存测速结果
server_cache.set("tdx_servers_sorted", sorted_servers)

# 获取缓存的服务器池
servers = server_cache.get("tdx_servers_sorted")
```

### 4.2 缓存业务规则

#### 4.2.1 日期失效缓存规则

**失效判断规则**：
- **缓存日期 = 今天** → 有效
- **缓存日期 < 今天** → 失效，自动删除
- **缓存日期 > 今天** → 异常，记录警告并删除
- **缺少cache_date字段** → 失效，自动删除

**应用场景**：
- 品种列表缓存（每日更新）
- 服务器池缓存（每日测速）
- 交易日历缓存（每日更新）
- IPO日期缓存（每日同步）

#### 4.2.2 LRU缓存规则

**淘汰规则**：
- 缓存满时，淘汰最久未访问的条目
- 每次访问自动更新访问顺序
- 支持手动删除指定条目

**访问顺序维护**：
```python
# 访问时自动更新顺序
data = cache.get("key")  # key移动到队尾（最近使用）

# 新增时添加到队尾
cache.set("new_key", data)  # new_key添加到队尾

# 淘汰时从队首删除
evicted_key = lru_strategy.get_lru_key()  # 获取队首（最少使用）
cache.delete(evicted_key)
```

**应用场景**：
- DataFrame内存缓存（限制内存占用）
- 查询结果缓存（限制缓存条目数）

#### 4.2.3 TTL缓存规则

**过期判断规则**：
- **(当前时间 - 创建时间) <= TTL** → 有效
- **(当前时间 - 创建时间) > TTL** → 过期，自动删除

**时间计算**：
```python
# 使用time.time()获取时间戳（秒）
created_at = time.time()

# 检查时计算elapsed时间
elapsed = time.time() - created_at

# 判断是否过期
is_expired = elapsed > ttl_seconds
```

**应用场景**：
- 短期缓存（如1小时内的查询结果）
- 临时数据缓存（如下载进度信息）

#### 4.2.4 组合策略规则

**组合逻辑**：
- **AND逻辑**：所有策略都有效才返回True
- 任一策略失败立即返回False
- 按策略列表顺序检查

**常用组合**：
- **LRU + TTL**：限制容量 + 限制时间
- **Date + LRU**：日期失效 + 容量限制

**应用示例**：
```python
# LRU + TTL组合：最多缓存100条，每条最多1小时
strategy = CompositeStrategy([
    LRUStrategy(max_capacity=100),
    TTLStrategy(ttl_seconds=3600)
])

# Date + LRU组合：每日失效 + 容量限制
strategy = CompositeStrategy([
    DateBasedStrategy(),
    LRUStrategy(max_capacity=50)
])
```

---

## 五、负载均衡业务规则

> **架构设计参考**：负载均衡器架构请参考 [最佳实践文档 - 2.1 data_module.py - IntelligentAdaptiveTuner](./data_module_vnpy新架构最佳实践cursor版.md#21-data_modulepy---核心模块)

### 5.1 微观架构设计

#### 5.1.1 压力评估器架构

**设计目标**:
- 实现木桶理论的多维压力评分
- 动态监控CPU、内存、磁盘、网络4个维度
- 自动识别系统瓶颈
- 支持木桶理论评分和EMA平滑

**核心类设计**:

```python
from dataclasses import dataclass, field
from typing import Dict, Any, Tuple
import time
import logging

logger = logging.getLogger(__name__)

# ==================== 压力维度数据模型 ====================

@dataclass
class PressureDimension:
    """压力维度数据模型"""
    
    name: str  # 维度名称
    value: float  # 当前值(0-100)
    weight: float  # 权重(0-1)
    threshold_warning: float = 70.0  # 警告阈值
    threshold_critical: float = 90.0  # 严重阈值
    sub_metrics: Dict[str, float] = field(default_factory=dict)  # 子指标
    
    def get_score(self) -> float:
        """获取评分值"""
        return self.value
    
    def get_status(self) -> str:
        """获取状态"""
        if self.value >= self.threshold_critical:
            return "critical"
        elif self.value >= self.threshold_warning:
            return "warning"
        else:
            return "normal"


@dataclass
class PressureReport:
    """压力评估报告"""
    
    overall_score: float  # 综合压力评分(0-100)
    bottleneck: str  # 瓶颈维度
    dimensions: Dict[str, PressureDimension]  # 各维度详情
    timestamp: float = field(default_factory=time.time)
    recommendation: str = ""  # 优化建议
    
    def get_adjustment_hint(self) -> str:
        """获取调整建议"""
        if self.overall_score < 30:
            return "系统空闲,建议增加并发"
        elif self.overall_score < 70:
            return "系统正常,维持当前配置"
        elif self.overall_score < 90:
            return "系统压力较高,建议减少并发"
        else:
            return "系统压力严重,立即降低并发"


# ==================== 压力评估器 ====================

class PressureEvaluator:
    """压力评估器(木桶理论实现)
    
    实现木桶理论:
    - 综合压力由最高的维度决定(木桶短板)
    - 各维度按权重计算加权平均
    - 支持子指标聚合(如CPU的多个子指标)
    - 使用EMA平滑波动
    
    使用示例:
        evaluator = PressureEvaluator(
            weights={"cpu": 0.4, "memory": 0.25, "disk": 0.25, "network": 0.15}
        )
        
        # 收集系统指标
        metrics = {
            "cpu": {"cpu_percent": 45, "context_switches": 1500, "interrupts": 800},
            "memory": {"mem_percent": 60, "swap_percent": 10},
            "disk": {"disk_usage": 70, "io_wait": 5},
            "network": {"bandwidth_usage": 30, "packet_loss": 0.1}
        }
        
        # 评估压力
        report = evaluator.evaluate(metrics)
        print(f"综合压力: {report.overall_score}, 瓶颈: {report.bottleneck}")
    """
    
    def __init__(
        self,
        weights: Dict[str, float],
        ema_alpha: float = 0.3,
        sub_metric_weights: Optional[Dict[str, Dict[str, float]]] = None
    ):
        """初始化压力评估器
        
        Args:
            weights: 各维度权重 {"cpu": 0.4, "memory": 0.25, ...}
            ema_alpha: EMA平滑系数(0-1), 越大越敏感
            sub_metric_weights: 子指标权重(可选)
        """
        self.weights = weights
        self.ema_alpha = ema_alpha
        self.sub_metric_weights = sub_metric_weights or {}
        
        # EMA历史值
        self._ema_values: Dict[str, float] = {dim: 0.0 for dim in weights.keys()}
        
        # 木桶理论：不使用权重，只记录维度名称
        self.dimensions = list(weights.keys())
        
        logger.info(f"压力评估器已初始化: 权重={self.weights}, EMA_alpha={ema_alpha}")
    
    def _aggregate_sub_metrics(
        self,
        dimension: str,
        sub_metrics: Dict[str, float]
    ) -> float:
        """聚合子指标为单一评分
        
        Args:
            dimension: 维度名称
            sub_metrics: 子指标字典
            
        Returns:
            聚合后的评分(0-100)
        """
        # 获取该维度的子指标权重
        sub_weights = self.sub_metric_weights.get(dimension, {})
        
        if not sub_weights:
            # 木桶理论：取最小值
            values = list(sub_metrics.values())
            return sum(values) / len(values) if values else 0.0
        
        # 加权聚合
        weighted_sum = 0.0
        total_weight = 0.0
        
        for metric_name, value in sub_metrics.items():
            weight = sub_weights.get(metric_name, 1.0)
            weighted_sum += value * weight
            total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def _apply_ema(self, dimension: str, current_value: float) -> float:
        """应用EMA平滑
        
        公式: EMA_new = alpha * current + (1 - alpha) * EMA_old
        
        Args:
            dimension: 维度名称
            current_value: 当前值
            
        Returns:
            平滑后的值
        """
        ema_old = self._ema_values.get(dimension, current_value)
        ema_new = self.ema_alpha * current_value + (1 - self.ema_alpha) * ema_old
        self._ema_values[dimension] = ema_new
        return ema_new
    
    def evaluate(self, metrics: Dict[str, Dict[str, float]]) -> PressureReport:
        """评估系统压力
        
        Args:
            metrics: 系统指标字典
                {
                    "cpu": {"cpu_percent": 45, "context_switches": 1500, ...},
                    "memory": {"mem_percent": 60, "swap_percent": 10},
                    "disk": {"disk_usage": 70, "io_wait": 5},
                    "network": {"bandwidth_usage": 30, "packet_loss": 0.1}
                }
            
        Returns:
            压力评估报告
        """
        dimensions = {}
        max_pressure = 0.0
        bottleneck = "none"
        
        # 1. 计算各维度压力
        for dim_name, weight in self.weights.items():
            sub_metrics = metrics.get(dim_name, {})
            
            if not sub_metrics:
                logger.warning(f"维度 {dim_name} 缺少指标数据,跳过")
                continue
            
            # 聚合子指标
            raw_score = self._aggregate_sub_metrics(dim_name, sub_metrics)
            
            # 应用EMA平滑
            smoothed_score = self._apply_ema(dim_name, raw_score)
            
            # 创建维度对象
            dimension = PressureDimension(
                name=dim_name,
                value=smoothed_score,
                weight=weight,
                sub_metrics=sub_metrics
            )
            dimensions[dim_name] = dimension
            
            # 2. 记录最大压力(木桶短板)
            if smoothed_score > max_pressure:
                max_pressure = smoothed_score
                bottleneck = dim_name
        
        # 3. 计算综合压力(木桶理论)
        # 只看最短的板
        all_scores = [dim.get_score() for dim in dimensions.values()]
        overall_score = min(all_scores) if all_scores else 0
        
        # 4. 生成报告
        report = PressureReport(
            overall_score=round(overall_score, 2),
            bottleneck=bottleneck,
            dimensions=dimensions
        )
        report.recommendation = report.get_adjustment_hint()
        
        logger.debug(
            f"压力评估完成: 综合={overall_score:.2f}, 瓶颈={bottleneck}, "
            f"建议={report.recommendation}"
        )
        
        return report


# ==================== 并发配置计算器 ====================

class ConcurrencyCalculator:
    """并发配置计算器
    
    基于压力评估结果动态调整并发配置。
    
    调整策略:
    - 压力<30: 增加并发(scale up)
    - 压力30-70: 维持当前配置
    - 压力70-90: 减少并发(scale down)
    - 压力>90: 大幅减少并发(emergency scale down)
    
    使用示例:
        calculator = ConcurrencyCalculator(
            base_workers=10,
            min_workers=2,
            max_workers=20,
            step_size=2
        )
        
        # 根据压力调整
        new_config = calculator.calculate(pressure_score=75.0)
        print(f"建议workers数: {new_config['workers']}")
    """
    
    def __init__(
        self,
        base_workers: int,
        min_workers: int,
        max_workers: int,
        step_size: int = 2,
        cooldown_seconds: float = 10.0
    ):
        """初始化并发配置计算器
        
        Args:
            base_workers: 基准worker数量
            min_workers: 最小worker数量
            max_workers: 最大worker数量
            step_size: 每次调整的步长
            cooldown_seconds: 冷却时间(秒),避免频繁调整
        """
        self.base_workers = base_workers
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.step_size = step_size
        self.cooldown_seconds = cooldown_seconds
        
        # 当前配置
        self.current_workers = base_workers
        self.last_adjust_time = 0.0
        
        logger.info(
            f"并发计算器已初始化: base={base_workers}, "
            f"range=[{min_workers}, {max_workers}], step={step_size}"
        )
    
    def calculate(self, pressure_score: float) -> Dict[str, Any]:
        """计算并发配置
        
        Args:
            pressure_score: 压力评分(0-100)
            
        Returns:
            配置字典 {"workers": int, "adjustment": str, "reason": str}
        """
        now = time.time()
        
        # 检查冷却时间
        if now - self.last_adjust_time < self.cooldown_seconds:
            return {
                "workers": self.current_workers,
                "adjustment": "no_change",
                "reason": "cooldown"
            }
        
        # 决定调整方向
        if pressure_score < 30:
            # 压力低,增加并发
            new_workers = min(
                self.current_workers + self.step_size,
                self.max_workers
            )
            adjustment = "scale_up"
            reason = "low_pressure"
            
        elif pressure_score < 70:
            # 压力正常,维持不变
            new_workers = self.current_workers
            adjustment = "no_change"
            reason = "normal_pressure"
            
        elif pressure_score < 90:
            # 压力较高,减少并发
            new_workers = max(
                self.current_workers - self.step_size,
                self.min_workers
            )
            adjustment = "scale_down"
            reason = "high_pressure"
            
        else:
            # 压力严重,大幅减少并发
            new_workers = max(
                self.current_workers - self.step_size * 2,
                self.min_workers
            )
            adjustment = "emergency_scale_down"
            reason = "critical_pressure"
        
        # 更新状态
        if new_workers != self.current_workers:
            logger.info(
                f"并发调整: {self.current_workers} -> {new_workers} "
                f"(压力={pressure_score:.2f}, 原因={reason})"
            )
            self.current_workers = new_workers
            self.last_adjust_time = now
        
        return {
            "workers": new_workers,
            "adjustment": adjustment,
            "reason": reason,
            "pressure_score": pressure_score
        }


# ==================== 智能防抖管理器 ====================

class IntelligentDebounceManager:
    """智能防抖管理器
    
    动态调整防抖间隔,避免频繁操作。
    
    规则:
    - 记录历史操作频率
    - 频率高时增大防抖间隔
    - 频率低时减小防抖间隔
    - 支持最小/最大间隔限制
    
    使用示例:
        debounce = IntelligentDebounceManager(
            min_interval=0.5,
            max_interval=5.0,
            window_size=10
        )
        
        # 检查是否应该执行操作
        if debounce.should_execute("download_task"):
            # 执行下载
            download()
            debounce.record_execution("download_task")
    """
    
    def __init__(
        self,
        min_interval: float = 0.5,
        max_interval: float = 5.0,
        window_size: int = 10
    ):
        """初始化防抖管理器
        
        Args:
            min_interval: 最小防抖间隔(秒)
            max_interval: 最大防抖间隔(秒)
            window_size: 评估窗口大小(记录最近N次操作)
        """
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.window_size = window_size
        
        # 操作历史: {key: [timestamp1, timestamp2, ...]}
        self._history: Dict[str, list] = {}
        
        # 最后执行时间: {key: timestamp}
        self._last_execution: Dict[str, float] = {}
        
        logger.info(
            f"防抖管理器已初始化: interval=[{min_interval}, {max_interval}], "
            f"window={window_size}"
        )
    
    def _calculate_dynamic_interval(self, operation_key: str) -> float:
        """计算动态防抖间隔
        
        规则:
        - 统计窗口内的操作频率
        - 频率越高,间隔越大
        - 频率越低,间隔越小
        
        Args:
            operation_key: 操作标识
            
        Returns:
            动态间隔(秒)
        """
        history = self._history.get(operation_key, [])
        
        if len(history) < 2:
            # 历史数据不足,使用最小间隔
            return self.min_interval
        
        # 计算平均间隔
        recent = history[-self.window_size:]
        intervals = [recent[i] - recent[i-1] for i in range(1, len(recent))]
        avg_interval = sum(intervals) / len(intervals) if intervals else self.min_interval
        
        # 根据平均间隔动态调整
        if avg_interval < 1.0:
            # 操作频繁,增大防抖间隔
            dynamic_interval = min(avg_interval * 2, self.max_interval)
        else:
            # 操作不频繁,使用中等间隔
            dynamic_interval = min(avg_interval, self.max_interval)
        
        # 限制在最小/最大范围内
        return max(self.min_interval, min(dynamic_interval, self.max_interval))
    
    def should_execute(self, operation_key: str) -> bool:
        """判断是否应该执行操作
        
        Args:
            operation_key: 操作标识
            
        Returns:
            True表示可以执行,False表示应该防抖
        """
        now = time.time()
        last_time = self._last_execution.get(operation_key, 0.0)
        
        # 计算动态间隔
        interval = self._calculate_dynamic_interval(operation_key)
        
        # 判断是否超过防抖间隔
        elapsed = now - last_time
        should_exec = elapsed >= interval
        
        if not should_exec:
            logger.debug(
                f"防抖拦截: {operation_key}, elapsed={elapsed:.2f}s, "
                f"required={interval:.2f}s"
            )
        
        return should_exec
    
    def record_execution(self, operation_key: str):
        """记录操作执行
        
        Args:
            operation_key: 操作标识
        """
        now = time.time()
        
        # 更新最后执行时间
        self._last_execution[operation_key] = now
        
        # 添加到历史记录
        if operation_key not in self._history:
            self._history[operation_key] = []
        
        self._history[operation_key].append(now)
        
        # 限制历史记录长度
        if len(self._history[operation_key]) > self.window_size:
            self._history[operation_key].pop(0)
```

**架构优势**:

1. **木桶理论压力评估**:
   - 准确识别系统瓶颈
   - 综合压力由最高维度决定
   - 支持多维度加权计算
   - EMA平滑避免波动

2. **动态并发调整**:
   - 基于压力自动调整worker数量
   - 支持冷却时间避免频繁调整
   - 分级调整策略(normal/emergency)
   - 严格限制最小/最大并发数

3. **智能防抖**:
   - 根据操作频率动态调整间隔
   - 避免频繁操作影响性能
   - 支持多个操作独立防抖
   - 自动记录和分析历史

#### 5.1.2 使用示例

**场景1:下载任务并发调整**:
```python
# 初始化压力评估器
evaluator = PressureEvaluator(
    weights={"cpu": 0.4, "memory": 0.25, "disk": 0.25, "network": 0.15},
    ema_alpha=0.3,
    sub_metric_weights={
        "cpu": {"cpu_percent": 1.0, "context_switches": 0.5, "interrupts": 0.3},
        "memory": {"mem_percent": 1.0, "swap_percent": 0.8}
    }
)

# 初始化并发计算器
calculator = ConcurrencyCalculator(
    base_workers=10,
    min_workers=2,
    max_workers=20,
    step_size=2,
    cooldown_seconds=10.0
)

# 定期评估和调整
while True:
    # 收集系统指标
    metrics = collect_system_metrics()
    
    # 评估压力
    report = evaluator.evaluate(metrics)
    
    # 计算新配置
    config = calculator.calculate(report.overall_score)
    
    # 应用配置
    if config["adjustment"] != "no_change":
        adjust_worker_pool(config["workers"])
    
    time.sleep(5)
```

**场景2:智能防抖控制**:
```python
# 初始化防抖管理器
debounce = IntelligentDebounceManager(
    min_interval=0.5,
    max_interval=5.0,
    window_size=10
)

# 在下载循环中使用
while True:
    if debounce.should_execute("batch_download"):
        # 执行批量下载
        download_batch(tasks)
        debounce.record_execution("batch_download")
    
    await asyncio.sleep(0.1)
```

### 5.2 负载均衡业务规则

#### 5.2.1 木桶理论压力评分规则

**评分维度定义**:
- **CPU维度**(权重40%):
  - cpu_percent: CPU使用率(0-100)
  - context_switches: 上下文切换次数
  - interrupts: 中断次数

- **内存维度**(权重25%):
  - mem_percent: 内存使用率(0-100)
  - swap_percent: 交换空间使用率(0-100)

- **磁盘维度**(权重25%):
  - disk_usage: 磁盘使用率(0-100)
  - io_wait: I/O等待时间百分比(0-100)

- **网络维度**(权重15%):
  - bandwidth_usage: 带宽使用率(0-100)
  - packet_loss: 丢包率(0-1转换为0-100)

**木桶理论评分规则**:
```python
# 1. 各维度加权平均
weighted_avg = sum(dim.value * dim.weight for dim in dimensions.values())

# 2. 木桶短板(最大压力)
max_pressure = max(dim.value for dim in dimensions.values())

# 3. 木桶理论评分（只看最短板）
overall_score = max(weighted_avg, max_pressure * 0.8)
```

**瓶颈识别规则**:
- 压力最高的维度即为瓶颈
- 记录瓶颈维度名称
- 在报告中提供针对性建议

#### 5.2.2 并发动态调整规则

**调整阈值**:
- **压力 < 30**: 系统空闲,增加并发
- **压力 30-70**: 系统正常,维持配置
- **压力 70-90**: 压力较高,减少并发
- **压力 > 90**: 压力严重,紧急降低并发

**调整步长**:
- 常规调整: ±step_size (默认±2)
- 紧急调整: ±step_size*2 (压力>90时)

**冷却机制**:
- 两次调整之间必须间隔cooldown_seconds
- 避免频繁调整导致震荡
- 冷却期间维持当前配置

#### 5.2.3 智能防抖决策规则

**动态间隔计算规则**:
```python
# 1. 计算窗口内平均操作间隔
avg_interval = sum(intervals) / len(intervals)

# 2. 根据频率动态调整
if avg_interval < 1.0:  # 操作频繁
    dynamic_interval = min(avg_interval * 2, max_interval)
else:  # 操作不频繁
    dynamic_interval = min(avg_interval, max_interval)

# 3. 限制在范围内
final_interval = max(min_interval, min(dynamic_interval, max_interval))
```

**防抖判定规则**:
- **elapsed >= interval**: 允许执行
- **elapsed < interval**: 防抖拦截,跳过本次操作

---

## 六、IPO日期管理业务规则

> **架构设计参考**:IPO缓存器架构请参考 [最佳实践文档 - 2.1 data_module.py](./data_module_vnpy新架构最佳实践cursor版.md#21-data_modulepy---核心模块)

### 6.1 微观架构设计

#### 6.1.1 双层缓存架构

**设计目标**:
- L1内存缓存:高速访问,避免重复请求
- L2文件缓存:持久化存储,实现日期失效
- 缓存一致性:两层缓存同步更新
- 高命中率:优先从内存查询,减少文件I/O

**核心类设计**:

```python
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Tuple
from pathlib import Path
import logging
import json

logger = logging.getLogger(__name__)

# ==================== IPO数据模型 ====================

@dataclass
class IPORecord:
    """IPO日期记录"""
    
    symbol: str
    ipo_date: date
    market: int  # 0=深圳, 1=上海, 2=北京
    source: str  # "tushare"/"tdx"/"manual"
    confidence: float = 1.0  # 置信度(0-1)
    updated_at: datetime = None
    
    def __post_init__(self):
        if self.updated_at is None:
            self.updated_at = datetime.now()
    
    def is_valid(self, base_date: date = None) -> bool:
        """验证IPO日期合法性
        
        规则:
        1. IPO日期不能超过今天+30天
        2. IPO日期不能早于1990年
        3. 如果指定base_date,不能早于base_date
        """
        if base_date is None:
            base_date = date.today()
        
        # 规则1: 不能超过今天+30天
        if self.ipo_date > base_date + timedelta(days=30):
            return False
        
        # 规则2: 不能早于1990年
        if self.ipo_date.year < 1990:
            return False
        
        return True
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "symbol": self.symbol,
            "ipo_date": self.ipo_date.strftime("%Y-%m-%d"),
            "market": self.market,
            "source": self.source,
            "confidence": self.confidence,
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "IPORecord":
        """从字典创建"""
        return cls(
            symbol=data["symbol"],
            ipo_date=datetime.strptime(data["ipo_date"], "%Y-%m-%d").date(),
            market=data["market"],
            source=data["source"],
            confidence=data.get("confidence", 1.0),
            updated_at=datetime.fromisoformat(data["updated_at"])
        )


# ==================== 双层缓存管理器 ====================

class TwoLevelCacheManager:
    """IPO日期双层缓存管理器
    
    架构设计:
    - L1 Cache (内存):
      - 存储类型: Dict[str, IPORecord]
      - 失效策略: 进程生命周期(不失效)
      - 查询性能: O(1)
      - 使用场景: 高频查询
    
    - L2 Cache (文件):
      - 存储类型: JSON文件
      - 失效策略: 日期失效(次日0时)
      - 查询性能: 文件I/O
      - 使用场景: 跨进程/重启后恢复
    
    查询流程:
    1. 尝试从 L1 内存缓存查询
    2. 如果 L1 miss,从 L2 文件缓存加载
    3. 如果 L2 miss 或已过期,从数据源获取
    4. 获取后同时更新 L1 和 L2
    
    使用示例:
        cache = TwoLevelCacheManager(cache_dir=Path("./cache"))
        
        # 查询IPO日期
        ipo_date, source = cache.get("000001.SZ")
        
        # 批量设置
        cache.set_batch(ipo_records)
        
        # 清空缓存
        cache.clear()
    """
    
    def __init__(self, cache_dir: Path):
        """初始化双层缓存
        
        Args:
            cache_dir: 缓存目录
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # L1 内存缓存
        self._memory_cache: Dict[str, IPORecord] = {}
        
        # L2 文件缓存路径
        self._file_cache_path = self.cache_dir / "ipo_dates.json"
        
        # 统计信息
        self._stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "misses": 0,
            "updates": 0
        }
        
        # 启动时加载 L2 缓存
        self._load_from_l2()
        
        logger.info(
            f"IPO双层缓存已初始化: 加载{len(self._memory_cache)}条记录"
        )
    
    def _load_from_l2(self) -> bool:
        """从 L2 文件缓存加载到 L1 内存
        
        Returns:
            True表示加载成功
        """
        if not self._file_cache_path.exists():
            logger.debug("L2 缓存文件不存在")
            return False
        
        try:
            with open(self._file_cache_path, 'r', encoding='utf-8') as f:
                cache_obj = json.load(f)
            
            # 验证缓存日期
            cache_date_str = cache_obj.get("cache_date")
            if cache_date_str != date.today().strftime("%Y-%m-%d"):
                logger.info(f"L2 缓存已过期: {cache_date_str}")
                return False
            
            # 加载数据
            data = cache_obj.get("data", {})
            for symbol, record_dict in data.items():
                record = IPORecord.from_dict(record_dict)
                if record.is_valid():
                    self._memory_cache[symbol] = record
                else:
                    logger.warning(f"IPO记录无效: {symbol}, 跳过")
            
            logger.info(f"L2 缓存加载成功: {len(self._memory_cache)}条记录")
            return True
            
        except Exception as e:
            logger.error(f"L2 缓存加载失败: {e}", exc_info=True)
            return False
    
    def _save_to_l2(self) -> bool:
        """保存 L1 内存缓存到 L2 文件
        
        Returns:
            True表示保存成功
        """
        try:
            # 构建缓存对象
            cache_obj = {
                "cache_date": date.today().strftime("%Y-%m-%d"),
                "data": {
                    symbol: record.to_dict()
                    for symbol, record in self._memory_cache.items()
                }
            }
            
            # 写入文件
            with open(self._file_cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_obj, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"L2 缓存保存成功: {len(self._memory_cache)}条记录")
            return True
            
        except Exception as e:
            logger.error(f"L2 缓存保存失败: {e}", exc_info=True)
            return False
    
    def get(self, symbol: str) -> Tuple[Optional[date], Optional[str]]:
        """获取IPO日期
        
        Args:
            symbol: 品种代码
            
        Returns:
            (ipo_date, source)元组,不存在返回(None, None)
        """
        # 尝试从 L1 内存缓存查询
        record = self._memory_cache.get(symbol)
        
        if record:
            self._stats["l1_hits"] += 1
            return record.ipo_date, record.source
        
        # L1 miss
        self._stats["misses"] += 1
        return None, None
    
    def get_all(self) -> Dict[str, Tuple[date, str]]:
        """获取所有IPO日期
        
        Returns:
            {symbol: (ipo_date, source)} 字典
        """
        return {
            symbol: (record.ipo_date, record.source)
            for symbol, record in self._memory_cache.items()
        }
    
    def set(self, symbol: str, ipo_date: date, source: str, market: int = 0) -> bool:
        """设置IPO日期
        
        Args:
            symbol: 品种代码
            ipo_date: IPO日期
            source: 数据源
            market: 市场代码
            
        Returns:
            True表示设置成功
        """
        # 创建记录
        record = IPORecord(
            symbol=symbol,
            ipo_date=ipo_date,
            market=market,
            source=source
        )
        
        # 验证合法性
        if not record.is_valid():
            logger.warning(f"IPO日期无效: {symbol}={ipo_date}, 跳过")
            return False
        
        # 更新 L1 内存缓存
        self._memory_cache[symbol] = record
        self._stats["updates"] += 1
        
        return True
    
    def set_batch(self, records: Dict[str, Tuple[date, str, int]]) -> int:
        """批量设置IPO日期
        
        Args:
            records: {symbol: (ipo_date, source, market)} 字典
            
        Returns:
            成功设置的数量
        """
        count = 0
        for symbol, (ipo_date, source, market) in records.items():
            if self.set(symbol, ipo_date, source, market):
                count += 1
        
        # 批量更新后保存到 L2
        self._save_to_l2()
        
        logger.info(f"批量设置IPO日期: {count}/{len(records)} 条成功")
        return count
    
    def exists(self, symbol: str) -> bool:
        """检查IPO日期是否存在"""
        return symbol in self._memory_cache
    
    def clear(self) -> int:
        """清空所有缓存
        
        Returns:
            清理的记录数量
        """
        count = len(self._memory_cache)
        
        # 清空 L1
        self._memory_cache.clear()
        
        # 删除 L2
        if self._file_cache_path.exists():
            self._file_cache_path.unlink()
        
        logger.info(f"已清空 IPO缓存: {count}条记录")
        return count
    
    def get_stats(self) -> Dict:
        """获取缓存统计"""
        total_requests = sum([
            self._stats["l1_hits"],
            self._stats["l2_hits"],
            self._stats["misses"]
        ])
        
        l1_hit_rate = (
            self._stats["l1_hits"] / total_requests * 100
            if total_requests > 0 else 0.0
        )
        
        return {
            "size": len(self._memory_cache),
            "l1_hits": self._stats["l1_hits"],
            "l2_hits": self._stats["l2_hits"],
            "misses": self._stats["misses"],
            "updates": self._stats["updates"],
            "l1_hit_rate": round(l1_hit_rate, 2)
        }


# ==================== IPO获取器 ====================

class IPOFetcher:
    """IPO日期获取器
    
    支持多数据源:
    1. Tushare API (优先)
    2. TDX 本地文件 (降级)
    3. 手动配置 (最后降级)
    
    使用示例:
        fetcher = IPOFetcher(tushare_token="xxx")
        
        # 单个获取
        ipo_date = fetcher.fetch_single("000001.SZ")
        
        # 批量获取
        ipo_dict = fetcher.fetch_batch(["000001.SZ", "600000.SH"])
    """
    
    def __init__(self, tushare_token: Optional[str] = None):
        """初始化IPO获取器
        
        Args:
            tushare_token: Tushare API token(可选)
        """
        self.tushare_token = tushare_token
        self._tushare_available = False
        
        # 尝试初始化Tushare
        if tushare_token:
            try:
                import tushare as ts
                ts.set_token(tushare_token)
                self.pro = ts.pro_api()
                self._tushare_available = True
                logger.info("✅ Tushare API已初始化")
            except Exception as e:
                logger.warning(f"⚠️ Tushare API初始化失败: {e}")
        
        logger.info(
            f"IPO获取器已初始化: Tushare={'available' if self._tushare_available else 'unavailable'}"
        )
    
    def fetch_single(self, symbol: str) -> Optional[date]:
        """获取单个IPO日期
        
        Args:
            symbol: 品种代码
            
        Returns:
            IPO日期,获取失败返回None
        """
        # 1. 尝试从 Tushare 获取
        if self._tushare_available:
            ipo_date = self._fetch_from_tushare(symbol)
            if ipo_date:
                return ipo_date
        
        # 2. 尝试从 TDX 本地文件获取
        ipo_date = self._fetch_from_tdx(symbol)
        if ipo_date:
            return ipo_date
        
        # 3. 所有数据源都失败
        logger.warning(f"无法获取IPO日期: {symbol}")
        return None
    
    def fetch_batch(self, symbols: list) -> Dict[str, date]:
        """批量获取IPO日期
        
        Args:
            symbols: 品种代码列表
            
        Returns:
            {symbol: ipo_date} 字典
        """
        result = {}
        
        for symbol in symbols:
            ipo_date = self.fetch_single(symbol)
            if ipo_date:
                result[symbol] = ipo_date
        
        logger.info(f"批量获取IPO日期: {len(result)}/{len(symbols)} 条成功")
        return result
    
    def _fetch_from_tushare(self, symbol: str) -> Optional[date]:
        """从 Tushare API 获取"""
        try:
            # Tushare码转换: 000001.SZ -> 000001.SZ
            ts_code = symbol
            
            # 查询股票基本信息
            df = self.pro.stock_basic(
                ts_code=ts_code,
                fields='ts_code,list_date'
            )
            
            if df.empty:
                return None
            
            list_date_str = df.iloc[0]['list_date']
            if not list_date_str or list_date_str == '':
                return None
            
            # 转换为日期
            ipo_date = datetime.strptime(list_date_str, "%Y%m%d").date()
            logger.debug(f"Tushare获取: {symbol} = {ipo_date}")
            return ipo_date
            
        except Exception as e:
            logger.debug(f"Tushare获取失败: {symbol}, {e}")
            return None
    
    def _fetch_from_tdx(self, symbol: str) -> Optional[date]:
        """从 TDX 本地文件获取"""
        # TODO: 实现从 TDX 本地文件读取逻辑
        # 需要解析 TDX 的 gpcw*.dat 文件
        return None
```

**架构优势**:

1. **双层缓存**:
   - L1内存缓存:O(1)查询,高速访问
   - L2文件缓存:持久化存储,跨进程共享
   - 自动同步:更新时同时写入两层缓存
   - 日期失效:每日自动失效,保证数据新鲜

2. **数据验证**:
   - IPO日期合法性验证
   - 过滤无效数据(未来日期/过早1990年)
   - 数据源置信度跟踪

3. **多数据源**:
   - 支持Tushare API(优先)
   - 支持TDX本地文件(降级)
   - 支持手动配置(最后降级)

4. **性能监控**:
   - L1/L2命中率统计
   - 缓存更新频率统计
   - 支持性能分析

#### 6.1.2 使用示例

**场景1:初始化和加载**:
```python
# 创建缓存管理器
ipo_cache = TwoLevelCacheManager(cache_dir=Path("./cache"))

# 初始化时会自动从 L2 加载到 L1
# 如果 L2 过期或不存在,L1 为空

# 查询IPO日期
ipo_date, source = ipo_cache.get("000001.SZ")
if ipo_date:
    print(f"IPO日期: {ipo_date}, 数据源: {source}")
```

**场景2:批量获取和缓存**:
```python
# 创建获取器
fetcher = IPOFetcher(tushare_token="xxx")

# 获取所有品种列表
symbols = get_all_symbols()

# 批量获取IPO日期
ipo_dict = fetcher.fetch_batch(symbols)

# 批量设置到缓存
records = {
    symbol: (ipo_date, "tushare", 0)
    for symbol, ipo_date in ipo_dict.items()
}

ipo_cache.set_batch(records)
```

**场景3:缓存命中率监控**:
```python
# 获取统计信息
stats = ipo_cache.get_stats()
print(f"L1命中率: {stats['l1_hit_rate']}%")
print(f"缓存大小: {stats['size']} 条记录")
```

### 6.2 IPO管理业务规则

#### 6.2.1 IPO日期验证规则

**验证规则**:
- **规则1**: IPO日期不能超过今天+30天
- **规则2**: IPO日期不能早于1990年
- **规则3**: 如果指定base_date,不能早于base_date

**处理策略**:
- 无效记录跳过,记录warning日志
- 不缓存无效数据

#### 6.2.2 数据源优先级规则

**优先级顺序**:
1. Tushare API (高置信度,实时更新)
2. TDX 本地文件 (中置信度,离线可用)
3. 手动配置 (低置信度,兼容性)

**降级策略**:
- Tushare失败后自动降级到TDX
- 所有数据源失败返回None

#### 6.2.3 缓存更新规则

**更新时机**:
- 每日首次启动时检查缓存有效性
- 发现新品种时自动获取IPO日期

**更新策略**:
- 批量更新:一次性获取所有品种
- 增量更新:只获取缺失的品种

---

## 七、数据质量管理业务规则

> **架构设计参考**:质量扫描器架构请参考 [最佳实践文档 - 2.4 data_quality.py](./data_module_vnpy新架构最佳实践cursor版.md#24-data_qualitypy---数据质量管理)

### 7.1 微观架构设计

#### 7.1.1 质量扫描器架构

**设计目标**:
- 高效扫描海量数据文件(5000+品种 × 4周期)
- 多进程并发扫描,充分利用CPU
- 增量扫描,避免重复扫描
- 质量指标可扩展,支持新增检测维度

**核心类设计**:

```python
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional
from pathlib import Path
from datetime import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)

# ==================== 质量指标数据模型 ====================

@dataclass
class QualityMetrics:
    """数据质量指标"""
    
    symbol: str
    interval: str
    
    # 基础指标
    total_records: int = 0
    missing_records: int = 0
    duplicate_records: int = 0
    
    # 格式质量(0-100)
    format_score: float = 0.0
    format_errors: List[str] = field(default_factory=list)
    
    # 逻辑质量(0-100)
    logic_score: float = 0.0
    logic_errors: List[str] = field(default_factory=list)
    
    # 完整性质量(0-100)
    completeness_score: float = 0.0
    missing_dates: List[str] = field(default_factory=list)
    
    # 新鲜度质量(0-100)
    freshness_score: float = 0.0
    lag_days: int = 0
    
    # 木桶理论评分(0-100)
    overall_score: float = 0.0
    quality_level: str = "unknown"  # excellent/good/fair/poor
    
    # 扫描元信息
    scanned_at: datetime = field(default_factory=datetime.now)
    file_size_mb: float = 0.0
    
    def calculate_overall_score(self, weights: Dict[str, float] = None):
        """计算木桶理论评分
        
        默认权重: 格式30% + 逻辑20% + 完整性30% + 新鲜度20%
        """
        if weights is None:
            weights = {
                "format": 0.3,
                "logic": 0.2,
                "completeness": 0.3,
                "freshness": 0.2
            }
        
        self.overall_score = (
            self.format_score * weights["format"] +
            self.logic_score * weights["logic"] +
            self.completeness_score * weights["completeness"] +
            self.freshness_score * weights["freshness"]
        )
        
        # 确定质量等级
        if self.overall_score >= 90:
            self.quality_level = "excellent"
        elif self.overall_score >= 75:
            self.quality_level = "good"
        elif self.overall_score >= 60:
            self.quality_level = "fair"
        else:
            self.quality_level = "poor"
    
    def needs_repair(self, threshold: float = 60.0) -> bool:
        """判断是否需要修复"""
        return self.overall_score < threshold


@dataclass
class ScanTask:
    """扫描任务"""
    
    symbol: str
    interval: str
    file_path: Path
    priority: int = 0  # 优先级(数值越大越优先)
    
    def get_task_id(self) -> str:
        """获取任务唯一标识"""
        return f"{self.symbol}_{self.interval}"


# ==================== 增量扫描记录管理 ====================

class ScanRecordManager:
    """扫描记录管理器
    
    记录已扫描文件的校验和,实现增量扫描。
    
    使用示例:
        manager = ScanRecordManager(record_file=Path("./scan_records.json"))
        
        # 检查是否需要扫描
        if manager.should_scan(file_path):
            # 执行扫描
            scan_file(file_path)
            # 标记已扫描
            manager.mark_scanned(file_path, checksum)
    """
    
    def __init__(self, record_file: Path):
        """
        Args:
            record_file: 扫描记录文件路径
        """
        self.record_file = record_file
        self._records: Dict[str, Dict] = {}  # {file_path: {checksum, scanned_at}}
        
        # 加载历史记录
        self._load_records()
    
    def _load_records(self):
        """加载扫描记录"""
        if not self.record_file.exists():
            return
        
        try:
            import json
            with open(self.record_file, 'r', encoding='utf-8') as f:
                self._records = json.load(f)
            logger.info(f"已加载 {len(self._records)} 条扫描记录")
        except Exception as e:
            logger.error(f"加载扫描记录失败: {e}")
    
    def _save_records(self):
        """保存扫描记录"""
        try:
            import json
            self.record_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.record_file, 'w', encoding='utf-8') as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存扫描记录失败: {e}")
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """计算文件校验和(使用文件大小+修改时间)"""
        try:
            stat = file_path.stat()
            content = f"{stat.st_size}_{stat.st_mtime}"
            return hashlib.md5(content.encode()).hexdigest()
        except Exception as e:
            logger.error(f"计算校验和失败 ({file_path}): {e}")
            return ""
    
    def should_scan(self, file_path: Path) -> bool:
        """判断文件是否需要扫描
        
        规则:
        - 文件不存在于记录中 → 需要扫描
        - 文件校验和变化 → 需要扫描
        - 文件校验和未变化 → 跳过扫描
        """
        file_key = str(file_path)
        current_checksum = self._calculate_checksum(file_path)
        
        if not current_checksum:
            return True
        
        if file_key not in self._records:
            return True
        
        old_checksum = self._records[file_key].get("checksum", "")
        return current_checksum != old_checksum
    
    def mark_scanned(self, file_path: Path, quality_score: float = None):
        """标记文件已扫描
        
        Args:
            file_path: 文件路径
            quality_score: 质量评分(可选)
        """
        file_key = str(file_path)
        checksum = self._calculate_checksum(file_path)
        
        self._records[file_key] = {
            "checksum": checksum,
            "scanned_at": datetime.now().isoformat(),
            "quality_score": quality_score
        }
        
        self._save_records()
    
    def clear_records(self):
        """清空所有记录"""
        self._records.clear()
        self._save_records()
        logger.info("已清空扫描记录")


# ==================== 质量扫描器 ====================

class QualityScanner:
    """数据质量扫描器
    
    职责:
    1. 扫描数据文件,生成质量指标
    2. 支持增量扫描,避免重复扫描
    3. 多进程并发扫描,提升效率
    4. 生成质量报告
    
    使用示例:
        scanner = QualityScanner(
            data_dir=Path("./data"),
            record_file=Path("./scan_records.json")
        )
        
        # 扫描所有数据
        results = scanner.scan_all(intervals=["1d", "1h"])
        
        # 生成报告
        report = scanner.generate_report(results)
    """
    
    def __init__(
        self,
        data_dir: Path,
        record_file: Path,
        validators: List = None
    ):
        """
        Args:
            data_dir: 数据目录
            record_file: 扫描记录文件
            validators: 验证器列表(可选)
        """
        self.data_dir = Path(data_dir)
        self.record_manager = ScanRecordManager(record_file)
        self.validators = validators or self._get_default_validators()
        
        logger.info(f"质量扫描器已初始化: data_dir={data_dir}")
    
    def _get_default_validators(self) -> List:
        """获取默认验证器列表"""
        # 引用第三章定义的验证器
        from .validation import (
            FormatValidator,
            LogicValidator,
            CompletenessValidator,
            FreshnessValidator
        )
        
        return [
            FormatValidator(),
            LogicValidator(),
            CompletenessValidator(),
            FreshnessValidator()
        ]
    
    def scan_file(self, task: ScanTask) -> Optional[QualityMetrics]:
        """扫描单个文件
        
        Args:
            task: 扫描任务
            
        Returns:
            质量指标,扫描失败返回None
        """
        # 检查是否需要扫描
        if not self.record_manager.should_scan(task.file_path):
            logger.debug(f"跳过已扫描文件: {task.file_path}")
            return None
        
        try:
            # 读取数据文件
            import pandas as pd
            df = pd.read_parquet(task.file_path)
            
            # 创建质量指标对象
            metrics = QualityMetrics(
                symbol=task.symbol,
                interval=task.interval,
                total_records=len(df),
                file_size_mb=task.file_path.stat().st_size / (1024 * 1024)
            )
            
            # 执行所有验证器
            for validator in self.validators:
                result = validator.validate(df, context=None)
                
                # 根据验证器类型更新指标
                if "Format" in validator.__class__.__name__:
                    metrics.format_score = result.score
                    metrics.format_errors = [e.message for e in result.errors]
                elif "Logic" in validator.__class__.__name__:
                    metrics.logic_score = result.score
                    metrics.logic_errors = [e.message for e in result.errors]
                elif "Completeness" in validator.__class__.__name__:
                    metrics.completeness_score = result.score
                    metrics.missing_dates = [e.date for e in result.errors if e.date]
                elif "Freshness" in validator.__class__.__name__:
                    metrics.freshness_score = result.score
                    if result.statistics:
                        metrics.lag_days = result.statistics.get("gap_days", 0)
            
            # 计算木桶理论评分
            metrics.calculate_overall_score()
            
            # 标记已扫描
            self.record_manager.mark_scanned(
                task.file_path,
                quality_score=metrics.overall_score
            )
            
            logger.debug(
                f"扫描完成: {task.symbol} {task.interval}, "
                f"评分={metrics.overall_score:.2f}"
            )
            
            return metrics
            
        except Exception as e:
            logger.error(f"扫描文件失败 ({task.file_path}): {e}", exc_info=True)
            return None
    
    def scan_all(
        self,
        intervals: List[str],
        symbols: List[str] = None,
        num_processes: int = 4
    ) -> Dict[str, QualityMetrics]:
        """扫描所有数据文件
        
        Args:
            intervals: 周期列表
            symbols: 品种列表(None表示扫描所有)
            num_processes: 进程数
            
        Returns:
            {task_id: metrics} 字典
        """
        # 生成扫描任务
        tasks = self._generate_tasks(intervals, symbols)
        
        logger.info(f"开始质量扫描: {len(tasks)} 个任务, {num_processes} 进程")
        
        # 多进程扫描
        from multiprocessing import Pool
        
        results = {}
        with Pool(processes=num_processes) as pool:
            metrics_list = pool.map(self.scan_file, tasks)
            
            for task, metrics in zip(tasks, metrics_list):
                if metrics:
                    results[task.get_task_id()] = metrics
        
        logger.info(
            f"扫描完成: {len(results)}/{len(tasks)} 个任务成功"
        )
        
        return results
    
    def _generate_tasks(self, intervals: List[str], symbols: List[str] = None) -> List[ScanTask]:
        """生成扫描任务列表"""
        tasks = []
        
        for interval in intervals:
            interval_dir = self.data_dir / interval
            if not interval_dir.exists():
                continue
            
            for file_path in interval_dir.glob("*.parquet"):
                symbol = file_path.stem
                
                # 过滤品种
                if symbols and symbol not in symbols:
                    continue
                
                task = ScanTask(
                    symbol=symbol,
                    interval=interval,
                    file_path=file_path
                )
                tasks.append(task)
        
        return tasks
    
    def generate_report(self, results: Dict[str, QualityMetrics]) -> Dict:
        """生成质量报告
        
        Args:
            results: 扫描结果
            
        Returns:
            质量报告字典
        """
        if not results:
            return {}
        
        # 统计各质量等级数量
        level_counts = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
        total_score = 0.0
        
        poor_quality_items = []
        
        for task_id, metrics in results.items():
            level_counts[metrics.quality_level] += 1
            total_score += metrics.overall_score
            
            # 收集低质量数据
            if metrics.quality_level == "poor":
                poor_quality_items.append({
                    "symbol": metrics.symbol,
                    "interval": metrics.interval,
                    "score": metrics.overall_score,
                    "errors": metrics.format_errors + metrics.logic_errors
                })
        
        # 生成报告
        report = {
            "total_files": len(results),
            "average_score": total_score / len(results) if results else 0,
            "level_distribution": level_counts,
            "poor_quality_items": poor_quality_items,
            "generated_at": datetime.now().isoformat()
        }
        
        logger.info(
            f"质量报告生成: 平均分={report['average_score']:.2f}, "
            f"优秀={level_counts['excellent']}, "
            f"良好={level_counts['good']}, "
            f"一般={level_counts['fair']}, "
            f"较差={level_counts['poor']}"
        )
        
        return report
```

**架构优势**:

1. **增量扫描**:
   - 基于文件校验和(大小+修改时间)
   - 避免重复扫描未变化文件
   - 大幅提升扫描效率

2. **多进程并发**:
   - 充分利用多核CPU
   - 大幅缩短扫描时间
   - 适合海量文件扫描

3. **质量指标**:
   - 多维度评分(格式/逻辑/完整性/新鲜度)
   - 木桶理论评分
   - 质量等级分类

4. **可扩展性**:
   - 验证器可插拔
   - 易于新增质量维度
   - 基于木桶理论（只看最短板）

### 7.2 数据质量业务规则

#### 7.2.1 质量评分规则

**木桶理论评分计算**:
```python
木桶理论评分 = min(格式评分, 逻辑评分, 完整性评分, 新鲜度评分)
```

**质量等级划分**:
- **优秀**(excellent): 木桶理论评分 ≥ 90分
- **良好**(good): 木桶理论评分 ≥ 75分
- **一般**(fair): 木桶理论评分 ≥ 60分
- **较差**(poor): 木桶理论评分 < 60分

#### 7.2.2 增量扫描规则

**校验和计算规则**:
```python
checksum = MD5(f"{文件大小}_{修改时间}")
```

**扫描判定规则**:
- 文件不在扫描记录中 → 需要扫描
- 文件校验和发生变化 → 需要扫描
- 文件校验和未变化 → 跳过扫描

#### 7.2.3 修复建议规则

**自动修复阈值**:
- 木桶理论评分 < 60分 → 建议修复
- 格式错误 > 0 → 必须修复
- 逻辑错误 > 10条 → 建议重新下载

---

## 八、统一数据查询业务规则

> **架构设计参考**:统一管理器架构请参考 [最佳实践文档 - 2.5 unified_data_manager.py](./data_module_vnpy新架构最佳实践cursor版.md#25-unified_data_managerpy---统一数据查询)

### 8.1 微观架构设计

#### 8.1.1 四层融合查询引擎

**设计目标**:
- L1内存缓存:毫秒级响应,LRU淘汰
- L2本地文件:秒级响应,Parquet格式
- L3实时下载:按需下载,自动补全
- L4数据源回放:历史数据回放
- 自动降级:上层失败自动降级到下层

**核心类设计**:

```python
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from datetime import date, datetime
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# ==================== 查询层抽象 ====================

class QueryLayer(ABC):
    """查询层抽象接口"""
    
    @abstractmethod
    def query(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Optional[pd.DataFrame]:
        """查询数据
        
        Args:
            symbol: 品种代码
            interval: 周期
            start_date: 起始日期(可选)
            end_date: 结束日期(可选)
            
        Returns:
            DataFrame,查询失败返回None
        """
        pass
    
    @abstractmethod
    def get_layer_name(self) -> str:
        """获取层名称"""
        pass


class L1MemoryCacheLayer(QueryLayer):
    """L1 内存缓存层"""
    
    def __init__(self, cache_manager):
        """Args: cache_manager: LRU缓存管理器"""
        self.cache = cache_manager
    
    def query(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Optional[pd.DataFrame]:
        """从内存缓存查询"""
        cache_key = f"{symbol}_{interval}"
        df = self.cache.get(cache_key)
        
        if df is None:
            logger.debug(f"L1 Cache Miss: {cache_key}")
            return None
        
        # 日期过滤
        if start_date or end_date:
            df = self._filter_by_date(df, start_date, end_date)
        
        logger.debug(f"L1 Cache Hit: {cache_key}, {len(df)} 条记录")
        return df.copy()
    
    def _filter_by_date(self, df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
        """日期过滤"""
        mask = pd.Series([True] * len(df), index=df.index)
        
        if start:
            mask &= df['datetime'].dt.date >= start
        if end:
            mask &= df['datetime'].dt.date <= end
        
        return df[mask]
    
    def get_layer_name(self) -> str:
        return "L1_Memory_Cache"


class L2LocalFileLayer(QueryLayer):
    """L2 本地文件层"""
    
    def __init__(self, storage_manager):
        """Args: storage_manager: 存储管理器"""
        self.storage = storage_manager
    
    def query(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Optional[pd.DataFrame]:
        """从本地文件查询"""
        try:
            df = self.storage.load_data(symbol, interval, start_date, end_date)
            
            if df is None or df.empty:
                logger.debug(f"L2 File Miss: {symbol} {interval}")
                return None
            
            logger.debug(f"L2 File Hit: {symbol} {interval}, {len(df)} 条记录")
            return df
            
        except Exception as e:
            logger.error(f"L2查询失败: {e}")
            return None
    
    def get_layer_name(self) -> str:
        return "L2_Local_File"


class L3RealtimeDownloadLayer(QueryLayer):
    """L3 实时下载层"""
    
    def __init__(self, downloader):
        """Args: downloader: 数据下载器"""
        self.downloader = downloader
    
    def query(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Optional[pd.DataFrame]:
        """实时下载数据"""
        try:
            logger.info(f"L3 实时下载: {symbol} {interval}")
            
            # 触发下载
            df = self.downloader.download_single(
                symbol=symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is None or df.empty:
                logger.warning(f"L3下载失败: {symbol} {interval}")
                return None
            
            logger.info(f"L3下载成功: {symbol} {interval}, {len(df)} 条记录")
            return df
            
        except Exception as e:
            logger.error(f"L3下载异常: {e}")
            return None
    
    def get_layer_name(self) -> str:
        return "L3_Realtime_Download"


class L4DataSourceReplayLayer(QueryLayer):
    """L4 数据源回放层"""
    
    def __init__(self, replay_source):
        """Args: replay_source: 回放数据源"""
        self.replay = replay_source
    
    def query(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Optional[pd.DataFrame]:
        """从数据源回放"""
        try:
            logger.info(f"L4 数据源回放: {symbol} {interval}")
            
            df = self.replay.replay_data(
                symbol=symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is None or df.empty:
                logger.warning(f"L4回放失败: {symbol} {interval}")
                return None
            
            logger.info(f"L4回放成功: {symbol} {interval}, {len(df)} 条记录")
            return df
            
        except Exception as e:
            logger.error(f"L4回放异常: {e}")
            return None
    
    def get_layer_name(self) -> str:
        return "L4_DataSource_Replay"


# ==================== 统一查询管理器 ====================

class UnifiedDataManager:
    """统一数据查询管理器
    
    实现四层融合查询:
    1. L1 内存缓存(毫秒级)
    2. L2 本地文件(秒级)
    3. L3 实时下载(分钟级)
    4. L4 数据源回放(分钟级)
    
    查询流程:
    - 优先从L1查询
    - L1 miss → L2查询
    - L2 miss → L3下载
    - L3失败 → L4回放
    - 查询成功后回写上层缓存
    
    使用示例:
        manager = UnifiedDataManager(
            l1_cache=memory_cache,
            l2_storage=storage_manager,
            l3_downloader=downloader,
            l4_replay=replay_source
        )
        
        # 统一查询接口
        df = manager.query_unified(
            symbol="000001.SZ",
            interval="1d",
            start_date=date(2024, 1, 1)
        )
    """
    
    def __init__(
        self,
        l1_cache=None,
        l2_storage=None,
        l3_downloader=None,
        l4_replay=None
    ):
        """初始化统一查询管理器"""
        # 构建查询层列表
        self.layers: List[QueryLayer] = []
        
        if l1_cache:
            self.layers.append(L1MemoryCacheLayer(l1_cache))
        if l2_storage:
            self.layers.append(L2LocalFileLayer(l2_storage))
        if l3_downloader:
            self.layers.append(L3RealtimeDownloadLayer(l3_downloader))
        if l4_replay:
            self.layers.append(L4DataSourceReplayLayer(l4_replay))
        
        # 统计信息
        self._stats = {
            "total_queries": 0,
            "layer_hits": {layer.get_layer_name(): 0 for layer in self.layers},
            "failures": 0
        }
        
        logger.info(
            f"统一查询管理器已初始化: {len(self.layers)} 个查询层"
        )
    
    def query_unified(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Optional[pd.DataFrame]:
        """统一查询接口
        
        按优先级依次查询各层,第一个成功的结果即返回。
        
        Args:
            symbol: 品种代码
            interval: 周期
            start_date: 起始日期
            end_date: 结束日期
            
        Returns:
            DataFrame,所有层都失败返回None
        """
        self._stats["total_queries"] += 1
        
        # 按优先级查询各层
        for layer in self.layers:
            try:
                df = layer.query(symbol, interval, start_date, end_date)
                
                if df is not None and not df.empty:
                    # 查询成功
                    layer_name = layer.get_layer_name()
                    self._stats["layer_hits"][layer_name] += 1
                    
                    logger.info(
                        f"查询成功: {symbol} {interval}, "
                        f"来源={layer_name}, {len(df)} 条记录"
                    )
                    
                    # 回写上层缓存
                    self._writeback_cache(symbol, interval, df, layer)
                    
                    return df
                    
            except Exception as e:
                logger.error(
                    f"查询层异常 ({layer.get_layer_name()}): {e}"
                )
                continue
        
        # 所有层都失败
        self._stats["failures"] += 1
        logger.warning(f"查询失败: {symbol} {interval}, 所有层都无数据")
        return None
    
    def _writeback_cache(
        self,
        symbol: str,
        interval: str,
        df: pd.DataFrame,
        source_layer: QueryLayer
    ):
        """回写上层缓存
        
        规则:
        - L2成功 → 回写L1
        - L3成功 → 回写L2和L1
        - L4成功 → 回写L3、L2和L1
        """
        source_index = self.layers.index(source_layer)
        
        # 回写所有上层
        for i in range(source_index):
            upper_layer = self.layers[i]
            try:
                if isinstance(upper_layer, L1MemoryCacheLayer):
                    # 回写L1内存缓存
                    cache_key = f"{symbol}_{interval}"
                    upper_layer.cache.set(cache_key, df)
                    logger.debug(f"回写L1缓存: {cache_key}")
                    
                elif isinstance(upper_layer, L2LocalFileLayer):
                    # 回写L2本地文件
                    upper_layer.storage.save_data(symbol, interval, df)
                    logger.debug(f"回写L2文件: {symbol} {interval}")
                    
            except Exception as e:
                logger.error(f"回写缓存失败 ({upper_layer.get_layer_name()}): {e}")
    
    def get_stats(self) -> Dict:
        """获取查询统计"""
        total = self._stats["total_queries"]
        
        # 计算各层命中率
        layer_hit_rates = {}
        for layer_name, hits in self._stats["layer_hits"].items():
            rate = (hits / total * 100) if total > 0 else 0.0
            layer_hit_rates[layer_name] = round(rate, 2)
        
        return {
            "total_queries": total,
            "layer_hits": self._stats["layer_hits"],
            "layer_hit_rates": layer_hit_rates,
            "failures": self._stats["failures"],
            "success_rate": round(
                (total - self._stats["failures"]) / total * 100
                if total > 0 else 0.0,
                2
            )
        }
```

**架构优势**:

1. **四层融合**:
   - 自动降级查询
   - 最大化数据可用性
   - 最小化响应延迟

2. **缓存回写**:
   - 自动回写上层缓存
   - 提升后续查询性能
   - 减少下层压力

3. **统一接口**:
   - 屏蔽多层复杂性
   - 简化调用方使用
   - 易于扩展新层

4. **性能监控**:
   - 各层命中率统计
   - 查询成功率统计
   - 便于性能优化

### 8.2 统一查询业务规则

#### 8.2.1 查询优先级规则

**优先级顺序**:
1. L1 内存缓存(最高优先级)
2. L2 本地文件
3. L3 实时下载
4. L4 数据源回放(最低优先级)

**降级规则**:
- 上层返回None或empty → 自动查询下层
- 上层异常 → 自动查询下层
- 所有层失败 → 返回None

#### 8.2.2 缓存回写规则

**回写触发条件**:
- L2成功 → 回写L1
- L3成功 → 回写L2+L1
- L4成功 → 回写L3+L2+L1

**回写异常处理**:
- 回写失败不影响查询结果
- 记录warning日志
- 继续查询流程

---

## 九、实时推送业务规则

> **架构设计参考**:数据源架构请参考 [最佳实践文档 - 2.6 realtime_data_source.py](./data_module_vnpy新架构最佳实践cursor版.md#26-realtime_data_sourcepy---实时数据推送)

### 9.1 微观架构设计

#### 9.1.1 数据源适配器架构

**设计目标**:
- 统一多种实时数据源接口(TDX/Tushare/WebSocket)
- 适配器模式隔离数据源差异
- 自动重连和异常恢复
- 支持订阅管理和频率控制

**核心类设计**:

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass
import asyncio
import logging

logger = logging.getLogger(__name__)

# ==================== 实时数据模型 ====================

@dataclass
class RealtimeTick:
    """实时tick数据"""
    
    symbol: str
    datetime: str
    last_price: float
    volume: int
    amount: float
    bid1: float = 0.0
    ask1: float = 0.0
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "symbol": self.symbol,
            "datetime": self.datetime,
            "last_price": self.last_price,
            "volume": self.volume,
            "amount": self.amount,
            "bid1": self.bid1,
            "ask1": self.ask1
        }


# ==================== 数据源适配器 ====================

class RealtimeDataSource(ABC):
    """实时数据源抽象接口"""
    
    @abstractmethod
    async def connect(self) -> bool:
        """连接数据源
        
        Returns:
            True表示连接成功
        """
        pass
    
    @abstractmethod
    async def disconnect(self):
        """断开连接"""
        pass
    
    @abstractmethod
    async def subscribe(self, symbols: List[str]) -> bool:
        """订阅品种
        
        Args:
            symbols: 品种列表
            
        Returns:
            True表示订阅成功
        """
        pass
    
    @abstractmethod
    async def unsubscribe(self, symbols: List[str]) -> bool:
        """取消订阅"""
        pass
    
    @abstractmethod
    def get_source_name(self) -> str:
        """获取数据源名称"""
        pass


class TDXRealtimeSource(RealtimeDataSource):
    """TDX实时数据源适配器"""
    
    def __init__(self, host: str, port: int, callback: Callable):
        """
        Args:
            host: 服务器地址
            port: 服务器端口
            callback: 数据回调函数 callback(tick: RealtimeTick)
        """
        self.host = host
        self.port = port
        self.callback = callback
        self._client = None
        self._subscribed_symbols: List[str] = []
        self._running = False
    
    async def connect(self) -> bool:
        """连接TDX服务器"""
        try:
            from pytdx.hq import TdxHq_API
            
            self._client = TdxHq_API()
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._client.connect,
                self.host,
                self.port
            )
            
            logger.info(f"TDX连接成功: {self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"TDX连接失败: {e}")
            return False
    
    async def disconnect(self):
        """断开TDX连接"""
        self._running = False
        if self._client:
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._client.disconnect
            )
            logger.info("TDX连接已断开")
    
    async def subscribe(self, symbols: List[str]) -> bool:
        """订阅品种(启动轮询)
        
        TDX没有推送机制,使用轮询模拟
        """
        self._subscribed_symbols.extend(symbols)
        self._subscribed_symbols = list(set(self._subscribed_symbols))
        
        if not self._running:
            self._running = True
            asyncio.create_task(self._polling_loop())
        
        logger.info(f"TDX订阅成功: {len(self._subscribed_symbols)}个品种")
        return True
    
    async def unsubscribe(self, symbols: List[str]) -> bool:
        """取消订阅"""
        for symbol in symbols:
            if symbol in self._subscribed_symbols:
                self._subscribed_symbols.remove(symbol)
        
        logger.info(f"TDX取消订阅: 剩余{len(self._subscribed_symbols)}个品种")
        return True
    
    async def _polling_loop(self):
        """轮询循环(模拟推送)"""
        while self._running:
            try:
                # 批量获取实时行情
                for symbol in self._subscribed_symbols:
                    market, code = self._parse_symbol(symbol)
                    
                    # 获取实时行情
                    quote = await asyncio.get_event_loop().run_in_executor(
                        None,
                        self._client.get_security_quotes,
                        [(market, code)]
                    )
                    
                    if quote:
                        tick = self._convert_to_tick(quote[0], symbol)
                        # 触发回调
                        await self.callback(tick)
                
                # 轮询间隔(1秒)
                await asyncio.sleep(1.0)
                
            except Exception as e:
                logger.error(f"TDX轮询异常: {e}")
                await asyncio.sleep(5.0)  # 异常后等待5秒重试
    
    def _parse_symbol(self, symbol: str) -> tuple:
        """解析品种代码"""
        if symbol.endswith(".SZ"):
            return 0, symbol[:6]
        elif symbol.endswith(".SH"):
            return 1, symbol[:6]
        else:
            return 0, symbol
    
    def _convert_to_tick(self, quote: Dict, symbol: str) -> RealtimeTick:
        """转换TDX行情为Tick"""
        return RealtimeTick(
            symbol=symbol,
            datetime=quote.get("datetime", ""),
            last_price=quote.get("price", 0.0),
            volume=quote.get("vol", 0),
            amount=quote.get("amount", 0.0),
            bid1=quote.get("bid1", 0.0),
            ask1=quote.get("ask1", 0.0)
        )
    
    def get_source_name(self) -> str:
        return "TDX_Realtime"


# ==================== 订阅管理器 ====================

class SubscriptionManager:
    """订阅管理器
    
    职责:
    1. 管理多个数据源的订阅
    2. 自动重连和异常恢复
    3. 订阅频率控制
    4. 数据分发
    
    使用示例:
        manager = SubscriptionManager()
        
        # 添加数据源
        tdx_source = TDXRealtimeSource(host, port, callback)
        manager.add_source(tdx_source)
        
        # 订阅品种
        await manager.subscribe(["000001.SZ", "600000.SH"])
        
        # 启动
        await manager.start()
    """
    
    def __init__(self):
        """初始化订阅管理器"""
        self._sources: List[RealtimeDataSource] = []
        self._callbacks: List[Callable] = []
        self._subscribed_symbols: set = set()
        self._running = False
        
        logger.info("订阅管理器已初始化")
    
    def add_source(self, source: RealtimeDataSource):
        """添加数据源
        
        Args:
            source: 实时数据源
        """
        self._sources.append(source)
        logger.info(f"已添加数据源: {source.get_source_name()}")
    
    def add_callback(self, callback: Callable):
        """添加数据回调
        
        Args:
            callback: 回调函数 callback(tick: RealtimeTick)
        """
        self._callbacks.append(callback)
        logger.info("已添加数据回调")
    
    async def subscribe(self, symbols: List[str]) -> bool:
        """订阅品种
        
        Args:
            symbols: 品种列表
            
        Returns:
            True表示订阅成功
        """
        # 记录订阅
        self._subscribed_symbols.update(symbols)
        
        # 订阅所有数据源
        success = True
        for source in self._sources:
            result = await source.subscribe(symbols)
            success = success and result
        
        logger.info(
            f"订阅完成: {len(symbols)}个品种, "
            f"总订阅{len(self._subscribed_symbols)}个"
        )
        
        return success
    
    async def unsubscribe(self, symbols: List[str]) -> bool:
        """取消订阅
        
        Args:
            symbols: 品种列表
            
        Returns:
            True表示取消成功
        """
        # 移除订阅
        self._subscribed_symbols.difference_update(symbols)
        
        # 取消所有数据源订阅
        success = True
        for source in self._sources:
            result = await source.unsubscribe(symbols)
            success = success and result
        
        logger.info(
            f"取消订阅: {len(symbols)}个品种, "
            f"剩余{len(self._subscribed_symbols)}个"
        )
        
        return success
    
    async def start(self):
        """启动订阅管理器"""
        self._running = True
        
        # 连接所有数据源
        for source in self._sources:
            await source.connect()
        
        # 自动重连任务
        asyncio.create_task(self._auto_reconnect_loop())
        
        logger.info("订阅管理器已启动")
    
    async def stop(self):
        """停止订阅管理器"""
        self._running = False
        
        # 断开所有数据源
        for source in self._sources:
            await source.disconnect()
        
        logger.info("订阅管理器已停止")
    
    async def _auto_reconnect_loop(self):
        """自动重连循环"""
        while self._running:
            try:
                # 检查数据源连接状态
                for source in self._sources:
                    # 如果断线,尝试重连
                    # TODO: 实现连接状态检查
                    pass
                
                # 每30秒检查一次
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"自动重连异常: {e}")
                await asyncio.sleep(60)
    
    async def _dispatch_tick(self, tick: RealtimeTick):
        """分发tick数据到所有回调
        
        Args:
            tick: tick数据
        """
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(tick)
                else:
                    callback(tick)
            except Exception as e:
                logger.error(f"回调执行异常: {e}")
```

**架构优势**:

1. **适配器模式**:
   - 统一多种数据源接口
   - 隔离数据源实现差异
   - 易于扩展新数据源

2. **订阅管理**:
   - 集中管理订阅状态
   - 支持动态订阅/取消
   - 自动重连机制

3. **数据分发**:
   - 支持多个回调函数
   - 异步数据推送
   - 异常隔离

4. **轮询优化**:
   - TDX轮询间隔可配置
   - 批量获取行情提升效率
   - 异常重试机制

### 9.2 实时推送业务规则

#### 9.2.1 轮询频率控制规则

**轮询间隔设定**:
- **交易时段**: 1秒轮询间隔
- **非交易时段**: 暂停轮询,节省资源
- **异常情况**: 5秒重试间隔

**频率控制实现**:
```python
# 根据交易时段调整轮询间隔
if is_trading_time():
    interval = 1.0  # 交易时段1秒
else:
    interval = 60.0  # 非交易时段1分钟(或暂停)

await asyncio.sleep(interval)
```

#### 9.2.2 订阅限制规则

**订阅数量限制**:
- 单次订阅最大品种数: 100个
- 总订阅品种数上限: 500个
- 超过限制时分批订阅

**订阅优先级**:
- 自选股优先订阅
- 活跃品种优先订阅
- 冷门品种低优先级

---

## 十、文件监控业务规则

> **架构设计参考**:文件监控器架构请参考 [最佳实践文档 - 2.7 file_monitor.py](./data_module_vnpy新架构最佳实践cursor版.md#27-file_monitorpy---文件监控)

### 10.1 微观架构设计

#### 10.1.1 文件监控器架构

**设计目标**:
- 监控数据目录文件变化(创建/修改/删除)
- 防抖机制避免频繁触发
- 异步事件分发
- 支持多种监控策略

**核心类设计**:

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from pathlib import Path
from typing import Callable, Dict, List
import asyncio
import time
import logging

logger = logging.getLogger(__name__)

# ==================== 文件事件模型 ====================

class FileChangeEvent:
    """文件变化事件"""
    
    def __init__(
        self,
        event_type: str,  # created/modified/deleted
        file_path: Path,
        timestamp: float
    ):
        self.event_type = event_type
        self.file_path = file_path
        self.timestamp = timestamp
    
    def __repr__(self) -> str:
        return f"FileChangeEvent({self.event_type}, {self.file_path})"


# ==================== 防抖管理器 ====================

class DebounceManager:
    """防抖管理器
    
    避免同一文件短时间内多次触发事件
    
    使用示例:
        debounce = DebounceManager(interval=1.0)
        
        if debounce.should_trigger(file_path, event_type):
            # 执行事件处理
            handle_event()
            debounce.mark_triggered(file_path, event_type)
    """
    
    def __init__(self, interval: float = 1.0):
        """
        Args:
            interval: 防抖间隔(秒)
        """
        self.interval = interval
        # {file_path: {event_type: last_trigger_time}}
        self._trigger_history: Dict[str, Dict[str, float]] = {}
    
    def should_trigger(self, file_path: Path, event_type: str) -> bool:
        """判断是否应该触发事件
        
        Args:
            file_path: 文件路径
            event_type: 事件类型
            
        Returns:
            True表示应该触发
        """
        file_key = str(file_path)
        now = time.time()
        
        if file_key not in self._trigger_history:
            return True
        
        event_history = self._trigger_history[file_key]
        if event_type not in event_history:
            return True
        
        last_time = event_history[event_type]
        elapsed = now - last_time
        
        return elapsed >= self.interval
    
    def mark_triggered(self, file_path: Path, event_type: str):
        """标记事件已触发
        
        Args:
            file_path: 文件路径
            event_type: 事件类型
        """
        file_key = str(file_path)
        now = time.time()
        
        if file_key not in self._trigger_history:
            self._trigger_history[file_key] = {}
        
        self._trigger_history[file_key][event_type] = now
    
    def cleanup_old_records(self, max_age: float = 3600):
        """清理过期记录
        
        Args:
            max_age: 最大保留时间(秒)
        """
        now = time.time()
        expired_files = []
        
        for file_key, event_history in self._trigger_history.items():
            # 检查所有事件是否都过期
            all_expired = all(
                now - last_time > max_age
                for last_time in event_history.values()
            )
            if all_expired:
                expired_files.append(file_key)
        
        for file_key in expired_files:
            del self._trigger_history[file_key]
        
        if expired_files:
            logger.debug(f"清理{len(expired_files)}条过期防抖记录")


# ==================== 文件监控器 ====================

class DataFileMonitor:
    """数据文件监控器
    
    使用watchdog监控数据目录变化,支持防抖和异步事件分发。
    
    使用示例:
        monitor = DataFileMonitor(
            watch_dir=Path("./data"),
            debounce_interval=1.0
        )
        
        # 注册事件回调
        monitor.on_file_created(callback_created)
        monitor.on_file_modified(callback_modified)
        monitor.on_file_deleted(callback_deleted)
        
        # 启动监控
        monitor.start()
    """
    
    def __init__(
        self,
        watch_dir: Path,
        debounce_interval: float = 1.0,
        file_pattern: str = "*.parquet"
    ):
        """
        Args:
            watch_dir: 监控目录
            debounce_interval: 防抖间隔(秒)
            file_pattern: 文件匹配模式
        """
        self.watch_dir = Path(watch_dir)
        self.file_pattern = file_pattern
        self.debounce = DebounceManager(interval=debounce_interval)
        
        # 事件回调
        self._on_created_callbacks: List[Callable] = []
        self._on_modified_callbacks: List[Callable] = []
        self._on_deleted_callbacks: List[Callable] = []
        
        # watchdog组件
        self._observer = None
        self._event_handler = None
        
        logger.info(
            f"文件监控器已初始化: watch_dir={watch_dir}, "
            f"debounce={debounce_interval}s"
        )
    
    def on_file_created(self, callback: Callable):
        """注册文件创建回调
        
        Args:
            callback: 回调函数 callback(event: FileChangeEvent)
        """
        self._on_created_callbacks.append(callback)
    
    def on_file_modified(self, callback: Callable):
        """注册文件修改回调"""
        self._on_modified_callbacks.append(callback)
    
    def on_file_deleted(self, callback: Callable):
        """注册文件删除回调"""
        self._on_deleted_callbacks.append(callback)
    
    def start(self):
        """启动文件监控"""
        # 创建事件处理器
        self._event_handler = _FileEventHandler(
            monitor=self,
            file_pattern=self.file_pattern
        )
        
        # 创建观察者
        self._observer = Observer()
        self._observer.schedule(
            self._event_handler,
            str(self.watch_dir),
            recursive=True
        )
        self._observer.start()
        
        logger.info(f"文件监控已启动: {self.watch_dir}")
    
    def stop(self):
        """停止文件监控"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            logger.info("文件监控已停止")
    
    async def _dispatch_event(self, event: FileChangeEvent):
        """分发事件到回调
        
        Args:
            event: 文件变化事件
        """
        # 选择对应的回调列表
        if event.event_type == "created":
            callbacks = self._on_created_callbacks
        elif event.event_type == "modified":
            callbacks = self._on_modified_callbacks
        elif event.event_type == "deleted":
            callbacks = self._on_deleted_callbacks
        else:
            return
        
        # 执行所有回调
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"事件回调异常: {e}", exc_info=True)


class _FileEventHandler(FileSystemEventHandler):
    """watchdog事件处理器(内部类)"""
    
    def __init__(self, monitor: DataFileMonitor, file_pattern: str):
        self.monitor = monitor
        self.file_pattern = file_pattern
        super().__init__()
    
    def on_created(self, event: FileSystemEvent):
        """文件创建事件"""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        if not file_path.match(self.file_pattern):
            return
        
        # 防抖检查
        if not self.monitor.debounce.should_trigger(file_path, "created"):
            return
        
        # 创建事件对象
        change_event = FileChangeEvent(
            event_type="created",
            file_path=file_path,
            timestamp=time.time()
        )
        
        # 标记已触发
        self.monitor.debounce.mark_triggered(file_path, "created")
        
        # 异步分发事件
        asyncio.create_task(self.monitor._dispatch_event(change_event))
        
        logger.debug(f"文件创建: {file_path}")
    
    def on_modified(self, event: FileSystemEvent):
        """文件修改事件"""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        if not file_path.match(self.file_pattern):
            return
        
        # 防抖检查
        if not self.monitor.debounce.should_trigger(file_path, "modified"):
            return
        
        change_event = FileChangeEvent(
            event_type="modified",
            file_path=file_path,
            timestamp=time.time()
        )
        
        self.monitor.debounce.mark_triggered(file_path, "modified")
        asyncio.create_task(self.monitor._dispatch_event(change_event))
        
        logger.debug(f"文件修改: {file_path}")
    
    def on_deleted(self, event: FileSystemEvent):
        """文件删除事件"""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        if not file_path.match(self.file_pattern):
            return
        
        # 防抖检查
        if not self.monitor.debounce.should_trigger(file_path, "deleted"):
            return
        
        change_event = FileChangeEvent(
            event_type="deleted",
            file_path=file_path,
            timestamp=time.time()
        )
        
        self.monitor.debounce.mark_triggered(file_path, "deleted")
        asyncio.create_task(self.monitor._dispatch_event(change_event))
        
        logger.debug(f"文件删除: {file_path}")
```

**架构优势**:

1. **防抖机制**:
   - 避免频繁触发
   - 可配置防抖间隔
   - 自动清理过期记录

2. **异步分发**:
   - 事件异步处理
   - 不阻塞监控线程
   - 支持多个回调

3. **灵活配置**:
   - 可配置监控目录
   - 可配置文件模式
   - 支持递归监控

4. **异常隔离**:
   - 回调异常不影响监控
   - 详细的错误日志
   - 自动恢复

### 10.2 文件监控业务规则

#### 10.2.1 防抖间隔设定规则

**防抖间隔配置**:
- **创建事件**: 1秒防抖间隔
- **修改事件**: 1秒防抖间隔
- **删除事件**: 0.5秒防抖间隔(更敏感)

**防抖触发判断**:
```python
# 同一文件同一事件类型,间隔小于防抖时间则跳过
if (now - last_trigger_time) < debounce_interval:
    return False  # 跳过此次触发
```

#### 10.2.2 监控范围规则

**监控目录**:
- 监控所有数据周期目录(1d/1h/30m/5m)
- 递归监控子目录
- 只监控.parquet文件

**排除规则**:
- 临时文件(.tmp)
- 隐藏文件(.开头)
- 非parquet文件

#### 10.2.3 事件响应规则

**文件创建响应**:
- 触发数据质量扫描
- 更新缓存索引
- 发送UI更新事件

**文件修改响应**:
- 清除L1内存缓存
- 触发重新验证
- 更新最后修改时间

**文件删除响应**:
- 清除所有缓存
- 更新数据索引
- 记录删除日志

---

## 十一、native_iocp集成业务规则

> **架构设计参考**：native_iocp技术架构请参考 [最佳实践文档 - 3. native_iocp深度集成方案](./data_module_vnpy新架构最佳实践cursor版.md#三native_iocp深度集成方案)

### 11.1 微观架构设计

#### 11.1.1 I/O策略工厂架构

**设计目标**：
- 封装三种I/O模式的选择和降级逻辑
- 提供统一的文件读写接口
- 支持运行时动态切换I/O策略
- 记录性能监控指标

**核心类设计**：

```python
from abc import ABC, abstractmethod
from typing import Optional, Union, Any
from pathlib import Path
import asyncio
import time
import pandas as pd
from dataclasses import dataclass

@dataclass
class IOPerformanceMetrics:
    """I/O性能指标"""
    io_mode: str  # "native_iocp" / "aiofiles" / "sync"
    file_size_mb: float
    elapsed_time: float
    throughput_mbps: float
    latency_ms: float
    success: bool
    error_msg: Optional[str] = None


class IOStrategy(ABC):
    """文件I/O策略抽象基类"""
    
    @abstractmethod
    async def read_file(self, file_path: Path) -> bytes:
        """异步读取文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件内容字节
        """
        pass
    
    @abstractmethod
    async def write_file(self, file_path: Path, data: bytes) -> None:
        """异步写入文件
        
        Args:
            file_path: 文件路径
            data: 要写入的数据
        """
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        pass


class NativeIOCPStrategy(IOStrategy):
    """native_iocp真异步I/O策略（Level 1）"""
    
    def __init__(self):
        # 尝试导入native_iocp
        try:
            from backend.infrastructure.native_iocp import compat_aopen
            self.compat_aopen = compat_aopen
            self.available = True
            logger.info("✅ native_iocp策略初始化成功")
        except ImportError as e:
            self.compat_aopen = None
            self.available = False
            logger.warning(f"⚠️ native_iocp不可用: {e}")
    
    async def read_file(self, file_path: Path) -> bytes:
        """IOCP异步读取"""
        if not self.available:
            raise RuntimeError("native_iocp不可用")
        
        async with await self.compat_aopen(file_path, 'rb') as f:
            data = await f.read()
        return data
    
    async def write_file(self, file_path: Path, data: bytes) -> None:
        """IOCP异步写入"""
        if not self.available:
            raise RuntimeError("native_iocp不可用")
        
        async with await self.compat_aopen(file_path, 'wb') as f:
            await f.write(data)
    
    def get_strategy_name(self) -> str:
        return "native_iocp"


class SyncIOStrategy(IOStrategy):
    """同步I/O策略（Level 3，最终降级）"""
    
    async def read_file(self, file_path: Path) -> bytes:
        """在executor中执行同步读取"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            lambda: file_path.read_bytes()
        )
    
    async def write_file(self, file_path: Path, data: bytes) -> None:
        """在executor中执行同步写入"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, 
            lambda: file_path.write_bytes(data)
        )
    
    def get_strategy_name(self) -> str:
        return "sync"


class IOStrategyFactory:
    """I/O策略工厂
    
    负责创建、管理、切换I/O策略
    """
    
    def __init__(self):
        # 初始化所有策略
        self._strategies = {
            "native_iocp": NativeIOCPStrategy(),
            "sync": SyncIOStrategy()
        }
        
        # 选择默认策略
        self._current_strategy = self._select_default_strategy()
        
        # 性能监控
        self._metrics_history = []
        self._strategy_usage_count = {
            "native_iocp": 0,
            "sync": 0
        }
        
        logger.info(
            f"🚀 I/O策略工厂初始化完成，默认策略: {self._current_strategy.get_strategy_name()}"
        )
    
    def _select_default_strategy(self) -> IOStrategy:
        """选择默认策略"""
        # 优先选择native_iocp
        if self._strategies["native_iocp"].available:
            return self._strategies["native_iocp"]
        # 降级到同步I/O
        return self._strategies["sync"]
    
    async def read_parquet_async(self, file_path: Union[str, Path]) -> pd.DataFrame:
        """异步读取Parquet文件（带性能监控）
        
        Returns:
            DataFrame
        """
        file_path = Path(file_path)
        start_time = time.time()
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        
        try:
            # 尝试当前策略
            data = await self._current_strategy.read_file(file_path)
            
            # 解析Parquet
            import pyarrow.parquet as pq
            from io import BytesIO
            table = pq.read_table(BytesIO(data))
            df = table.to_pandas()
            
            # 记录成功指标
            metrics = self._record_metrics(
                io_mode=self._current_strategy.get_strategy_name(),
                file_size_mb=file_size_mb,
                start_time=start_time,
                success=True
            )
            
            logger.debug(
                f"📁 读取Parquet: {file_path.name}, "
                f"{file_size_mb:.2f} MB, {metrics.elapsed_time:.3f}s, "
                f"{metrics.throughput_mbps:.2f} MB/s, 模式={metrics.io_mode}"
            )
            
            return df
            
        except Exception as e:
            # 记录失败指标
            self._record_metrics(
                io_mode=self._current_strategy.get_strategy_name(),
                file_size_mb=file_size_mb,
                start_time=start_time,
                success=False,
                error_msg=str(e)
            )
            
            # 尝试降级
            fallback_strategy = self._strategies["sync"]
            if fallback_strategy != self._current_strategy:
                logger.warning(
                    f"⚠️ {self._current_strategy.get_strategy_name()}读取失败，"
                    f"降级到{fallback_strategy.get_strategy_name()}: {e}"
                )
                
                # 使用降级策略重试
                data = await fallback_strategy.read_file(file_path)
                import pyarrow.parquet as pq
                from io import BytesIO
                table = pq.read_table(BytesIO(data))
                return table.to_pandas()
            else:
                raise
    
    async def write_parquet_async(
        self, 
        file_path: Union[str, Path], 
        df: pd.DataFrame
    ) -> bool:
        """异步写入Parquet文件（带性能监控）
        
        Returns:
            bool: 成功/失败
        """
        file_path = Path(file_path)
        start_time = time.time()
        
        try:
            # 先序列化到内存
            from io import BytesIO
            buffer = BytesIO()
            df.to_parquet(buffer, engine='pyarrow', compression='snappy')
            data = buffer.getvalue()
            
            file_size_mb = len(data) / (1024 * 1024)
            
            # 异步写入
            await self._current_strategy.write_file(file_path, data)
            
            # 记录成功指标
            metrics = self._record_metrics(
                io_mode=self._current_strategy.get_strategy_name(),
                file_size_mb=file_size_mb,
                start_time=start_time,
                success=True
            )
            
            logger.debug(
                f"💾 写入Parquet: {file_path.name}, "
                f"{file_size_mb:.2f} MB, {metrics.elapsed_time:.3f}s, "
                f"{metrics.throughput_mbps:.2f} MB/s, 模式={metrics.io_mode}"
            )
            
            return True
            
        except Exception as e:
            # 记录失败指标
            self._record_metrics(
                io_mode=self._current_strategy.get_strategy_name(),
                file_size_mb=0,
                start_time=start_time,
                success=False,
                error_msg=str(e)
            )
            
            # 尝试降级
            fallback_strategy = self._strategies["sync"]
            if fallback_strategy != self._current_strategy:
                logger.warning(
                    f"⚠️ {self._current_strategy.get_strategy_name()}写入失败，"
                    f"降级到{fallback_strategy.get_strategy_name()}: {e}"
                )
                
                # 使用降级策略重试
                await fallback_strategy.write_file(file_path, data)
                return True
            else:
                logger.error(f"❌ 写入Parquet失败: {e}", exc_info=True)
                return False
    
    def _record_metrics(
        self,
        io_mode: str,
        file_size_mb: float,
        start_time: float,
        success: bool,
        error_msg: Optional[str] = None
    ) -> IOPerformanceMetrics:
        """记录性能指标"""
        elapsed_time = time.time() - start_time
        throughput = file_size_mb / elapsed_time if elapsed_time > 0 else 0
        latency_ms = elapsed_time * 1000
        
        metrics = IOPerformanceMetrics(
            io_mode=io_mode,
            file_size_mb=file_size_mb,
            elapsed_time=elapsed_time,
            throughput_mbps=throughput,
            latency_ms=latency_ms,
            success=success,
            error_msg=error_msg
        )
        
        # 记录历史指标
        self._metrics_history.append(metrics)
        
        # 统计使用次数
        if success:
            self._strategy_usage_count[io_mode] += 1
        
        return metrics
    
    def get_performance_report(self) -> Dict[str, Any]:
        """生成性能报告"""
        if not self._metrics_history:
            return {"total_operations": 0}
        
        total = len(self._metrics_history)
        success_count = sum(1 for m in self._metrics_history if m.success)
        
        # 按模式统计
        by_mode = {}
        for mode in ["native_iocp", "sync"]:
            mode_metrics = [m for m in self._metrics_history if m.io_mode == mode]
            if mode_metrics:
                avg_throughput = sum(m.throughput_mbps for m in mode_metrics) / len(mode_metrics)
                avg_latency = sum(m.latency_ms for m in mode_metrics) / len(mode_metrics)
                by_mode[mode] = {
                    "count": len(mode_metrics),
                    "avg_throughput_mbps": avg_throughput,
                    "avg_latency_ms": avg_latency
                }
        
        return {
            "total_operations": total,
            "success_count": success_count,
            "success_rate": (success_count / total) * 100 if total > 0 else 0,
            "by_mode": by_mode,
            "current_strategy": self._current_strategy.get_strategy_name()
        }
```

**架构优势**：

1. **策略模式**：
   - 封装多种I/O策略
   - 运行时动态切换
   - 扩展性强

2. **自动降级**：
   - native_iocp失败→同步I/O
   - 透明切换，不影响上层
   - 详细的降级日志

3. **性能监控**：
   - 自动记录各项指标
   - 支持按模式统计
   - 生成性能报告

4. **统一接口**：
   - 屏蔽底层策略差异
   - 简化上层调用
   - 便于维护

---

### 11.2 三级降级策略

**降级层次设计**：

**Level 1: native_iocp真异步I/O（优先）**
- **技术实现**：Windows IOCP（I/O Completion Ports）
- **性能特征**：0延迟，真正的异步I/O，无线程池开销
- **适用场景**：Windows平台，native_iocp模块可用
- **触发条件**：`_USE_IOCP == True` 且 `compat_aopen is not None`

**Level 2: aiofiles异步I/O（降级）**
- **技术实现**：基于线程池的异步I/O模拟
- **性能特征**：~5ms延迟，线程池模拟异步
- **适用场景**：Windows平台，但native_iocp不可用
- **触发条件**：native_iocp导入失败或运行时异常

**Level 3: 同步I/O（最终降级）**
- **技术实现**：在asyncio executor中执行同步读写
- **性能特征**：~20ms延迟，阻塞I/O
- **适用场景**：aiofiles也不可用或发生异常
- **触发条件**：所有异步方案失败

#### 11.1.1 降级触发条件详细规则

**ImportError降级（模块级别）**：
```python
# 在模块加载阶段检测
try:
    from backend.infrastructure.native_iocp import compat_aopen
    _USE_IOCP = True
except ImportError:
    compat_aopen = None
    _USE_IOCP = False
    # 降级到Level 2或Level 3
```

**运行时异常降级（函数级别）**：
```python
async def _read_parquet_async(file_path: Union[str, Path]) -> pd.DataFrame:
    try:
        if _USE_IOCP and compat_aopen is not None:
            # Level 1: 尝试native_iocp
            file_obj = await compat_aopen(file_path, 'rb')
            # ... IOCP读取逻辑
    except Exception as e:
        logger.warning(f"native_iocp读取失败，降级到同步读取: {e}")
        # Level 3: 降级到同步读取（跳过Level 2以简化逻辑）
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, pd.read_parquet, file_path)
```

**降级判定标准**：
1. **模块不可用**：`ImportError` → 自动降级到Level 2/3
2. **文件打开失败**：`compat_aopen()` 异常 → 降级到Level 3
3. **读取异常**：`file_obj.read()` 异常 → 降级到Level 3
4. **解析异常**：`pyarrow.parquet.read_table()` 异常 → 降级到Level 3

### 11.2 日志记录规范

#### 11.2.1 降级日志规范

**WARNING级别：记录降级原因**
```python
logger.warning(
    "⚠️ native_iocp读取失败，降级到同步读取: %s",
    error_message
)
```

**记录内容要求**：
- 原因描述：具体的异常类型和消息
- 降级目标：明确降级到哪个Level
- 文件路径：失败的文件路径（DEBUG级别）

**INFO级别：记录实际使用的I/O模式**
```python
# 在StorageManager初始化时记录
if _USE_IOCP:
    logger.info("✓ 使用native_iocp真异步I/O（Level 1）")
else:
    logger.info("⚠️ native_iocp不可用，使用降级方案（Level 2/3）")
```

**DEBUG级别：记录性能监控数据**
```python
logger.debug(
    "文件读取性能: 文件=%s, 大小=%d MB, 耗时=%.3f秒, 模式=%s",
    file_path,
    file_size_mb,
    elapsed_time,
    io_mode  # "native_iocp" / "aiofiles" / "sync"
)
```

#### 11.2.2 日志输出位置

**AI日志文件**：
- 所有降级事件必须写入AI日志文件
- 文件路径：`C:\Users\USER\Desktop\terminal_v0.50\logs\data_storage_{timestamp}.log`
- 日志格式：包含时间戳、级别图标、模块名、详细消息

**终端日志**：
- WARNING级别降级日志输出到终端（根据terminal_mode配置）
- INFO级别初始化日志输出到终端
- DEBUG级别性能日志仅写入文件，不输出到终端

### 11.3 性能监控指标定义

#### 11.3.1 I/O模式性能基准

| I/O模式 | 延迟 | 吞吐量 | CPU占用 | 适用场景 |
|---------|------|--------|---------|----------|
| native_iocp | 0ms | 最高 | 最低 | Windows平台，生产环境 |
| aiofiles | ~5ms | 中等 | 中等 | 降级场景，兼容性优先 |
| 同步读取 | ~20ms | 最低 | 最高 | 最终降级，确保功能 |

#### 11.3.2 性能监控指标

**吞吐量指标**：
- **指标名称**：`io_throughput_mbps`
- **计算公式**：`file_size_mb / elapsed_time`
- **单位**：MB/s
- **记录频率**：每次文件读写操作

**延迟指标**：
- **指标名称**：`io_latency_ms`
- **计算公式**：`elapsed_time * 1000`
- **单位**：毫秒
- **记录频率**：每次文件读写操作

**模式使用统计**：
- **指标名称**：`io_mode_usage_count`
- **记录内容**：`{"native_iocp": count1, "aiofiles": count2, "sync": count3}`
- **统计周期**：每小时汇总一次

#### 11.3.3 性能监控实现示例

```python
import time
from pathlib import Path

async def _read_parquet_async_with_metrics(
    file_path: Union[str, Path]
) -> pd.DataFrame:
    """异步读取Parquet文件（带性能监控）"""
    start_time = time.time()
    file_size_mb = Path(file_path).stat().st_size / (1024 * 1024)
    io_mode = "unknown"
    
    try:
        if _USE_IOCP and compat_aopen is not None:
            # Level 1: native_iocp
            io_mode = "native_iocp"
            file_obj = await compat_aopen(file_path, 'rb')
            async with file_obj:
                data = await file_obj.read()
            
            import pyarrow.parquet as pq
            import io
            table = pq.read_table(io.BytesIO(data))
            df = table.to_pandas()
        else:
            # Level 3: 同步读取
            io_mode = "sync"
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, pd.read_parquet, file_path)
        
        # 计算性能指标
        elapsed_time = time.time() - start_time
        throughput = file_size_mb / elapsed_time if elapsed_time > 0 else 0
        latency_ms = elapsed_time * 1000
        
        # 记录性能日志
        logger.debug(
            "文件读取性能: 文件=%s, 大小=%.2f MB, "
            "耗时=%.3f秒, 吞吐量=%.2f MB/s, 延迟=%.2f ms, 模式=%s",
            file_path, file_size_mb, elapsed_time, 
            throughput, latency_ms, io_mode
        )
        
        return df
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.warning(
            "异步读取Parquet失败，降级到同步读取: %s （耗时: %.3f秒）",
            e, elapsed_time
        )
        # 最终降级
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, pd.read_parquet, file_path)
```

### 11.4 应用场景详细说明

#### 11.4.1 Parquet文件异步读写

**应用位置**：`data_storage.py` - `StorageManager`

**读取场景**：
```python
class StorageManager:
    async def load_data_async(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Optional[pd.DataFrame]:
        """异步加载数据（使用native_iocp）"""
        file_path = self.get_data_path(symbol, interval)
        
        if not file_path.exists():
            return None
        
        try:
            # 🚀 使用native_iocp异步读取
            from backend.infrastructure.native_iocp import compat_aopen
            from io import BytesIO
            
            async with await compat_aopen(file_path, 'rb') as f:
                data = await f.read()
            
            # 解析Parquet
            df = pd.read_parquet(BytesIO(data))
            
            # 日期过滤
            if start_date or end_date:
                df = self._filter_by_date(df, start_date, end_date)
            
            return df
        except Exception as e:
            logger.error(f"加载数据失败: {e}", exc_info=True)
            return None
```

**写入场景**：
```python
    async def save_data_async(
        self,
        symbol: str,
        interval: str,
        df: pd.DataFrame
    ) -> bool:
        """异步保存数据（使用native_iocp）"""
        file_path = self.get_data_path(symbol, interval)
        
        try:
            # 🚀 使用native_iocp异步写入
            from backend.infrastructure.native_iocp import compat_aopen
            from io import BytesIO
            
            # 先同步到内存
            buffer = BytesIO()
            df.to_parquet(buffer, engine='pyarrow', compression='snappy')
            data = buffer.getvalue()
            
            # 异步写入文件
            async with await compat_aopen(file_path, 'wb') as f:
                await f.write(data)
            
            return True
        except Exception as e:
            logger.error(f"保存数据失败: {e}", exc_info=True)
            return False
```

#### 11.4.2 缓存文件异步读写

**应用位置**：`data_module.py` - `DailyCacheManager`

**异步保存缓存**：
```python
class DailyCacheManager:
    @staticmethod
    async def save_with_date_async(data: Any, cache_file: Path) -> bool:
        """异步保存数据并记录日期（使用native_iocp）"""
        try:
            from backend.infrastructure.native_iocp import compat_aopen
            import json
            
            # 构建缓存对象
            cache_obj = {
                "cache_date": DailyCacheManager.get_today(),
                "data": data
            }
            
            # 序列化为JSON
            json_data = json.dumps(
                cache_obj, 
                ensure_ascii=False, 
                indent=2, 
                default=str
            )
            
            # 🚀 使用native_iocp异步写入
            async with await compat_aopen(cache_file, 'w', encoding='utf-8') as f:
                await f.write(json_data)
            
            logger.debug("缓存已保存: %s (日期: %s)", cache_file, cache_obj["cache_date"])
            return True
            
        except Exception as e:
            logger.error("保存缓存失败 (%s): %s", cache_file, e, exc_info=True)
            return False
```

**异步加载缓存**：
```python
    @staticmethod
    async def load_with_validation_async(
        cache_file: Path
    ) -> Tuple[Optional[Any], Optional[str], bool]:
        """异步加载数据并验证日期（使用native_iocp）"""
        try:
            if not cache_file.exists():
                return None, None, False
            
            from backend.infrastructure.native_iocp import compat_aopen
            import json
            
            # 🚀 使用native_iocp异步读取
            async with await compat_aopen(cache_file, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            if not content.strip():
                logger.warning("缓存文件为空: %s", cache_file)
                return None, None, False
            
            cache_obj = json.loads(content)
            data = cache_obj.get("data")
            cache_date = cache_obj.get("cache_date")
            
            # 验证日期
            is_valid = DailyCacheManager.is_cache_valid(cache_date)
            
            return data, cache_date, is_valid
            
        except Exception as e:
            logger.error("加载缓存失败: %s", e, exc_info=True)
            return None, None, False
```

#### 11.4.3 质量扫描文件异步读取

**应用位置**：`data_quality.py` - `DataSensor`

```python
async def _scan_symbol_quality_async(
    symbol: str, 
    intervals: List[str], 
    data_dir: str
) -> Optional[dict]:
    """异步扫描单个品种的质量（使用native_iocp）"""
    try:
        quality_dict = {"symbol": symbol, "intervals": {}}
        
        for interval in intervals:
            file_path = Path(data_dir) / interval / f"{symbol}.parquet"
            
            if not file_path.exists():
                quality_dict["intervals"][interval] = {"missing": True}
                continue
            
            # 🚀 使用native_iocp异步读取
            df = await _read_parquet_async(file_path)
            
            # 执行质量检查
            quality_result = validate_data_quality(df)
            quality_dict["intervals"][interval] = quality_result
        
        return quality_dict
        
    except Exception as e:
        logger.error(f"异步扫描品种 {symbol} 失败: {e}")
        return None
```

---

## 十二、子进程日志配置业务规则

> **架构设计参考**：日志系统架构请参考 [统一日志系统文档](../system_vnpy/系统监控完整集成指南.md)

### 12.1 微观架构设计

#### 12.1.1 子进程日志配置管理器架构

**设计目标**：
- 统一管理所有子进程的日志配置
- 确保子进程日志正确接入LogHub
- 支持降级机制，保障日志输出
- 自动清理继承的handler

**核心类设计**：

```python
import logging
import threading
from typing import Optional, Dict, List
from dataclasses import dataclass
from enum import Enum

class SubprocessLogLevel(Enum):
    """子进程日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class SubprocessLogConfig:
    """子进程日志配置"""
    worker_id: int
    task_type: str  # "worker"/"quality_scan"/"ipo"/"finance"
    logger_name: str
    level: SubprocessLogLevel = SubprocessLogLevel.DEBUG
    

class SubprocessLogConfigManager:
    """子进程日志配置管理器
    
    统一管理所有子进程的日志配置，提供标准化的配置接口
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._configs: Dict[str, SubprocessLogConfig] = {}
            self._loghub_available = True
            self._initialized = True
    
    def configure_subprocess_logging(
        self,
        worker_id: int,
        task_type: str = "worker"
    ) -> logging.Logger:
        """配置子进程日志系统，接入LogHub统一路由
        
        四步配置流程：
        1. 获取LogHub实例
        2. 清理继承的handler
        3. 添加LogHub到root logger
        4. 创建子进程专用logger
        
        Args:
            worker_id: 子进程ID
            task_type: 任务类型
            
        Returns:
            配置好的logger实例
        """
        import sys
        
        try:
            # Step 1: 获取LogHub实例
            from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub
            hub = get_logging_hub()
            
            # Step 2: 清理子进程继承的所有handler（避免重复输出）
            root_logger = logging.getLogger()
            cleared_count = self._clear_inherited_handlers(root_logger)
            
            # Step 3: 将LogHub添加到root logger
            root_logger.addHandler(hub)
            root_logger.setLevel(logging.DEBUG)
            
            # Step 4: 创建子进程专用logger（带worker_id标识）
            logger_name = f"subprocess.{task_type}.{worker_id}"
            subprocess_logger = logging.getLogger(logger_name)
            subprocess_logger.propagate = True  # 让日志传播到root logger
            
            # 记录配置
            config = SubprocessLogConfig(
                worker_id=worker_id,
                task_type=task_type,
                logger_name=logger_name,
                level=SubprocessLogLevel.DEBUG
            )
            self._configs[logger_name] = config
            
            subprocess_logger.info(
                f"✅ 子进程 {worker_id} ({task_type}) 日志系统已接入LogHub "
                f"(清理{cleared_count}个handler)"
            )
            
            return subprocess_logger
            
        except Exception as e:
            # 降级：如果LogHub配置失败，使用标准logger
            self._loghub_available = False
            fallback_logger = self._create_fallback_logger(worker_id, task_type)
            fallback_logger.warning(
                f"⚠️ 子进程 {worker_id} ({task_type}) LogHub配置失败，使用降级日志: {e}"
            )
            return fallback_logger
    
    def _clear_inherited_handlers(self, root_logger: logging.Logger) -> int:
        """清理继承的handler
        
        Args:
            root_logger: root logger实例
            
        Returns:
            清理的handler数量
        """
        cleared_count = 0
        
        # 遍历所有handler（使用切片复制，避免遍历时修改）
        for handler in root_logger.handlers[:]:
            try:
                # 介root logger移除handler
                root_logger.removeHandler(handler)
                
                # 关闭handler，释放资源
                # - FileHandler: 关闭文件句柄
                # - StreamHandler: 刷新缓冲区
                # - SocketHandler: 关闭网络连接
                handler.close()
                
                cleared_count += 1
            except Exception as e:
                # 忽略清理异常，继续清理其他handler
                pass
        
        return cleared_count
    
    def _create_fallback_logger(
        self,
        worker_id: int,
        task_type: str
    ) -> logging.Logger:
        """创建降级logger（LogHub不可用时）
        
        Args:
            worker_id: 子进程ID
            task_type: 任务类型
            
        Returns:
            降级logger
        """
        logger_name = f"subprocess.{task_type}.{worker_id}.fallback"
        fallback_logger = logging.getLogger(logger_name)
        
        # 配置基本的StreamHandler
        if not fallback_logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] [Worker-%(name)s] %(message)s'
            )
            handler.setFormatter(formatter)
            fallback_logger.addHandler(handler)
            fallback_logger.setLevel(logging.DEBUG)
        
        return fallback_logger
    
    def get_config(self, logger_name: str) -> Optional[SubprocessLogConfig]:
        """获取指定logger的配置"""
        return self._configs.get(logger_name)
    
    def get_all_configs(self) -> Dict[str, SubprocessLogConfig]:
        """获取所有配置"""
        return dict(self._configs)
    
    def is_loghub_available(self) -> bool:
        """检查LogHub是否可用"""
        return self._loghub_available


# 全局实例
def get_subprocess_log_config_manager() -> SubprocessLogConfigManager:
    """获取全局子进程日志配置管理器"""
    return SubprocessLogConfigManager()


# 便捷函数
def configure_subprocess_logging(
    worker_id: int,
    task_type: str = "worker"
) -> logging.Logger:
    """配置子进程日志（便捷函数）
    
    封装细节，提供简单的接口
    
    Args:
        worker_id: 子进程ID
        task_type: 任务类型 (worker/quality_scan/ipo/finance等)
        
    Returns:
        配置好的logger
    """
    manager = get_subprocess_log_config_manager()
    return manager.configure_subprocess_logging(worker_id, task_type)
```

**架构优势**：

1. **统一管理**：
   - 单例模式，全局统一配置
   - 集中管理所有子进程配置
   - 便于监控和调试

2. **自动清理**：
   - 自动清理继承的handler
   - 避免日志重复输出
   - 正确释放资源

3. **降级机制**：
   - LogHub不可用时自动降级
   - 保障日志输出
   - 详细的降级日志

4. **标准化命名**：
   - 统一的logger命名格式
   - 支持多种任务类型
   - 便于LogHub路由

---

### 12.2 LogHub统一路由接入流程

#### 12.1.1 四步接入流程

**Step 1: 获取LogHub实例**
```python
from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub

hub = get_logging_hub()
```

**功能说明**：
- 获取全局单例LogHub实例
- LogHub负责统一路由所有日志消息
- 支持3层路由架构（模块→阶段→全局）

**Step 2: 清理继承的handler**
```python
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)
    handler.close()
```

**功能说明**：
- 子进程会继承父进程的所有handler
- 必须清理旧handler，否则日志重复输出
- `handler.close()`确保资源释放

**Step 3: 添加LogHub到root logger**
```python
root_logger.addHandler(hub)
root_logger.setLevel(logging.DEBUG)
```

**功能说明**：
- 将LogHub作为唯一的handler添加到root logger
- 设置DEBUG级别确保捕获所有日志
- 通过LogHub的路由规则控制实际输出

**Step 4: 创建子进程专用logger**
```python
logger_name = f"subprocess.{task_type}.{worker_id}"
subprocess_logger = logging.getLogger(logger_name)
subprocess_logger.propagate = True
```

**功能说明**：
- 使用标准化命名格式标识子进程
- `propagate=True`让日志传播到root logger
- root logger的LogHub会处理所有传播的日志

#### 12.1.2 完整配置函数实现

```python
def _configure_subprocess_logging(
    worker_id: int, 
    task_type: str = "worker"
):
    """配置子进程日志系统，接入LogHub统一路由
    
    Args:
        worker_id: 子进程ID
        task_type: 任务类型（worker/quality_scan/ipo/finance等）
    
    Returns:
        配置好的logger实例
    """
    import logging
    import sys
    
    try:
        # Step 1: 获取LogHub实例
        from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub
        hub = get_logging_hub()
        
        # Step 2: 清理子进程继承的所有handler（避免重复输出）
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
        
        # Step 3: 将LogHub添加到root logger
        root_logger.addHandler(hub)
        root_logger.setLevel(logging.DEBUG)
        
        # Step 4: 创建子进程专用logger（带worker_id标识）
        logger_name = f"subprocess.{task_type}.{worker_id}"
        subprocess_logger = logging.getLogger(logger_name)
        subprocess_logger.propagate = True  # 让日志传播到root logger
        
        subprocess_logger.info(f"✅ 子进程 {worker_id} 日志系统已接入LogHub")
        return subprocess_logger
        
    except Exception as e:
        # 降级：如果LogHub配置失败，使用标准logger
        fallback_logger = logging.getLogger(__name__)
        fallback_logger.warning(
            f"⚠️ 子进程 {worker_id} LogHub配置失败，使用降级日志: {e}"
        )
        return fallback_logger
```

### 12.2 子进程日志命名规范

#### 12.2.1 命名格式标准

**格式定义**：`subprocess.{task_type}.{worker_id}`

**命名组成部分**：
1. **前缀**：`subprocess` - 标识这是子进程日志
2. **任务类型**：`{task_type}` - 标识任务的业务类型
3. **进程ID**：`{worker_id}` - 唯一标识具体的worker进程

#### 12.2.2 任务类型枚举

| task_type | 说明 | 应用场景 |
|-----------|------|----------|
| `worker` | K线下载进程 | 多进程+协程K线下载 |
| `quality_scan` | 质量扫描进程 | 多进程并发数据质量扫描 |
| `ipo` | IPO下载进程 | 批量IPO日期下载 |
| `finance` | 财务数据下载进程 | 批量财务数据下载 |
| `server_test` | 服务器测速进程 | 服务器池并发测速 |
| `tdx_read` | TDX本地读取进程 | 批量读取通达信本地文件 |

#### 12.2.3 命名示例

```python
# K线下载进程 Worker 0
logger_name = "subprocess.worker.0"

# K线下载进程 Worker 15
logger_name = "subprocess.worker.15"

# 质量扫描进程 Worker 2
logger_name = "subprocess.quality_scan.2"

# IPO下载进程 Worker 5
logger_name = "subprocess.ipo.5"

# 服务器测速进程 Worker 1
logger_name = "subprocess.server_test.1"
```

### 12.3 Handler清理机制

#### 12.3.1 清理原因详解

**问题背景**：
- Python的`multiprocessing`模块在创建子进程时会复制父进程的完整状态
- 父进程的所有logger和handler都会被继承到子进程
- 如果不清理，日志会同时被父进程和子进程的handler处理
- 导致日志重复输出、文件冲突、性能下降

**清理目标**：
1. 移除所有继承的FileHandler（避免文件写入冲突）
2. 移除所有继承的StreamHandler（避免终端重复输出）
3. 移除所有继承的LogHub handler（避免双重路由）

#### 12.3.2 清理实现详解

```python
# 获取root logger
root_logger = logging.getLogger()

# 遍历所有handler（使用切片复制，避免遍历时修改）
for handler in root_logger.handlers[:]:
    # 从root logger移除handler
    root_logger.removeHandler(handler)
    
    # 关闭handler，释放资源
    # - FileHandler: 关闭文件句柄
    # - StreamHandler: 刷新缓冲区
    # - SocketHandler: 关闭网络连接
    handler.close()
```

**关键点说明**：
1. **使用切片复制**：`handlers[:]` 创建列表副本，避免迭代时修改
2. **先移除后关闭**：确保handler不再处理新日志后再关闭
3. **必须close()**：释放文件句柄、网络连接等资源

#### 12.3.3 清理影响范围

**影响范围**：
- 仅影响当前子进程的logger配置
- 不影响父进程的logger配置
- 不影响其他子进程的logger配置

**清理后的状态**：
- root logger的handlers列表为空
- 所有旧handler资源已释放
- 准备添加新的LogHub handler

### 12.4 日志传播机制

#### 12.4.1 传播链路设计

```
子进程专用logger (subprocess.worker.0)
    ↓ propagate=True
root logger
    ↓ handlers=[LogHub]
LogHub (统一路由)
    ↓ 3层路由规则
    ├─ Layer 3: 模块规则 (subprocess.worker.*)
    ├─ Layer 2: 阶段规则 (downloading)
    └─ Layer 1: 全局规则 (兜底)
    ↓
    ├─ AI日志文件 (完整日志)
    ├─ 终端输出 (过滤后)
    └─ 系统日志文件
```

#### 12.4.2 propagate属性详解

**propagate=True（默认值，必须显式设置）**：
- 子进程logger产生的日志会传播到父logger
- 最终传播到root logger
- root logger的LogHub会处理所有传播的日志

**propagate=False（禁止传播，谨慎使用）**：
- 日志不会传播到父logger
- 必须为该logger添加独立的handler
- 通常不建议在子进程中使用

#### 12.4.3 日志级别设置规范

**root logger级别**：
```python
root_logger.setLevel(logging.DEBUG)
```
- 必须设置为DEBUG级别
- 确保所有级别的日志都能传递到LogHub
- LogHub通过路由规则控制实际输出

**子进程logger级别**：
```python
subprocess_logger = logging.getLogger(f"subprocess.{task_type}.{worker_id}")
# 不设置level，继承root logger的DEBUG级别
```
- 通常不单独设置level
- 继承root logger的DEBUG级别
- 通过LogHub路由规则控制输出

### 12.5 应用场景示例

#### 12.5.1 K线下载进程日志配置

```python
def _run_kline_download_worker(*args):
    """K线下载worker进程入口函数"""
    import warnings
    
    # 抑制ResourceWarning
    warnings.filterwarnings(
        "ignore", 
        category=ResourceWarning, 
        message=".*socket.*"
    )
    
    # 配置子进程日志
    logger = _configure_subprocess_logging(
        worker_id=args[0],  # 第一个参数是worker_id
        task_type="worker"
    )
    
    # 运行异步事件循环
    asyncio.run(_kline_download_worker_async(*args))
```

#### 12.5.2 质量扫描进程日志配置

```python
def _run_quality_scan_worker(*args):
    """质量扫描worker进程入口函数"""
    import warnings
    
    # 抑制ResourceWarning
    warnings.filterwarnings(
        "ignore", 
        category=ResourceWarning, 
        message=".*socket.*"
    )
    
    # 配置子进程日志
    logger = _configure_subprocess_logging(
        worker_id=args[0],
        task_type="quality_scan"
    )
    
    # 运行异步事件循环
    asyncio.run(_quality_scan_worker_async(*args))
```

#### 12.5.3 IPO下载进程日志配置

```python
def _run_ipo_download_worker(*args):
    """IPO下载worker进程入口函数"""
    # 配置子进程日志
    logger = _configure_subprocess_logging(
        worker_id=args[0],
        task_type="ipo"
    )
    
    # 运行异步事件循环
    asyncio.run(_ipo_download_worker_async(*args))
```

### 12.6 降级机制

#### 12.6.1 LogHub不可用时的降级

```python
try:
    from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub
    hub = get_logging_hub()
    # ... 正常配置流程
except Exception as e:
    # 降级：使用标准logger
    fallback_logger = logging.getLogger(__name__)
    fallback_logger.warning(
        f"⚠️ 子进程 {worker_id} LogHub配置失败，使用降级日志: {e}"
    )
    return fallback_logger
```

**降级行为**：
- 使用Python标准logging配置
- 日志输出到stderr
- 不支持AI日志文件
- 不支持3层路由规则

#### 12.6.2 降级日志记录要求

- 必须记录降级原因
- 使用WARNING级别
- 包含worker_id信息
- 包含异常详细信息

---

## 十三、背压控制与队列管理业务规则

> **架构设计参考**：背压控制架构请参考 [最佳实践文档 - 2.2 data_acquisition.py](./data_module_vnpy新架构最佳实践cursor版.md#22-data_acquisitionpy---数据获取模块)

### 13.1 微观架构设计

#### 13.1.1 队列监控器架构

**设计目标**：
- 统一管理所有队列的积压监控
- 分级告警，及时发现系统瓶颈
- 支持统计数据查询和复位
- 线程安全，支持并发访问

**核心类设计**：

```python
import threading
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
import time
import logging

@dataclass
class QueueSkipStats:
    """队列跳过统计"""
    queue_name: str
    worker_id: Optional[int]
    skip_count: int = 0
    last_warning: int = 0  # 上次告警时的skip_count值
    first_skip_time: Optional[float] = None
    last_skip_time: Optional[float] = None
    
    @property
    def stats_key(self) -> str:
        """生成统计key"""
        if self.worker_id is not None:
            return f"{self.queue_name}_{self.worker_id}"
        return self.queue_name
    
    @property
    def skip_duration(self) -> float:
        """跳过持续时间（秒）"""
        if self.first_skip_time is None or self.last_skip_time is None:
            return 0.0
        return self.last_skip_time - self.first_skip_time


class QueuePressureMonitor:
    """队列压力监控器
    
    统一管理所有队列的积压监控，分级告警，统计数据收集
    """
    
    # 告警阈值
    WARNING_THRESHOLD_1 = 3      # 前3次每次告警
    WARNING_THRESHOLD_10 = 10    # 第10次起每10次告警
    ERROR_THRESHOLD_100 = 100    # 第100次严重告警
    ERROR_THRESHOLD_500 = 500    # 第500次起每500次告警
    
    def __init__(self):
        self._stats: Dict[str, QueueSkipStats] = {}
        self._lock = threading.Lock()
        self._logger = logging.getLogger("backend.data_module.queue")
        self._alert_logger = logging.getLogger("backend.data_module.alert")
    
    def record_skip(
        self,
        queue_name: str,
        worker_id: Optional[int] = None,
        timeout: float = 1.0,
        error_type: str = "Full"
    ) -> int:
        """记录队列跳过事件
        
        Args:
            queue_name: 队列名称
            worker_id: Worker ID
            timeout: 超时时间
            error_type: 异常类型
            
        Returns:
            当前累计跳过次数
        """
        with self._lock:
            # 生成stats_key
            stats_key = self._make_stats_key(queue_name, worker_id)
            
            # 初始化或更新统计
            if stats_key not in self._stats:
                self._stats[stats_key] = QueueSkipStats(
                    queue_name=queue_name,
                    worker_id=worker_id,
                    skip_count=0,
                    last_warning=0,
                    first_skip_time=time.time()
                )
            
            stats = self._stats[stats_key]
            stats.skip_count += 1
            stats.last_skip_time = time.time()
            skip_count = stats.skip_count
            
            # 分级告警
            self._trigger_alert(stats, timeout, error_type)
            
            return skip_count
    
    def _trigger_alert(
        self,
        stats: QueueSkipStats,
        timeout: float,
        error_type: str
    ):
        """触发分级告警
        
        Args:
            stats: 统计数据
            timeout: 超时时间
            error_type: 异常类型
        """
        skip_count = stats.skip_count
        
        # 前3次：每次都记录WARNING
        if skip_count <= self.WARNING_THRESHOLD_1:
            self._logger.warning(
                f"⚠️ 队列入队失败（{error_type}）: "
                f"队列={stats.queue_name}, Worker={stats.worker_id}, "
                f"累计跳过={skip_count}次, 超时={timeout}s"
            )
            stats.last_warning = skip_count
        
        # 第10次起：每10次记录一次WARNING
        elif skip_count >= self.WARNING_THRESHOLD_10 and skip_count % 10 == 1:
            self._logger.warning(
                f"⚠️ 队列入队失败（{error_type}）: "
                f"队列={stats.queue_name}, Worker={stats.worker_id}, "
                f"累计跳过={skip_count}次, 超时={timeout}s"
            )
            stats.last_warning = skip_count
        
        # 第100次：记录ERROR级别严重告警
        if skip_count == self.ERROR_THRESHOLD_100:
            self._alert_logger.error(
                f"🔥 队列严重积压告警: "
                f"队列={stats.queue_name}, Worker={stats.worker_id}, "
                f"累计跳过={skip_count}次，消费者可能过慢！"
            )
        
        # 第500次起：每500次记录一次ERROR
        elif skip_count >= self.ERROR_THRESHOLD_500 and skip_count % 500 == 0:
            self._alert_logger.error(
                f"🔥 队列严重积压告警: "
                f"队列={stats.queue_name}, Worker={stats.worker_id}, "
                f"累计跳过={skip_count}次，消费者可能过慢！"
            )
    
    def _make_stats_key(self, queue_name: str, worker_id: Optional[int]) -> str:
        """生成统计key"""
        if worker_id is not None:
            return f"{queue_name}_{worker_id}"
        return queue_name
    
    def get_stats(self, queue_name: str, worker_id: Optional[int] = None) -> Optional[QueueSkipStats]:
        """获取指定队列的统计数据"""
        stats_key = self._make_stats_key(queue_name, worker_id)
        with self._lock:
            return self._stats.get(stats_key)
    
    def get_all_stats(self) -> Dict[str, QueueSkipStats]:
        """获取所有统计数据（用于监控）"""
        with self._lock:
            return dict(self._stats)
    
    def reset(self):
        """重置队列跳过统计"""
        with self._lock:
            self._stats.clear()
        self._logger.info("队列跳过统计已重置")
    
    def log_summary(self):
        """输出统计摘要（用于诊断）"""
        with self._lock:
            if not self._stats:
                self._logger.info("无队列跳过统计")
                return
            
            self._logger.info("===== 队列跳过统计 =====")
            for stats_key, stats in self._stats.items():
                self._logger.info(
                    f"  {stats_key}: {stats.skip_count}次跳过 "
                    f"(持续{stats.skip_duration:.1f}秒)"
                )
            self._logger.info("==========================")


# 全局实例
_queue_pressure_monitor = QueuePressureMonitor()


def get_queue_pressure_monitor() -> QueuePressureMonitor:
    """获取全局队列压力监控器"""
    return _queue_pressure_monitor


def safe_put_queue(
    q,
    item,
    timeout: float = 1.0,
    queue_name: str = "queue",
    worker_id: Optional[int] = None,
) -> bool:
    """安全入队，支持超时阻塞和跳过策略（背压控制）
    
    Args:
        q: 队列对象
        item: 要入队的数据
        timeout: 超时时间（秒）
        queue_name: 队列名称（用于日志）
        worker_id: Worker ID（用于统计）
    
    Returns:
        bool: True=入队成功, False=入队失败（队列满）
    """
    monitor = get_queue_pressure_monitor()
    
    try:
        # 尝试入队（阻塞等待，最多timeout秒）
        q.put(item, timeout=timeout)
        return True
        
    except Exception as e:
        # 队列满或其他异常
        error_type = type(e).__name__
        
        # 记录跳过事件（自动触发分级告警）
        skip_count = monitor.record_skip(
            queue_name=queue_name,
            worker_id=worker_id,
            timeout=timeout,
            error_type=error_type
        )
        
        return False
```

**架构优势**：

1. **统一监控**：
   - 全局统一管理所有队列统计
   - 支持多队列、多进程监控
   - 线程安全，支持并发访问

2. **分级告警**：
   - 前3次每次告警，及时发现问题
   - 第10次起每10次，减少日志噪音
   - 第100次严重告警，提示系统瓶颈

3. **数据收集**：
   - 记录跳过次数、时间、持续时间
   - 支持按队列、进程查询
   - 生成统计报告

4. **简化调用**：
   - `safe_put_queue`封装所有逻辑
   - 自动监控、自动告警
   - 上层调用简单

---

### 13.2 队列跳过统计机制

#### 13.1.1 数据结构定义

**全局统计字典**：
```python
_queue_skip_stats = {
    "{queue_name}_{worker_id}": {
        "skip_count": int,      # 累计跳过次数
        "last_warning": int,    # 上次告警的skip_count值
    }
}
```

**线程安全锁**：
```python
_queue_skip_lock = threading.Lock()
```

**示例数据**：
```python
{
    "result_queue_0": {
        "skip_count": 156,
        "last_warning": 150
    },
    "progress_queue_3": {
        "skip_count": 23,
        "last_warning": 20
    }
}
```

#### 13.1.2 分级告警规则

**前3次：每次都记录WARNING**
```python
if skip_count <= 3:
    logger.warning(
        f"⚠️ 队列入队失败（{error_type}）: "
        f"队列={queue_name}, Worker={worker_id}, "
        f"累计跳过={skip_count}次, 超时={timeout}s"
    )
```

**第10次起：每10次记录一次WARNING**
```python
if skip_count % 10 == 1:
    logger.warning(
        f"⚠️ 队列入队失败（{error_type}）: "
        f"队列={queue_name}, Worker={worker_id}, "
        f"累计跳过={skip_count}次, 超时={timeout}s"
    )
```

**第100次：记录ERROR级别严重告警**
```python
if skip_count == 100:
    logger_alert.error(
        f"🔥 队列严重积压告警: "
        f"队列={queue_name}, Worker={worker_id}, "
        f"累计跳过={skip_count}次，消费者可能过慢！"
    )
```

**第500次起：每500次记录一次ERROR**
```python
if skip_count % 500 == 0:
    logger_alert.error(
        f"🔥 队列严重积压告警: "
        f"队列={queue_name}, Worker={worker_id}, "
        f"累计跳过={skip_count}次，消费者可能过慢！"
    )
```

#### 13.1.3 统计复位机制

**复位时机**：
1. 下载任务完成时调用`_reset_queue_skip_stats()`
2. 质量扫描完成时复位统计
3. IPO下载完成时复位统计

**复位实现**：
```python
def _reset_queue_skip_stats():
    """重置队列跳过统计"""
    with _queue_skip_lock:
        _queue_skip_stats.clear()
```

**复位日志**：
```python
logger.info("队列跳过统计已重置")
```

#### 13.1.4 统计查询接口

```python
def _get_queue_skip_stats() -> Dict[str, Dict[str, int]]:
    """获取队列跳过统计（用于监控）
    
    Returns:
        统计字典的副本
    """
    with _queue_skip_lock:
        return dict(_queue_skip_stats)
```

**使用示例**：
```python
# 在下载完成后查询统计
stats = _get_queue_skip_stats()
for queue_key, queue_stats in stats.items():
    logger.info(
        f"队列 {queue_key} 跳过统计: {queue_stats['skip_count']}次"
    )
```

### 13.2 安全入队函数实现

#### 13.2.1 函数签名

```python
def _safe_put_queue(
    q,
    item,
    timeout: float = 1.0,
    queue_name: str = "queue",
    worker_id: Optional[int] = None,
) -> bool:
    """安全入队，支持超时阻塞和跳过策略（背压控制）
    
    Args:
        q: 队列对象
        item: 要入队的数据
        timeout: 超时时间（秒）
        queue_name: 队列名称（用于日志）
        worker_id: Worker ID（用于统计）
    
    Returns:
        bool: True=入队成功, False=入队失败（队列满）
    """
```

#### 13.2.2 设计原理

**1. 阻塞等待（有超时）**：
- 队列满时等待timeout秒
- 而非立即失败或无限等待
- 给消费者一定的处理时间

**2. 超时跳过**：
- 超时后记录警告并丢弃任务
- 避免生产者阻塞影响其他任务
- 通过统计监控队列积压情况

**3. 统计监控**：
- 记录跳过次数，触发告警
- 帮助发现系统瓶颈
- 支持动态调整策略

#### 13.2.3 完整实现

```python
def _safe_put_queue(
    q,
    item,
    timeout: float = 1.0,
    queue_name: str = "queue",
    worker_id: Optional[int] = None,
) -> bool:
    """安全入队，支持超时阻塞和跳过策略（背压控制）"""
    import logging
    
    logger = logging.getLogger("backend.data_module.download")
    logger_alert = logging.getLogger("backend.data_module.alert")
    
    try:
        # 尝试入队（阻塞等待，最多timeout秒）
        q.put(item, timeout=timeout)
        return True
        
    except Exception as e:
        # 队列满或其他异常
        error_type = type(e).__name__
        
        # 统计跳过次数（线程安全）
        stats_key = (
            f"{queue_name}_{worker_id}" 
            if worker_id is not None 
            else queue_name
        )
        
        with _queue_skip_lock:
            if stats_key not in _queue_skip_stats:
                _queue_skip_stats[stats_key] = {
                    "skip_count": 0, 
                    "last_warning": 0
                }
            
            _queue_skip_stats[stats_key]["skip_count"] += 1
            skip_count = _queue_skip_stats[stats_key]["skip_count"]
            
            # 分级告警
            if skip_count % 10 == 1 or skip_count <= 3:
                logger.warning(
                    f"⚠️ 队列入队失败（{error_type}）: "
                    f"队列={queue_name}, Worker={worker_id}, "
                    f"累计跳过={skip_count}次, 超时={timeout}s"
                )
                _queue_skip_stats[stats_key]["last_warning"] = skip_count
            
            # 严重告警
            if skip_count == 100 or skip_count % 500 == 0:
                logger_alert.error(
                    f"🔥 队列严重积压告警: "
                    f"队列={queue_name}, Worker={worker_id}, "
                    f"累计跳过={skip_count}次，消费者可能过慢！"
                )
        
        return False
```

### 13.3 应用场景

#### 13.3.1 下载结果队列背压控制

```python
# 在K线下载worker中应用
async def kline_download_worker(worker_id, task_queue, result_queue, ...):
    while True:
        # 获取任务
        symbol, interval = await get_task_from_queue(task_queue)
        
        # 下载数据
        data = await download_kline(symbol, interval)
        
        # 🆕 背压控制：使用_safe_put_queue代替原来的无限等待
        success = await asyncio.to_thread(
            _safe_put_queue,
            result_queue,
            (symbol, interval, data),
            timeout=1.0,
            queue_name="result_queue",
            worker_id=worker_id,
        )
        
        if success:
            await asyncio.to_thread(progress_queue.put, (symbol, interval, "success"))
        else:
            # 队列满，跳过该任务
            await asyncio.to_thread(progress_queue.put, (symbol, interval, "skipped"))
```

#### 13.3.2 进度队列背压控制

```python
# 在质量扫描worker中应用
async def quality_scan_worker(worker_id, task_queue, result_queue, progress_queue, ...):
    while True:
        # 获取任务
        symbol = await get_task_from_queue(task_queue)
        
        # 扫描质量
        quality_dict = await scan_symbol_quality(symbol)
        
        # 上报进度（带背压控制）
        success = await asyncio.to_thread(
            _safe_put_queue,
            progress_queue,
            (symbol, "success"),
            timeout=0.5,  # 进度队列超时更短
            queue_name="progress_queue",
            worker_id=worker_id,
        )
        
        if not success:
            logger.debug(f"进度上报失败，跳过: {symbol}")
```

### 13.4 监控与诊断

#### 13.4.1 实时监控

```python
# 在主进程中定期查询统计
def monitor_queue_pressure():
    """监控队列压力"""
    stats = _get_queue_skip_stats()
    
    for queue_key, queue_stats in stats.items():
        skip_count = queue_stats["skip_count"]
        
        if skip_count > 100:
            logger_alert.warning(
                f"⚠️ 队列 {queue_key} 积压严重: {skip_count}次跳过"
            )
        elif skip_count > 10:
            logger.info(
                f"ℹ️ 队列 {queue_key} 有轻微积压: {skip_count}次跳过"
            )
```

#### 13.4.2 任务完成后诊断

```python
# 在下载任务完成后输出诊断信息
def log_queue_statistics():
    """输出队列统计信息（用于诊断）"""
    stats = _get_queue_skip_stats()
    
    if stats:
        logger.info("===== 队列跳过统计 =====")
        for queue_key, queue_stats in stats.items():
            logger.info(
                f"  {queue_key}: {queue_stats['skip_count']}次跳过"
            )
        logger.info("==========================")
    
    # 重置统计
    _reset_queue_skip_stats()
```

---

## 文档总结

本文档专注于data_module_vnpy新架构的业务流程规则和实现逻辑，包括：

### 核心业务规则
1. **品种管理规则**：分类标准、过滤规则、缓存机制
2. **数据下载规则**：两段式下载策略、并发控制、任务分配
3. **数据验证规则**：格式验证、逻辑验证、完整性检查

### 实现算法
- 智能起点计算算法
- 日期范围异常处理
- 停牌日期识别算法
- IPv6池降级机制

### 业务流程
- 品种加载完整流程
- 下载任务管理流程  
- 数据验证执行流程

> **技术架构参考**：详细的组件设计、异步操作、错误处理等技术架构请参考 [最佳实践文档](./data_module_vnpy新架构最佳实践cursor版.md)
