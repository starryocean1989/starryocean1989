#ifndef FINANCE_METRICS_H
#define FINANCE_METRICS_H

#include <Python.h>

// 结构体：日频聚合结果
typedef struct {
    double* dates;           // 日期数组（YYYYMMDD格式转换为double）
    double* daily_returns;   // 每日收益
    double* cumulative_equity; // 累计净值曲线
    size_t count;            // 数据点数量
} DailyAggregation;

// 结构体：绩效指标
typedef struct {
    double total_return;     // 总收益率
    double annualized_return; // 年化收益率
    double volatility;       // 波动率
    double sharpe_ratio;     // 夏普比率
    double max_drawdown;     // 最大回撤
    int drawdown_days;       // 最大回撤持续天数
    double calmar_ratio;     // 卡玛比率
} PerformanceMetrics;

// 结构体：周期分组结果
typedef struct {
    char** period_labels;    // 周期标签（如"2024-W01", "2024-01"等）
    double* period_returns;  // 每个周期的收益
    size_t count;            // 周期数量
} PeriodBuckets;

// 函数声明

// 按日期聚合盈亏并生成累计曲线
DailyAggregation* aggregate_daily_pnl(int* dates, double* pnl, size_t count);

// 计算绩效指标
PerformanceMetrics* compute_return_metrics(double* pnl_series, double* equity_series, size_t count, int trading_days_per_year);

// 按周期分组
PeriodBuckets* bucketize_period(double* equity_series, int* dates, size_t count, const char* period_mode);

// 清理函数
void free_daily_aggregation(DailyAggregation* agg);
void free_performance_metrics(PerformanceMetrics* metrics);
void free_period_buckets(PeriodBuckets* buckets);

#endif // FINANCE_METRICS_H
