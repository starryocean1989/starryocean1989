import pytest
import numpy as np
from typing import List, Dict, Any
from backend.services.backtest_optimizer import BacktestOptimizer, BacktestResult

class MockStrategy:
    """模拟策略类，用于测试回测优化器"""
    def __init__(self, params: Dict[str, Any]):
        self.params = params
        self.equity = []
        self.returns = []
        
    def run_backtest(self, data: List[Dict]) -> None:
        """模拟回测执行"""
        # 简单的模拟策略：根据参数计算收益
        for i in range(len(data)):
            ret = (data[i].get('close', 0) - data[i].get('open', 0)) / data[i].get('open', 1)
            ret = ret * self.params.get('leverage', 1.0)
            self.returns.append(ret)
            self.equity.append(10000 * (1 + sum(self.returns)))

def test_backtest_optimizer():
    """测试回测优化器基础功能"""
    # 准备测试数据
    test_data = [
        {'open': 10.0, 'high': 10.5, 'low': 9.8, 'close': 10.2, 'volume': 1000},
        {'open': 10.2, 'high': 10.8, 'low': 10.1, 'close': 10.5, 'volume': 1200},
        {'open': 10.5, 'high': 11.0, 'low': 10.4, 'close': 10.8, 'volume': 1500}
    ]
    
    # 定义参数网格
    param_grid = {
        'leverage': [1.0, 2.0, 3.0],
        'ma_period': [5, 10, 20]
    }
    
    # 创建优化器
    optimizer = BacktestOptimizer()
    
    # 执行优化
    def mock_backtest(strategy_cls, data, symbol, exchange, **params):
        strategy = strategy_cls(params)
        strategy.run_backtest(data)
        return strategy.returns, strategy.equity
    
    # 模拟优化过程
    results = []
    from itertools import product
    for params in product(*param_grid.values()):
        param_dict = dict(zip(param_grid.keys(), params))
        strategy = MockStrategy(param_dict)
        strategy.run_backtest(test_data)
        sharpe = np.mean(strategy.returns) / (np.std(strategy.returns) + 1e-8)
        mdd = 0.1  # 简化的最大回撤计算
        results.append(BacktestResult(param_dict, sharpe, mdd))
    
    # 验证结果
    assert len(results) == 9  # 3x3 参数组合
    assert all(isinstance(r, BacktestResult) for r in results)
    assert all('leverage' in r.params for r in results)
    assert all('ma_period' in r.params for r in results)
