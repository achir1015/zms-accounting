"""帳簿與財務報表（只計入已過帳傳票，可選擇含未過帳試算）。

金額正負：每個科目以「正常餘額方向」為正（資產、費用借餘為正；負債、權益、收入貸餘為正），
抵銷科目（累計折舊、銷貨退回…）自然變成負數，彙總時直接相加即可。
"""
import ast
import datetime as dt
import operator
import re
from decimal import Decimal

from . import rocdate
from .seed import default_nature

ZERO = Decimal(0)


def sign_of(prefix: str) -> int:
    return 1 if default_nature(prefix) == "D" else -1


class Reports:
    def __init__(self, books):
        self.b = books
        self.db = books.db

    # ------------------------------------------------------------ 共用
    def _status(self, include_unposted):
        return "v.status IN (0,1,2)" if include_unposted else "v.status=2"

    def _sums(self, start=None, end=None, include_unposted=False, exclude_closing=False, dept="", project=""):
        """各明細科目在期間內的借、貸合計：{code: (debit, credit)}"""
        sql = ("SELECT l.account, SUM(l.debit) d, SUM(l.credit) c FROM voucher_lines l "
               "JOIN vouchers v ON v.id=l.voucher_id WHERE " + self._status(include_unposted))
        args = []
        if start:
            sql += " AND v.v_date>=%s"
            args.append(start)
        if end:
            sql += " AND v.v_date<=%s"
            args.append(end)
        if exclude_closing:
            sql += " AND v.v_type<>'結帳'"
        if dept:
            sql += " AND l.dept=%s"
            args.append(dept)
        if project:
            sql += " AND l.project=%s"
            args.append(project)
        sql += " GROUP BY l.account"
        return {r["account"]: (Decimal(r["d"] or 0), Decimal(r["c"] or 0)) for r in self.db.rows(sql, args)}

    @staticmethod
    def _bal(sums, prefix, sign=None):
        """以 prefix 類別的方向計算餘額。"""
        sg = sign if sign is not None else sign_of(prefix)
        t = ZERO
        for code, (d, c) in sums.items():
            if code.startswith(prefix):
                t += (d - c) * sg
        return t

    def _accounts(self):
        return {r["code"]: r for r in self.db.rows("SELECT * FROM accounts ORDER BY code")}

    # ------------------------------------------------------------ 日記簿
    def journal(self, start, end, include_unposted=False, v_type=""):
        sql = ("SELECT v.id, v.v_no, v.v_date, v.v_type, v.status, l.line_no, l.account, a.name AS account_name, "
               "l.summary, l.debit, l.credit, l.dept, l.partner FROM vouchers v "
               "JOIN voucher_lines l ON l.voucher_id=v.id LEFT JOIN accounts a ON a.code=l.account "
               "WHERE " + self._status(include_unposted) + " AND v.v_date BETWEEN %s AND %s")
        args = [start, end]
        if v_type:
            sql += " AND v.v_type=%s"
            args.append(v_type)
        return self.db.rows(sql + " ORDER BY v.v_date, v.v_no, l.line_no", args)

    # ------------------------------------------------------------ 明細分類帳
    def ledger(self, account, start, end, include_unposted=False, partner_kind="", partner=""):
        """單一科目（或代號開頭）明細：期初、逐筆、累計餘額。"""
        sg = sign_of(account)
        cond, args = "l.account LIKE %s", [account + "%"]
        if partner:
            cond += " AND l.partner_kind=%s AND l.partner=%s"
            args += [partner_kind, partner]
        st = self._status(include_unposted)
        r = self.db.row("SELECT SUM(l.debit) d, SUM(l.credit) c FROM voucher_lines l JOIN vouchers v "
                        "ON v.id=l.voucher_id WHERE %s AND %s AND v.v_date<%%s" % (st, cond), args + [start])
        opening = (Decimal(r["d"] or 0) - Decimal(r["c"] or 0)) * sg
        rows = self.db.rows("SELECT v.id, v.v_no, v.v_date, v.v_type, l.account, a.name AS account_name, l.summary, "
                            "l.debit, l.credit, l.partner_kind, l.partner, l.dept FROM voucher_lines l "
                            "JOIN vouchers v ON v.id=l.voucher_id LEFT JOIN accounts a ON a.code=l.account "
                            "WHERE %s AND %s AND v.v_date BETWEEN %%s AND %%s ORDER BY v.v_date, v.v_no, l.line_no"
                            % (st, cond), args + [start, end])
        bal = opening
        for x in rows:
            bal += (Decimal(x["debit"]) - Decimal(x["credit"])) * sg
            x["balance"] = bal
        return dict(opening=opening, rows=rows, closing=bal, debit=sum((Decimal(x["debit"]) for x in rows), ZERO),
                    credit=sum((Decimal(x["credit"]) for x in rows), ZERO))

    # ------------------------------------------------------------ 總分類帳／試算表
    def trial_balance(self, start, end, level=4, include_unposted=False, hide_zero=True):
        accts = self._accounts()
        before = self._sums(None, start - dt.timedelta(days=1), include_unposted)
        during = self._sums(start, end, include_unposted)
        out = []
        for code, a in accts.items():
            if a["level"] != level:
                continue
            od = oc = pd = pc = ZERO
            for c2, (d, c) in before.items():
                if c2.startswith(code):
                    od += d
                    oc += c
            for c2, (d, c) in during.items():
                if c2.startswith(code):
                    pd += d
                    pc += c
            open_net, close_net = od - oc, od - oc + pd - pc
            if hide_zero and not (open_net or pd or pc or close_net):
                continue
            out.append(dict(code=code, name=a["name"], nature=a["nature"],
                            open_d=open_net if open_net > 0 else ZERO, open_c=-open_net if open_net < 0 else ZERO,
                            debit=pd, credit=pc,
                            close_d=close_net if close_net > 0 else ZERO, close_c=-close_net if close_net < 0 else ZERO))
        tot = {k: sum((r[k] for r in out), ZERO) for k in ("open_d", "open_c", "debit", "credit", "close_d", "close_c")}
        return dict(rows=out, total=tot, balanced=tot["close_d"] == tot["close_c"] and tot["debit"] == tot["credit"])

    def general_ledger(self, start, end, level=4, include_unposted=False):
        """總分類帳：各科目期初、本期借貸、期末（正常方向）。"""
        tb = self.trial_balance(start, end, level, include_unposted)
        accts = self._accounts()
        for r in tb["rows"]:
            sg = 1 if accts[r["code"]]["nature"] == "D" else -1
            r["opening"] = (r["open_d"] - r["open_c"]) * sg
            r["closing"] = (r["close_d"] - r["close_c"]) * sg
        return tb["rows"]

    # ------------------------------------------------------------ 現金簿
    def cash_book(self, start, end, include_unposted=False):
        codes = [r["code"] for r in self.db.rows("SELECT code FROM accounts WHERE is_cash=1 AND level=4 ORDER BY code")]
        books = []
        for code in codes:
            led = self.ledger(code, start, end, include_unposted)
            if led["rows"] or led["opening"]:
                led["code"], led["name"] = code, self._accounts()[code]["name"]
                # 對方科目
                for x in led["rows"]:
                    other = self.db.rows("SELECT DISTINCT l.account, a.name FROM voucher_lines l LEFT JOIN accounts a "
                                         "ON a.code=l.account WHERE l.voucher_id=%s AND l.account<>%s",
                                         (x["id"], code))
                    x["other"] = "、".join(o["name"] or o["account"] for o in other[:3]) + ("…" if len(other) > 3 else "")
                books.append(led)
        return books

    # ------------------------------------------------------------ 損益表
    def income_statement(self, start, end, dept="", include_unposted=False, compare=None):
        """compare=(start, end) 時多一欄比較期間。"""
        cur = self._sums(start, end, include_unposted, exclude_closing=True, dept=dept)
        cmp_ = self._sums(compare[0], compare[1], include_unposted, exclude_closing=True, dept=dept) if compare else None
        accts = self._accounts()

        def amt(sums, prefix, sign):
            return self._bal(sums, prefix, sign) if sums is not None else None

        lines = []

        def section(title, prefix, sign):
            lines.append(dict(kind="head", name=title))
            for code, a in accts.items():
                if a["level"] == 4 and code.startswith(prefix):
                    v, w = amt(cur, code, sign), amt(cmp_, code, sign)
                    if v or w:
                        lines.append(dict(kind="item", code=code, name=a["name"], amount=v, compare=w))
            v, w = amt(cur, prefix, sign), amt(cmp_, prefix, sign)
            lines.append(dict(kind="sub", name=title + "合計", amount=v, compare=w))
            return v, w

        def total(name, v, w):
            lines.append(dict(kind="total", name=name, amount=v, compare=w))

        rev, rev_c = section("營業收入", "4", -1)
        cost, cost_c = section("營業成本", "5", 1)
        gp = rev - cost
        gp_c = rev_c - cost_c if compare else None
        total("營業毛利", gp, gp_c)
        exp, exp_c = section("營業費用", "6", 1)
        op = gp - exp
        op_c = gp_c - exp_c if compare else None
        total("營業淨利（損）", op, op_c)
        ni_inc, ni_inc_c = section("營業外收益", "71", -1)
        ni_exp, ni_exp_c = section("營業外費損", "72", 1)
        pre = op + ni_inc - ni_exp
        pre_c = op_c + ni_inc_c - ni_exp_c if compare else None
        total("稅前淨利（損）", pre, pre_c)
        tax, tax_c = section("所得稅費用", "8", 1)
        net = pre - tax
        net_c = pre_c - tax_c if compare else None
        total("本期淨利（損）", net, net_c)
        for ln in lines:
            ln["pct"] = (ln["amount"] / rev * 100) if rev and ln.get("amount") is not None else None
        return dict(lines=lines, revenue=rev, gross=gp, operating=op, pretax=pre, net=net, net_compare=net_c)

    def net_income(self, start, end, include_unposted=False, dept=""):
        s = self._sums(start, end, include_unposted, exclude_closing=True, dept=dept)
        t = ZERO
        for code, (d, c) in s.items():
            if code[0] in "45678":
                t += c - d
        return t

    # ------------------------------------------------------------ 資產負債表
    def balance_sheet(self, as_of, include_unposted=False):
        sums = self._sums(None, as_of, include_unposted)
        accts = self._accounts()
        # 尚未結轉到累積盈虧的損益（含本年度與未結帳的以前年度）
        unclosed = ZERO
        for code, (d, c) in sums.items():
            if code[0] in "45678":
                unclosed += c - d
        sides = []
        for big, title in (("1", "資產"), ("2", "負債"), ("3", "權益")):
            items = []
            for mid, a in accts.items():
                if a["level"] != 2 or not mid.startswith(big):
                    continue
                details = []
                for code, b in accts.items():
                    if b["level"] == 4 and code.startswith(mid):
                        v = self._bal(sums, code, sign_of(big))
                        if v:
                            details.append(dict(code=code, name=b["name"], amount=v))
                subtotal = self._bal(sums, mid, sign_of(big))
                if big == "3" and mid == "33":
                    details.append(dict(code="", name="本期損益（尚未結轉）", amount=unclosed))
                    subtotal += unclosed
                if details or subtotal:
                    items.append(dict(code=mid, name=a["name"], details=details, amount=subtotal))
            if big == "3" and not any(i["code"] == "33" for i in items) and unclosed:
                items.append(dict(code="33", name="保留盈餘", amount=unclosed,
                                  details=[dict(code="", name="本期損益（尚未結轉）", amount=unclosed)]))
            total = self._bal(sums, big, sign_of(big)) + (unclosed if big == "3" else ZERO)
            sides.append(dict(code=big, name=title, items=items, total=total))
        assets, liab, eq = (s["total"] for s in sides)
        current_assets = self._bal(sums, "11") + self._bal(sums, "12")
        return dict(sides=sides, assets=assets, liabilities=liab, equity=eq, current_assets=current_assets,
                    balanced=assets == liab + eq, unclosed=unclosed)

    # ------------------------------------------------------------ 現金流量表（直接法）
    def cash_flow(self, start, end, include_unposted=False):
        """凡有現金科目的傳票，把「非現金」那幾行依科目的現金流量歸類（營業／投資／籌資）。
        每一行對現金的影響＝貸方－借方，加總恰好等於現金淨增減。"""
        st = self._status(include_unposted)
        rows = self.db.rows(
            "SELECT l.account, a.name, a.cf_section, SUM(l.credit-l.debit) amt FROM voucher_lines l "
            "JOIN vouchers v ON v.id=l.voucher_id JOIN accounts a ON a.code=l.account "
            "WHERE " + st + " AND v.v_type NOT IN ('開帳','結帳') AND v.v_date BETWEEN %s AND %s AND a.is_cash=0 "
            "AND EXISTS (SELECT 1 FROM voucher_lines x JOIN accounts xa ON xa.code=x.account "
            "WHERE x.voucher_id=v.id AND xa.is_cash=1) GROUP BY l.account, a.name, a.cf_section "
            "HAVING SUM(l.credit-l.debit)<>0 ORDER BY a.cf_section, l.account", (start, end))
        sections = {}
        for k in ("OP", "INV", "FIN"):
            items = [dict(code=r["account"], name=r["name"], amount=Decimal(r["amt"])) for r in rows
                     if r["cf_section"] == k]
            sections[k] = dict(items=items, total=sum((i["amount"] for i in items), ZERO))
        cash_codes = [r["code"] for r in self.db.rows("SELECT code FROM accounts WHERE is_cash=1")]
        before = self._sums(None, start - dt.timedelta(days=1), include_unposted)
        after = self._sums(None, end, include_unposted)
        opening = sum(((d - c) for code, (d, c) in before.items() if code in cash_codes), ZERO)
        closing = sum(((d - c) for code, (d, c) in after.items() if code in cash_codes), ZERO)
        # 開帳傳票帶進來的現金、或現金科目互轉以外的差異
        net = sum(s["total"] for s in sections.values())
        other = closing - opening - net
        return dict(sections=sections, net=net, opening=opening, closing=closing, other=other)

    # ------------------------------------------------------------ 財務比率
    def ratios(self, start, end, include_unposted=False):
        bal = self._sums(None, end, include_unposted)
        per = self._sums(start, end, include_unposted, exclude_closing=True)
        ni = self.net_income(start, end, include_unposted)
        eq = self.balance_sheet(end, include_unposted)["equity"]
        out = []
        for r in self.db.rows("SELECT * FROM ratios ORDER BY sort, id"):
            try:
                v = evaluate(r["formula"], lambda p: self._bal(bal, p), lambda p: self._bal(per, p), ni, eq)
                err = ""
            except ZeroDivisionError:
                v, err = None, "分母為 0"
            except Exception as e:
                v, err = None, "公式錯誤：%s" % e
            out.append(dict(r, value=v, error=err))
        return out

    # ------------------------------------------------------------ 往來明細（應收、應付）
    def partner_balances(self, kind, as_of, include_unposted=False):
        st = self._status(include_unposted)
        table = "employees e" if kind == "E" else "partners e"
        join_on = "e.code=l.partner" + ("" if kind == "E" else " AND e.kind=l.partner_kind")
        rows = self.db.rows(
            "SELECT l.partner code, MAX(e.name) name, l.account, MAX(a.name) account_name, a.nature, "
            "SUM(l.debit) d, SUM(l.credit) c FROM voucher_lines l JOIN vouchers v ON v.id=l.voucher_id "
            "JOIN accounts a ON a.code=l.account LEFT JOIN " + table + " ON " + join_on +
            " WHERE " + st + " AND l.partner_kind=%s AND v.v_date<=%s GROUP BY l.partner, l.account, a.nature "
            "ORDER BY l.partner, l.account", (kind, as_of))
        for r in rows:
            r["balance"] = (Decimal(r["d"] or 0) - Decimal(r["c"] or 0)) * (1 if r["nature"] == "D" else -1)
        return [r for r in rows if r["balance"]]

    # ------------------------------------------------------------ 預算比較
    def budget_compare(self, year, upto_month, dept=""):
        s, _ = rocdate.fiscal_year_range(year)
        e = rocdate.month_last(dt.date(year, upto_month, 1))
        actual = self._sums(s, e, exclude_closing=True, dept=dept)
        accts = self._accounts()
        out = []
        for b in self.db.rows("SELECT * FROM budgets WHERE year=%s AND dept=%s ORDER BY account", (year, dept)):
            bud = sum((Decimal(b["m%d" % m]) for m in range(1, upto_month + 1)), ZERO)
            act = self._bal(actual, b["account"])
            out.append(dict(code=b["account"], name=accts.get(b["account"], {}).get("name", ""), budget=bud,
                            actual=act, diff=act - bud, pct=(act / bud * 100) if bud else None))
        return out

    # ------------------------------------------------------------ 首頁摘要
    def dashboard(self):
        today = rocdate.today()
        ms = rocdate.month_first(today)
        cash = self._sums(None, today)
        cash_codes = {r["code"] for r in self.db.rows("SELECT code FROM accounts WHERE is_cash=1")}
        month = self._sums(ms, today, exclude_closing=True)
        months = []
        y, m = today.year, today.month
        for _ in range(12):
            s = dt.date(y, m, 1)
            sm = self._sums(s, rocdate.month_last(s), exclude_closing=True)
            months.append(dict(label="%d/%d" % (y - 1911, m), revenue=self._bal(sm, "4") + self._bal(sm, "71"),
                               expense=self._bal(sm, "5") + self._bal(sm, "6") + self._bal(sm, "72") + self._bal(sm, "8")))
            y, m = (y, m - 1) if m > 1 else (y - 1, 12)
        months.reverse()
        return dict(
            cash=sum(((d - c) for code, (d, c) in cash.items() if code in cash_codes), ZERO),
            receivable=self._bal(cash, "113") + self._bal(cash, "114"),
            payable=self._bal(cash, "212") + self._bal(cash, "213"),
            month_revenue=self._bal(month, "4") + self._bal(month, "71"),
            month_net=sum(((c - d) for code, (d, c) in month.items() if code[0] in "45678"), ZERO),
            pending=int(self.db.value("SELECT COUNT(*) FROM vouchers WHERE status IN (0,1)") or 0),
            unapproved=int(self.db.value("SELECT COUNT(*) FROM vouchers WHERE status=0") or 0),
            months=months)


# ---------------------------------------------------------------- 比率公式計算（安全，只允許四則運算）
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def evaluate(formula, B, P, NI, EQ):
    def repl(m):
        fn, code = m.group(1), m.group(2)
        if not code.isdigit():
            raise ValueError("科目代號 %s 不正確" % code)
        v = B(code) if fn == "B" else P(code)
        return "(%s)" % v
    expr = re.sub(r"\b([BP])\(\s*([0-9A-Za-z]+)\s*\)", repl, formula)
    expr = re.sub(r"\bNI\b", "(%s)" % NI, expr)
    expr = re.sub(r"\bEQ\b", "(%s)" % EQ, expr)
    tree = ast.parse(expr, mode="eval")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return Decimal(str(n.value))
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Div) and b == 0:
                raise ZeroDivisionError
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError("只能使用 B()、P()、NI、EQ、數字與 + - * / ( )")
    return ev(tree)
