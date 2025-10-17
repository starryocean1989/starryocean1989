# -*- coding: utf-8 -*-
"""
异步复权调整模块

提供股票数据复权调整功能，完全异步化实现，
基于mootdx复权算法，使用现有的除权除息信息接口。

核心算法：
- 前复权：adj = (preclose.shift(-1) / close).fillna(1)[::-1].cumprod()
- 后复权：adj = (preclose.shift(-1) / close).fillna(1).cumprod()
- 新浪因子：可选从新浪财经获取在线复权因子

作者：[项目名称]
版本：2.0
"""

import asyncio
from typing import List, Optional, Union

import pandas as pd

from .async_hq import AsyncTdxHq_API
from .logger import logger


async def apply_adjustment(
    df: pd.DataFrame,
    symbol: str,
    adjust_type: str = 'qfq',  # 'qfq'=前复权, 'hfq'=后复权, None=不复权
    market: Optional[int] = None,
    client: Optional[AsyncTdxHq_API] = None
) -> pd.DataFrame:
    """
    完整异步复权调整（基于mootdx算法）

    核心算法（来自mootdx.tools.reversion）：
    1. 计算前日收盘价：preclose = (close*10 - fenhong + peigu*peigujia) / (10 + peigu + songzhuangu)
    2. 计算复权因子：
       - 前复权：adj = (preclose.shift(-1) / close).fillna(1)[::-1].cumprod()
       - 后复权：adj = (preclose.shift(-1) / close).fillna(1).cumprod()
    3. 应用复权：
       - OHLC价格：price * adj（前复权）或 price / adj（后复权）
       - 成交量：volume / adj（均需调整）

    :param df: 待复权的数据DataFrame（必须包含open/high/low/close/volume等字段）
    :param symbol: 股票代码
    :param adjust_type: 复权类型（'qfq'/'hfq'/'before'/'after'/None）
    :param market: 市场代码（可选，自动推断）
    :param client: 异步客户端（可选，提供则使用该连接获取除权数据）
    :return: 复权后的DataFrame
    """
    if df is None or df.empty:
        return df

    # 标准化复权类型
    if adjust_type in ['before']:
        adjust_type = 'qfq'
    elif adjust_type in ['after']:
        adjust_type = 'hfq'

    if adjust_type not in ['qfq', 'hfq', None]:
        raise ValueError(f"不支持的复权类型: {adjust_type}")

    if adjust_type is None:
        return df  # 不复权直接返回

    # 自动推断市场（如果未提供）
    if market is None:
        # 简单市场推断
        if symbol.startswith(('0', '3')):
            market = 0  # 深圳
        else:
            market = 1  # 上海

    try:
        # 获取除权除息信息
        xdxr_data = await _get_xdxr_info_async(symbol, market, client)

        if not xdxr_data or xdxr_data.empty:
            logger.warning(f"股票{symbol}无除权除息信息，返回原始数据")
            return df

        # 应用完整复权算法（基于mootdx实现）
        adjusted_df = _apply_full_adjustment(df.copy(), xdxr_data, adjust_type)

        logger.info(f"股票{symbol}复权调整完成，类型: {adjust_type}")
        return adjusted_df

    except Exception as e:
        logger.error(f"复权调整失败: {e}")
        import traceback
        traceback.print_exc()
        return df  # 失败时返回原数据


