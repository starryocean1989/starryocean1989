# -*- coding: utf-8 -*-
import pandas as pd

df = pd.read_parquet("data/kline/600000/1d/data.parquet")
print("品种 600000 数据:")
print(f"记录数: {len(df)}")
print(f"列名: {df.columns.tolist()}")
print(f'时间范围: {df["datetime"].min()} 到 {df["datetime"].max()}')
print(f"\n前5条记录:")
print(df.head())
