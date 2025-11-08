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
#include <ctype.h>

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

typedef struct {
    int year;
    int month;
    int week;
} PeriodKey;

typedef enum {
    PERIOD_MODE_MONTHLY = 0,
    PERIOD_MODE_WEEKLY = 1,
    PERIOD_MODE_YEARLY = 2
} PeriodMode;

static int is_leap_year(int year) {
    return (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);
}

static int day_of_year(int year, int month, int day) {
    static const int month_lengths[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    int doy = 0;
    for (int i = 1; i < month; i++) {
        doy += month_lengths[i - 1];
        if (i == 2 && is_leap_year(year)) {
            doy += 1;
        }
    }
    doy += day;
    return doy;
}

static int iso_day_of_week(int year, int month, int day) {
    int y = year;
    int m = month;
    if (m < 3) {
        m += 12;
        y -= 1;
    }
    int k = y % 100;
    int j = y / 100;
    int h = (day + (13 * (m + 1)) / 5 + k + k / 4 + j / 4 + 5 * j) % 7;
    int d = ((h + 5) % 7) + 1; // Monday=1 ... Sunday=7
    return d;
}

static int iso_weeks_in_year(int year) {
    int jan1_dow = iso_day_of_week(year, 1, 1);
    int dec31_dow = iso_day_of_week(year, 12, 31);
    if (jan1_dow == 4 || dec31_dow == 4) {
        return 53;
    }
    if (jan1_dow == 3 && is_leap_year(year)) {
        return 53;
    }
    if (dec31_dow == 5 && is_leap_year(year)) {
        return 53;
    }
    return 52;
}

static int iso_week_number(int year, int month, int day, int* iso_year) {
    int dow = iso_day_of_week(year, month, day);
    int doy = day_of_year(year, month, day);
    int week = (doy - dow + 10) / 7;

    if (week < 1) {
        *iso_year = year - 1;
        return iso_weeks_in_year(*iso_year);
    }
    int weeks = iso_weeks_in_year(year);
    if (week > weeks) {
        *iso_year = year + 1;
        return 1;
    }
    *iso_year = year;
    return week;
}

static void normalize_mode(const char* period_mode, char* normalized) {
    size_t len = strlen(period_mode);
    for (size_t i = 0; i < len && i < 15; i++) {
        normalized[i] = (char)tolower((unsigned char)period_mode[i]);
    }
    normalized[len > 15 ? 15 : len] = '\0';
}

static PeriodMode resolve_period_mode(const char* normalized_mode) {
    if (strcmp(normalized_mode, "weekly") == 0) {
        return PERIOD_MODE_WEEKLY;
    }
    if (strcmp(normalized_mode, "yearly") == 0) {
        return PERIOD_MODE_YEARLY;
    }
    return PERIOD_MODE_MONTHLY;
}

static void compute_period_key(int date, PeriodMode mode, PeriodKey* key, int* label_year, int* label_month, int* label_week) {
    int year = date / 10000;
    int month = (date / 100) % 100;
    int day = date % 100;

    key->year = year;
    key->month = month;
    key->week = 0;

    if (mode == PERIOD_MODE_WEEKLY) {
        int iso_year = year;
        int iso_week = iso_week_number(year, month, day, &iso_year);
        key->year = iso_year;
        key->week = iso_week;
        key->month = 0;
        if (label_year) *label_year = iso_year;
        if (label_week) *label_week = iso_week;
    } else if (mode == PERIOD_MODE_YEARLY) {
        key->month = 0;
        if (label_year) *label_year = year;
    } else {
        if (label_year) *label_year = year;
        if (label_month) *label_month = month;
    }
}

static int period_keys_equal(const PeriodKey* a, const PeriodKey* b) {
    return a->year == b->year && a->month == b->month && a->week == b->week;
}

static char* build_period_label(PeriodMode mode, int year, int month, int week) {
    char* label = (char*)malloc(24);
    if (!label) {
        return NULL;
    }
    if (mode == PERIOD_MODE_WEEKLY) {
        snprintf(label, 24, "%04d-W%02d", year, week);
    } else if (mode == PERIOD_MODE_YEARLY) {
        snprintf(label, 24, "%04d", year);
    } else {
        snprintf(label, 24, "%04d-%02d", year, month);
    }
    return label;
}

static double compute_period_return(double start_equity, double end_equity) {
    if (start_equity == 0.0) {
        if (end_equity == 0.0) {
            return 0.0;
        }
        return end_equity > 0.0 ? INFINITY : -INFINITY;
    }
    return (end_equity - start_equity) / start_equity;
}

// 按周期分组（支持"weekly", "monthly", "yearly"）
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

    char normalized_mode[16] = {0};
    normalize_mode(period_mode, normalized_mode);
    if (normalized_mode[0] == '\0') {
        strncpy(normalized_mode, "monthly", sizeof(normalized_mode) - 1);
    }

    PeriodMode mode = resolve_period_mode(normalized_mode);
    PeriodKey current_key = {0};
    int label_year = 0, label_month = 0, label_week = 0;
    compute_period_key(dates[0], mode, &current_key, &label_year, &label_month, &label_week);

    double period_start_equity = equity_series[0];
    double last_equity = equity_series[0];
    size_t period_count = 0;

    for (size_t i = 1; i < count; i++) {
        PeriodKey next_key = {0};
        int next_year = 0, next_month = 0, next_week = 0;
        compute_period_key(dates[i], mode, &next_key, &next_year, &next_month, &next_week);

        if (!period_keys_equal(&next_key, &current_key)) {
            char* label = build_period_label(mode, label_year, label_month, label_week);
            if (!label) {
                for (size_t j = 0; j < period_count; j++) {
                    free(buckets->period_labels[j]);
                }
                free(buckets->period_labels);
                free(buckets->period_returns);
                free(buckets);
                return NULL;
            }
            buckets->period_labels[period_count] = label;
            buckets->period_returns[period_count] =
                compute_period_return(period_start_equity, last_equity);
            period_count++;

            current_key = next_key;
            label_year = next_year;
            label_month = next_month;
            label_week = next_week;
            period_start_equity = equity_series[i];
        }
        last_equity = equity_series[i];
    }

    char* label = build_period_label(mode, label_year, label_month, label_week);
    if (!label) {
        for (size_t j = 0; j < period_count; j++) {
            free(buckets->period_labels[j]);
        }
        free(buckets->period_labels);
        free(buckets->period_returns);
        free(buckets);
        return NULL;
    }
    buckets->period_labels[period_count] = label;
    buckets->period_returns[period_count] =
        compute_period_return(period_start_equity, last_equity);
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