async def _get_xdxr_info_async(
    symbol: str,
    market: int,
    client: Optional[AsyncTdxHq_API] = None
) -> pd.DataFrame:
    """
    异步获取除权除息信息

    :param symbol: 股票代码
    :param market: 市场代码
    :param client: 客户端（如果提供则使用，否则临时创建）
    :return: DataFrame包含除权除息信息
    """
    need_close = False

    try:
        # 如果未提供客户端，临时创建一个
        if client is None:
            from .constants import HQ_HOSTS
            # 使用第一个可用服务器临时获取数据
            for server in HQ_HOSTS[:5]:  # 尝试前5个
                temp_client = await AsyncTdxHq_API.factory(
                    server=(server[1], server[2]),
                    timeout=3.0,
                    raise_exception=False
                )
                if temp_client:
                    client = temp_client
                    need_close = True
                    break

        if not client:
            logger.warning("无法连接TDX服务器获取除权信息")
            return pd.DataFrame()

        # 获取除权除息数据
        xdxr_list = await client.get_xdxr_info(market, symbol)

        if not xdxr_list:
            return pd.DataFrame()

        # 转换为DataFrame
        xdxr_df = pd.DataFrame(xdxr_list)

        # 创建date列
        xdxr_df['date'] = pd.to_datetime(xdxr_df[['year', 'month', 'day']])
        xdxr_df = xdxr_df.set_index('date')

        return xdxr_df

    finally:
        # 如果是临时创建的客户端，需要关闭
        if need_close and client:
            await client.close()


def _apply_full_adjustment(
    bfq_data: pd.DataFrame,
    xdxr_data: pd.DataFrame,
    adjust_type: str
) -> pd.DataFrame:
    """
    完整复权调整实现（基于mootdx.tools.reversion算法）

    :param bfq_data: 不复权数据（必须包含open/high/low/close/volume字段）
    :param xdxr_data: 除权除息数据（必须包含fenhong/peigu/peigujia/songzhuangu字段）
    :param adjust_type: 复权类型（'qfq'或'hfq'）
    :return: 复权后的DataFrame
    """
    if xdxr_data.empty:
        return bfq_data

    # 筛选除权除息数据（category==1表示除权除息）
    info = xdxr_data.query('category==1') if 'category' in xdxr_data.columns else xdxr_data

    if len(info) == 0:
        return bfq_data

    # 添加交易标记
    data = bfq_data.assign(if_trade=1)

    # 合并除权数据到行情数据中
    try:
        data = pd.concat([data, info.loc[data.index[0]: data.index[-1], ['category']]], axis=1)
        data['if_trade'].fillna(value=0, inplace=True)
        data = data.fillna(method='ffill')
        data = pd.concat(
            [data, info.loc[data.index[0]: data.index[-1], ['fenhong', 'peigu', 'peigujia', 'songzhuangu']]],
            axis=1
        )
    except Exception:
        data = pd.concat([data, info.loc[:, ['category', 'fenhong', 'peigu', 'peigujia', 'songzhuangu']]], axis=1)

    # 数据补全
    data = data.fillna(0)

    # 核心算法：计算前日收盘价（mootdx核心公式）
    data['preclose'] = (
        data['close'].shift(1) * 10 - data['fenhong'] + data['peigu'] * data['peigujia']
    ) / (10 + data['peigu'] + data['songzhuangu'])

    # 计算复权因子
    if adjust_type.lower() in ['qfq', '01', 'before']:
        # 前复权（mootdx核心公式）
        data['adj'] = (data['preclose'].shift(-1) / data['close']).fillna(1)[::-1].cumprod()

        # 价格复权（前复权）
        for col in ['open', 'high', 'low', 'close', 'preclose']:
            if col in data.columns:
                data[col] = data[col] * data['adj']

    elif adjust_type.lower() in ['hfq', '02', 'after']:
        # 后复权（mootdx核心公式）
        data['adj'] = (data['preclose'].shift(-1) / data['close']).fillna(1).cumprod()

        # 价格复权（后复权）
        for col in ['open', 'high', 'low', 'close', 'preclose']:
            if col in data.columns:
                data[col] = data[col] / data['adj']

    # 成交量复权（统一调整）
    if 'volume' in data.columns and 'adj' in data.columns:
        data['volume'] = data['volume'] / data['adj']
    elif 'vol' in data.columns and 'adj' in data.columns:
        data['vol'] = data['vol'] / data['adj']

    # 清理：只保留交易日数据，且开盘价不为0
    data = data.query('if_trade==1 and open != 0')

    # 删除辅助列
    data = data.drop(
        ['fenhong', 'peigu', 'peigujia', 'songzhuangu', 'if_trade', 'category', 'adj', 'preclose'],
        axis=1,
        errors='ignore'
    )

    return data


