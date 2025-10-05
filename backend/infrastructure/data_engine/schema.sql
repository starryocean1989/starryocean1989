-- 星辰金融终端 v4.23 - 数据持久化架构
-- 数据库：SQLite
-- 版本：v1.0
-- 更新日期：2025-09-11

-- 启用外键约束
PRAGMA foreign_keys = ON;

-- =============================================================================
-- 基础表
-- =============================================================================

-- 证券信息表
CREATE TABLE IF NOT EXISTS securities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(20) NOT NULL,
    exchange VARCHAR(20),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 市场数据表
CREATE TABLE IF NOT EXISTS market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    security_id INTEGER NOT NULL,
    datetime DATETIME NOT NULL,
    open_price DECIMAL(15,4),
    high_price DECIMAL(15,4),
    low_price DECIMAL(15,4),
    close_price DECIMAL(15,4),
    volume INTEGER,
    turnover DECIMAL(20,2),
    bid_price_1 DECIMAL(15,4),
    ask_price_1 DECIMAL(15,4),
    bid_volume_1 INTEGER,
    ask_volume_1 INTEGER,
    FOREIGN KEY (security_id) REFERENCES securities(id),
    UNIQUE(security_id, datetime)
);

-- =============================================================================
-- 投资组合相关表
-- =============================================================================

-- 投资组合表
CREATE TABLE IF NOT EXISTS portfolios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    strategy VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

-- 投资组合持仓表
CREATE TABLE IF NOT EXISTS portfolio_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL,
    security_id INTEGER NOT NULL,
    quantity DECIMAL(15,4) NOT NULL,
    average_cost DECIMAL(15,4),
    current_price DECIMAL(15,4),
    market_value DECIMAL(20,2),
    unrealized_pnl DECIMAL(20,2),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
    FOREIGN KEY (security_id) REFERENCES securities(id),
    UNIQUE(portfolio_id, security_id)
);

-- 投资组合交易记录表
CREATE TABLE IF NOT EXISTS portfolio_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL,
    security_id INTEGER NOT NULL,
    transaction_type VARCHAR(10) NOT NULL, -- BUY, SELL
    quantity DECIMAL(15,4) NOT NULL,
    price DECIMAL(15,4) NOT NULL,
    amount DECIMAL(20,2) NOT NULL,
    commission DECIMAL(10,2) DEFAULT 0,
    transaction_time DATETIME NOT NULL,
    notes TEXT,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
    FOREIGN KEY (security_id) REFERENCES securities(id)
);

-- =============================================================================
-- 算法相关表
-- =============================================================================

-- 算法配置表
CREATE TABLE IF NOT EXISTS algorithm_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    type VARCHAR(50) NOT NULL,
    config_json TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 算法运行结果表
CREATE TABLE IF NOT EXISTS algorithm_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    algorithm_config_id INTEGER NOT NULL,
    portfolio_id INTEGER,
    result_json TEXT NOT NULL,
    performance_metrics TEXT,
    execution_time DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL, -- SUCCESS, FAILED, RUNNING
    error_message TEXT,
    FOREIGN KEY (algorithm_config_id) REFERENCES algorithm_configs(id),
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
);

-- =============================================================================
-- 配置和系统表
-- =============================================================================

-- 系统配置表
CREATE TABLE IF NOT EXISTS system_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT,
    config_type VARCHAR(20) DEFAULT 'string', -- string, number, boolean, json
    description TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 用户配置表
CREATE TABLE IF NOT EXISTS user_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(50) DEFAULT 'default',
    config_key VARCHAR(100) NOT NULL,
    config_value TEXT,
    config_type VARCHAR(20) DEFAULT 'string',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, config_key)
);

-- 系统日志表
CREATE TABLE IF NOT EXISTS system_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level VARCHAR(10) NOT NULL, -- DEBUG, INFO, WARN, ERROR
    module VARCHAR(50),
    message TEXT NOT NULL,
    details TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 索引优化
-- =============================================================================

-- 市场数据查询索引
CREATE INDEX IF NOT EXISTS idx_market_data_security_datetime ON market_data(security_id, datetime);
CREATE INDEX IF NOT EXISTS idx_market_data_datetime ON market_data(datetime);

-- 投资组合查询索引
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_portfolio ON portfolio_positions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_portfolio ON portfolio_transactions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_time ON portfolio_transactions(transaction_time);

-- 算法结果查询索引
CREATE INDEX IF NOT EXISTS idx_algorithm_results_config ON algorithm_results(algorithm_config_id);
CREATE INDEX IF NOT EXISTS idx_algorithm_results_time ON algorithm_results(execution_time);

-- 系统日志查询索引
CREATE INDEX IF NOT EXISTS idx_system_logs_timestamp ON system_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level);
