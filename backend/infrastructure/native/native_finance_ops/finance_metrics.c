// -*- coding: utf-8 -*-
/*
 * finance_metrics.c - 组合分析核心算子C实现
 * 
 * 功能：
 * 1. 日频盈亏聚合与累计曲线生成
 * 2. 绩效指标计算（收益率、波动率、夏普、回撤）
 * 3. 周期分组（周/月/年）
 */

#include "finance_metrics.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdio.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// 比较函数用于qsort（按日期升序）
static int compare_dates(const void* a, const void* b) {
    int date_a = *((int*)a);
    int date_b = *((int*)b);
    return date_a - date_b;
}

// 辅助结构：日期-盈亏对
typedef struct {
    int date;
    double pnl;
} DatePnLPair;

static int compare_date_pnl_pairs(const void* a, const void* b) {
    DatePnLPair* pair_a = (DatePnLPair*)a;
    DatePnLPair* pair_b = (DatePnLPair*)b;
    return pair_a->date - pair_b->date;
}

// 按日期聚合盈亏并生成累计曲线
DailyAggregation* aggregate_daily_pnl(int* dates, double* pnl, size_t count) {
    if (!dates || !pnl || count == 0) {
        return NULL;
    }

    // 创建日期-盈亏对数组并排序
    DatePnLPair* pairs = (DatePnLPair*)malloc(sizeof(DatePnLPair) * count);
    if (!pairs) return NULL;

    for (size_t i = 0; i < count; i++) {
        pairs[i].date = dates[i];
        pairs[i].pnl = pnl[i];
    }

    qsort(pairs, count, sizeof(DatePnLPair), compare_date_pnl_pairs);

    // 聚合相同日期的盈亏
    DailyAggregation* result = (DailyAggregation*)malloc(sizeof(DailyAggregation));
    if (!result) {
        free(pairs);
        return NULL;
    }

    // 预分配足够空间（最坏情况：每天都不同）
    result->dates = (double*)malloc(sizeof(double) * count);
    result->daily_returns = (double*)malloc(sizeof(double) * count);
    result->cumulative_equity = (double*)malloc(sizeof(double) * count);
    
    if (!result->dates || !result->daily_returns || !result->cumulative_equity) {
        free(pairs);
        free(result->dates);
        free(result->daily_returns);
        free(result->cumulative_equity);
        free(result);
        return NULL;
    }

    // 聚合逻辑
    size_t unique_count = 0;
    int current_date = pairs[0].date;
    double current_pnl = 0.0;
    double cumulative = 1.0; // 初始净值为1.0

    for (size_t i = 0; i < count; i++) {
        if (pairs[i].date == current_date) {
            current_pnl += pairs[i].pnl;
        } else {
            // 保存上一个日期的数据
            result->dates[unique_count] = (double)current_date;
            result->daily_returns[unique_count] = current_pnl;
            cumulative += current_pnl;
            result->cumulative_equity[unique_count] = cumulative;
            unique_count++;

            // 开始新日期
            current_date = pairs[i].date;
            current_pnl = pairs[i].pnl;
        }
    }

    // 保存最后一个日期的数据
    result->dates[unique_count] = (double)current_date;
    result->daily_returns[unique_count] = current_pnl;
    cumulative += current_pnl;
    result->cumulative_equity[unique_count] = cumulative;
    unique_count++;

    result->count = unique_count;

    free(pairs);
    return result;
}