# ==================== 便捷函数 ====================

def is_adjustment_needed(symbol: str) -> bool:
    """
    判断股票是否需要复权调整

    :param symbol: 股票代码
    :return: 是否需要复权
    """
    # 简单的判断逻辑
    # 北交所股票通常不需要复权
    if symbol.startswith(('4', '8')):
        return False

    # 其他股票通常需要复权
    return True


async def get_sina_fq_factor(symbol: str, method: str = 'qfq'):
    """
    从新浪财经获取复权因子（异步）

    数据来源：新浪财经在线复权因子API
    优势：实时更新，准确性高

    :param symbol: 股票代码
    :param method: 复权方法（'qfq'=前复权, 'hfq'=后复权）
    :return: DataFrame包含复权因子
    """
    try:
        # 需要httpx异步HTTP客户端
        import httpx
    except ImportError:
        logger.warning("未安装httpx，无法使用新浪财经复权因子")
        return pd.DataFrame()

    # 移除前缀
    symbol = symbol.replace('sh', '').replace('sz', '').replace('bj', '')

    # 自动添加市场前缀（新浪需要）
    if symbol.startswith(('6', '5')):
        symbol = f'sh{symbol}'
    else:
        symbol = f'sz{symbol}'

    # 新浪财经复权因子API
    url_map = {
        'hfq': f'https://finance.sina.com.cn/realstock/company/{symbol}/hfq.js',
        'qfq': f'https://finance.sina.com.cn/realstock/company/{symbol}/qfq.js'
    }

    url = url_map.get(method, url_map['qfq'])

    try:
        async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
            response = await client.get(url)

            if response.status_code != 200:
                logger.warning(f"获取新浪复权因子失败: HTTP {response.status_code}")
                return pd.DataFrame()

            # 解析新浪返回的JS数据
            import json
            data_str = response.text.split('=')[1].split('\n')[0]
            data_json = json.loads(data_str)

            # 转换为DataFrame
            fq_df = pd.DataFrame(data_json['data'])

            if fq_df.empty:
                return pd.DataFrame()

            fq_df.columns = ['date', f'{method}_factor']
            fq_df['date'] = pd.to_datetime(fq_df['date'])
            fq_df = fq_df.set_index('date')

            logger.info(f"成功获取{symbol}的{method}复权因子，共{len(fq_df)}条")
            return fq_df

    except Exception as e:
        logger.warning(f"获取新浪复权因子异常: {e}")
        return pd.DataFrame()


# ==================== 使用示例 ====================

async def example_usage():
    """使用示例"""

    # 示例数据（需要包含date和OHLC字段）
    data = pd.DataFrame([
        {'date': '2023-01-01', 'open': 10.0, 'high': 10.5, 'low': 9.8, 'close': 10.2, 'volume': 1000},
        {'date': '2023-01-02', 'open': 10.2, 'high': 10.8, 'low': 10.0, 'close': 10.5, 'volume': 1100},
        {'date': '2023-01-03', 'open': 10.5, 'high': 11.0, 'low': 10.3, 'close': 10.8, 'volume': 1200},
    ])

    # 设置日期索引
    data['date'] = pd.to_datetime(data['date'])
    data = data.set_index('date')

    # 前复权调整
    try:
        adjusted_df = await apply_adjustment(data, '600000', adjust_type='qfq')
        print("前复权调整完成")
        print(adjusted_df.head())
    except Exception as e:
        print(f"前复权失败: {e}")

    # 后复权调整
    try:
        adjusted_df = await apply_adjustment(data, '600000', adjust_type='hfq')
        print("后复权调整完成")
        print(adjusted_df.head())
    except Exception as e:
        print(f"后复权失败: {e}")

    # 获取新浪复权因子（可选）
    try:
        sina_factor = await get_sina_fq_factor('600000', 'qfq')
        print(f"新浪复权因子: {len(sina_factor)}条")
    except Exception as e:
        print(f"获取新浪因子失败: {e}")


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
