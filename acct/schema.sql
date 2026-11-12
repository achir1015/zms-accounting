-- 資料助秘之一般公司會計：資料表（可重複執行）

CREATE TABLE IF NOT EXISTS meta (
  k VARCHAR(40) PRIMARY KEY,
  v VARCHAR(255) NOT NULL DEFAULT ''
);

-- 公司（單一公司）
CREATE TABLE IF NOT EXISTS company (
  id TINYINT PRIMARY KEY,
  name VARCHAR(100) NOT NULL DEFAULT '',
  tax_id VARCHAR(10) NOT NULL DEFAULT '',
  owner VARCHAR(40) NOT NULL DEFAULT '',
  phone VARCHAR(30) NOT NULL DEFAULT '',
  address VARCHAR(200) NOT NULL DEFAULT '',
  fiscal_start_month TINYINT NOT NULL DEFAULT 1,
  base_currency CHAR(3) NOT NULL DEFAULT 'TWD',
  auto_post TINYINT NOT NULL DEFAULT 0,          -- 1＝存檔即過帳（即時過帳）；0＝審核後分批過帳
  separate_approver TINYINT NOT NULL DEFAULT 1,  -- 1＝製單人不可審核自己的傳票
  updated_at DATETIME NULL
);

-- 使用者與權限
CREATE TABLE IF NOT EXISTS users (
  uid VARCHAR(20) PRIMARY KEY,
  name VARCHAR(40) NOT NULL,
  pw_hash VARCHAR(200) NOT NULL,
  role VARCHAR(20) NOT NULL DEFAULT '',
  is_admin TINYINT NOT NULL DEFAULT 0,
  active TINYINT NOT NULL DEFAULT 1,
  last_login DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_perms (
  uid VARCHAR(20) NOT NULL,
  func VARCHAR(10) NOT NULL,
  lvl TINYINT NOT NULL DEFAULT 0,               -- 0 無、1 查詢、2 維護
  PRIMARY KEY (uid, func)
);

CREATE TABLE IF NOT EXISTS audit_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  uid VARCHAR(20) NOT NULL DEFAULT '',
  action VARCHAR(30) NOT NULL,
  target VARCHAR(60) NOT NULL DEFAULT '',
  detail VARCHAR(500) NOT NULL DEFAULT '',
  INDEX idx_audit_at (at)
);