// 计算绩效指标
PerformanceMetrics* compute_return_metrics(double* pnl_series, double* equity_series, 
                                          size_t count, int trading_days_per_year) {
    if (!pnl_series || !equity_series || count < 2) {
        return NULL;
    }

    PerformanceMetrics* metrics = (PerformanceMetrics*)malloc(sizeof(PerformanceMetrics));
    if (!metrics) return NULL;

    // 初始化
    memset(metrics, 0, sizeof(PerformanceMetrics));

    // 1. 总收益率
    double initial_equity = equity_series[0];
    double final_equity = equity_series[count - 1];
    metrics->total_return = (final_equity - initial_equity) / initial_equity;

    // 2. 年化收益率
    double years = (double)count / trading_days_per_year;
    if (years > 0 && final_equity > 0 && initial_equity > 0) {
        metrics->annualized_return = pow(final_equity / initial_equity, 1.0 / years) - 1.0;
    }

    // 3. 波动率（日收益率标准差）
    double mean_return = 0.0;
    for (size_t i = 0; i < count; i++) {
        mean_return += pnl_series[i];
    }
    mean_return /= count;

    double variance = 0.0;
    for (size_t i = 0; i < count; i++) {
        double diff = pnl_series[i] - mean_return;
        variance += diff * diff;
    }
    variance /= count;
    double daily_volatility = sqrt(variance);
    metrics->volatility = daily_volatility * sqrt((double)trading_days_per_year); // 年化波动率

    // 4. 夏普比率（假设无风险利率为0）
    if (metrics->volatility > 0) {
        metrics->sharpe_ratio = metrics->annualized_return / metrics->volatility;
    }

    // 5. 最大回撤与持续天数
    double peak = equity_series[0];
    double max_dd = 0.0;
    int dd_start = 0;
    int dd_end = 0;
    int current_dd_start = 0;

    for (size_t i = 1; i < count; i++) {
        if (equity_series[i] > peak) {
            peak = equity_series[i];
            current_dd_start = i;
        } else {
            double drawdown = (peak - equity_series[i]) / peak;
            if (drawdown > max_dd) {
                max_dd = drawdown;
                dd_start = current_dd_start;
                dd_end = i;
            }
        }
    }

    metrics->max_drawdown = max_dd;
    metrics->drawdown_days = dd_end - dd_start;

    // 6. 卡玛比率
    if (metrics->max_drawdown > 0) {
        metrics->calmar_ratio = metrics->annualized_return / metrics->max_drawdown;
    }

    return metrics;
}

// 按周期分组（简化实现：仅支持"weekly", "monthly", "yearly"）
PeriodBuckets* bucketize_period(double* equity_series, int* dates, size_t count, const char* period_mode) {
    if (!equity_series || !dates || count == 0 || !period_mode) {
        return NULL;
    }

    PeriodBuckets* buckets = (PeriodBuckets*)malloc(sizeof(PeriodBuckets));
    if (!buckets) return NULL;

    // 预分配空间（最坏情况估算）
    size_t max_periods = count; // 简化：最多等于数据点数
    buckets->period_labels = (char**)malloc(sizeof(char*) * max_periods);
    buckets->period_returns = (double*)malloc(sizeof(double) * max_periods);
    
    if (!buckets->period_labels || !buckets->period_returns) {
        free(buckets->period_labels);
        free(buckets->period_returns);
        free(buckets);
        return NULL;
    }

    // 简化实现：按月分组（YYYYMM）
    size_t period_count = 0;
    int current_period = dates[0] / 100; // YYYYMM
    double period_start_equity = equity_series[0];
    
    for (size_t i = 1; i < count; i++) {
        int date_period = dates[i] / 100;
        
        if (date_period != current_period) {
            // 保存上一周期
            char* label = (char*)malloc(16);
            snprintf(label, 16, "%d", current_period);
            buckets->period_labels[period_count] = label;
            buckets->period_returns[period_count] = 
                (equity_series[i-1] - period_start_equity) / period_start_equity;
            period_count++;

            // 开始新周期
            current_period = date_period;
            period_start_equity = equity_series[i];
        }
    }

    // 保存最后一个周期
    char* label = (char*)malloc(16);
    snprintf(label, 16, "%d", current_period);
    buckets->period_labels[period_count] = label;
    buckets->period_returns[period_count] = 
        (equity_series[count-1] - period_start_equity) / period_start_equity;
    period_count++;

    buckets->count = period_count;

    return buckets;
}

// 清理函数
void free_daily_aggregation(DailyAggregation* agg) {
    if (agg) {
        free(agg->dates);
        free(agg->daily_returns);
        free(agg->cumulative_equity);
        free(agg);
    }
}

void free_performance_metrics(PerformanceMetrics* metrics) {
    if (metrics) {
        free(metrics);
    }
}

void free_period_buckets(PeriodBuckets* buckets) {
    if (buckets) {
        if (buckets->period_labels) {
            for (size_t i = 0; i < buckets->count; i++) {
                free(buckets->period_labels[i]);
            }
            free(buckets->period_labels);
        }
        free(buckets->period_returns);
        free(buckets);
    }
}