-- 會計科目
CREATE TABLE IF NOT EXISTS accounts (
  code VARCHAR(10) PRIMARY KEY,
  name VARCHAR(60) NOT NULL,
  parent VARCHAR(10) NOT NULL DEFAULT '',
  level TINYINT NOT NULL DEFAULT 4,             -- 1 大類、2 中類、3 小類、4 明細（只有明細科目可記帳）
  nature CHAR(1) NOT NULL DEFAULT 'D',          -- 正常餘額：D 借、C 貸
  is_cash TINYINT NOT NULL DEFAULT 0,           -- 現金及約當現金（現金簿、現金流量表用）
  cf_section VARCHAR(4) NOT NULL DEFAULT 'OP',  -- 現金流量表歸類：OP 營業、INV 投資、FIN 籌資
  partner_kind VARCHAR(2) NOT NULL DEFAULT '',  -- 需輸入往來對象：C 客戶、V 廠商、E 員工
  need_dept TINYINT NOT NULL DEFAULT 0,
  currency CHAR(3) NOT NULL DEFAULT '',         -- 外幣科目（現值調整用）
  active TINYINT NOT NULL DEFAULT 1,
  memo VARCHAR(100) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS departments (
  code VARCHAR(10) PRIMARY KEY,
  name VARCHAR(40) NOT NULL,
  manager VARCHAR(40) NOT NULL DEFAULT '',
  active TINYINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS employees (
  code VARCHAR(10) PRIMARY KEY,
  name VARCHAR(40) NOT NULL,
  dept VARCHAR(10) NOT NULL DEFAULT '',
  title VARCHAR(30) NOT NULL DEFAULT '',
  phone VARCHAR(30) NOT NULL DEFAULT '',
  hire_date DATE NULL,
  active TINYINT NOT NULL DEFAULT 1
);

-- 往來對象：客戶 C、廠商 V
CREATE TABLE IF NOT EXISTS partners (
  kind CHAR(1) NOT NULL,
  code VARCHAR(12) NOT NULL,
  name VARCHAR(80) NOT NULL,
  short_name VARCHAR(20) NOT NULL DEFAULT '',
  tax_id VARCHAR(10) NOT NULL DEFAULT '',
  contact VARCHAR(30) NOT NULL DEFAULT '',
  phone VARCHAR(30) NOT NULL DEFAULT '',
  address VARCHAR(200) NOT NULL DEFAULT '',
  pay_terms VARCHAR(30) NOT NULL DEFAULT '',
  active TINYINT NOT NULL DEFAULT 1,
  PRIMARY KEY (kind, code)
);

CREATE TABLE IF NOT EXISTS projects (
  code VARCHAR(12) PRIMARY KEY,
  name VARCHAR(60) NOT NULL,
  start_date DATE NULL,
  end_date DATE NULL,
  budget DECIMAL(16,2) NOT NULL DEFAULT 0,
  active TINYINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS currencies (
  code CHAR(3) PRIMARY KEY,
  name VARCHAR(20) NOT NULL,
  rate DECIMAL(14,6) NOT NULL DEFAULT 1,        -- 1 外幣 = ? 本國幣
  rate_date DATE NULL
);

-- 摘要片語
CREATE TABLE IF NOT EXISTS phrases (
  id INT AUTO_INCREMENT PRIMARY KEY,
  text VARCHAR(100) NOT NULL,
  UNIQUE KEY uq_phrase (text)
);

-- 常用分錄
CREATE TABLE IF NOT EXISTS templates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(60) NOT NULL,
  v_type VARCHAR(4) NOT NULL DEFAULT '轉',
  memo VARCHAR(200) NOT NULL DEFAULT '',
  UNIQUE KEY uq_tpl (name)
);

CREATE TABLE IF NOT EXISTS template_lines (
  tpl_id INT NOT NULL,
  line_no SMALLINT NOT NULL,
  account VARCHAR(10) NOT NULL,
  side CHAR(1) NOT NULL,                        -- D 借、C 貸
  summary VARCHAR(100) NOT NULL DEFAULT '',
  ratio DECIMAL(8,4) NOT NULL DEFAULT 0,        -- 以輸入金額乘上比率；0＝不自動帶金額
  PRIMARY KEY (tpl_id, line_no)
);

-- 會計期間（關帳控制）
CREATE TABLE IF NOT EXISTS periods (
  ym CHAR(6) PRIMARY KEY,
  closed TINYINT NOT NULL DEFAULT 0,
  closed_by VARCHAR(20) NOT NULL DEFAULT '',
  closed_at DATETIME NULL
);

-- 傳票
CREATE TABLE IF NOT EXISTS vouchers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  v_no VARCHAR(16) NOT NULL,
  v_date DATE NOT NULL,
  v_type VARCHAR(4) NOT NULL,                   -- 收、支、轉、開帳、結帳、調整
  status TINYINT NOT NULL DEFAULT 0,            -- 0 未審核、1 已審核、2 已過帳、9 作廢
  memo VARCHAR(200) NOT NULL DEFAULT '',
  total DECIMAL(16,2) NOT NULL DEFAULT 0,
  attachments SMALLINT NOT NULL DEFAULT 0,      -- 附件張數
  created_by VARCHAR(20) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_by VARCHAR(20) NOT NULL DEFAULT '',
  updated_at DATETIME NULL,
  approved_by VARCHAR(20) NOT NULL DEFAULT '',
  approved_at DATETIME NULL,
  posted_by VARCHAR(20) NOT NULL DEFAULT '',
  posted_at DATETIME NULL,
  UNIQUE KEY uq_vno (v_no),
  INDEX idx_v_date (v_date, status)
);

CREATE TABLE IF NOT EXISTS voucher_lines (
  voucher_id INT NOT NULL,
  line_no SMALLINT NOT NULL,
  account VARCHAR(10) NOT NULL,
  summary VARCHAR(100) NOT NULL DEFAULT '',
  debit DECIMAL(16,2) NOT NULL DEFAULT 0,
  credit DECIMAL(16,2) NOT NULL DEFAULT 0,
  dept VARCHAR(10) NOT NULL DEFAULT '',
  project VARCHAR(12) NOT NULL DEFAULT '',
  partner_kind CHAR(1) NOT NULL DEFAULT '',
  partner VARCHAR(12) NOT NULL DEFAULT '',
  currency CHAR(3) NOT NULL DEFAULT '',
  fx_rate DECIMAL(14,6) NOT NULL DEFAULT 0,
  fx_amount DECIMAL(16,2) NOT NULL DEFAULT 0,   -- 外幣金額（借正貸負）
  PRIMARY KEY (voucher_id, line_no),
  INDEX idx_vl_account (account),
  INDEX idx_vl_partner (partner_kind, partner)
);

-- 預算（年度、科目、部門，每月金額）
CREATE TABLE IF NOT EXISTS budgets (
  year SMALLINT NOT NULL,
  account VARCHAR(10) NOT NULL,
  dept VARCHAR(10) NOT NULL DEFAULT '',
  m1 DECIMAL(16,2) NOT NULL DEFAULT 0, m2 DECIMAL(16,2) NOT NULL DEFAULT 0, m3 DECIMAL(16,2) NOT NULL DEFAULT 0,
  m4 DECIMAL(16,2) NOT NULL DEFAULT 0, m5 DECIMAL(16,2) NOT NULL DEFAULT 0, m6 DECIMAL(16,2) NOT NULL DEFAULT 0,
  m7 DECIMAL(16,2) NOT NULL DEFAULT 0, m8 DECIMAL(16,2) NOT NULL DEFAULT 0, m9 DECIMAL(16,2) NOT NULL DEFAULT 0,
  m10 DECIMAL(16,2) NOT NULL DEFAULT 0, m11 DECIMAL(16,2) NOT NULL DEFAULT 0, m12 DECIMAL(16,2) NOT NULL DEFAULT 0,
  PRIMARY KEY (year, account, dept)
);

-- 財務比率公式（自由設定）
CREATE TABLE IF NOT EXISTS ratios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(40) NOT NULL,
  formula VARCHAR(300) NOT NULL,
  unit VARCHAR(4) NOT NULL DEFAULT '%',
  memo VARCHAR(200) NOT NULL DEFAULT '',
  sort SMALLINT NOT NULL DEFAULT 0,
  UNIQUE KEY uq_ratio (name)
);

-- 進銷存拋轉匯入紀錄（v1.4.0）
CREATE TABLE IF NOT EXISTS gl_imports (
  id INT AUTO_INCREMENT PRIMARY KEY,
  batch_uid VARCHAR(64) NOT NULL,
  batch_no VARCHAR(20) NOT NULL DEFAULT '',
  source VARCHAR(60) NOT NULL DEFAULT '',
  company_name VARCHAR(80) NOT NULL DEFAULT '',
  tax_id VARCHAR(10) NOT NULL DEFAULT '',
  date_from DATE NULL,
  date_to DATE NULL,
  voucher_count INT NOT NULL DEFAULT 0,
  total DECIMAL(16,2) NOT NULL DEFAULT 0,
  voucher_ids TEXT NULL,
  voucher_nos VARCHAR(60) NOT NULL DEFAULT '',
  created_info TEXT NULL,
  status TINYINT NOT NULL DEFAULT 1,
  imported_by VARCHAR(20) NOT NULL DEFAULT '',
  imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  canceled_by VARCHAR(20) NOT NULL DEFAULT '',
  canceled_at DATETIME NULL,
  INDEX idx_uid (batch_uid)
);
