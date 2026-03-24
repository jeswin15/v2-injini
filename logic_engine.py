import re
import pandas as pd
from datetime import datetime
from statistics import median

# ──────────────────────────────────────────────────────────────────────────────
#  Date Parsing
# ──────────────────────────────────────────────────────────────────────────────

_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DATE_FMTS = [
    "%B %Y",                    # September 2023
    "%b %Y",                    # Sep 2023
    "%Y-%m-%d",                 # 2023-09-01
    "%Y-%m-%dT%H:%M:%S.%fZ",   # 2023-09-01T00:00:00.000Z
    "%Y-%m-%dT%H:%M:%SZ",      # 2023-09-01T00:00:00Z
    "%m/%Y",                    # 09/2023
    "%m-%Y",                    # 09-2023
    "%Y/%m",                    # 2023/09
    "%d/%m/%Y",                 # 01/09/2023
]

def parse_reporting_month(val) -> pd.Timestamp:
    if isinstance(val, list): val = val[0] if val else None
    if val is None: return pd.NaT
    if not isinstance(val, str):
        try: val = str(val)
        except: return pd.NaT
    val = val.strip()
    if not val or val.lower() in ("unknown", "n/a", "-", "none"): return pd.NaT
    for fmt in _DATE_FMTS:
        try: return datetime.strptime(val, fmt).replace(day=1)
        except ValueError: continue
    m = re.search(r"\b([A-Za-z]+)\b\s+(\d{4})\b", val)
    if m:
        word, year = m.group(1).lower(), m.group(2)
        if word in _MONTH_ABBR: return datetime(int(year), _MONTH_ABBR[word], 1)
        for fmt in ("%B", "%b"):
            try:
                dt = datetime.strptime(m.group(1), fmt)
                return datetime(int(year), dt.month, 1)
            except ValueError: continue
    m2 = re.match(r"^([A-Za-z]{3})-(\d{2})$", val)
    if m2:
        mon = m2.group(1).lower()
        yr = int(m2.group(2)) + 2000
        if mon in _MONTH_ABBR: return datetime(yr, _MONTH_ABBR[mon], 1)
    return pd.NaT

# ──────────────────────────────────────────────────────────────────────────────
#  Growth Helpers (Mathematical Specification)
# ──────────────────────────────────────────────────────────────────────────────

def _calculate_growth(series: pd.Series):
    clean = series.dropna()
    n = len(clean)
    
    if n < 6: return "Insufficient Data"
    elif n <= 11: k = 3
    elif n <= 17: k = 6
    elif n <= 23: k = 12
    else: k = 12
    
    first = clean.iloc[:k].mean()
    last  = clean.iloc[-k:].mean()
    
    if first == 0 and last == 0: return 0.0
    if first == 0 and last > 0:  return 100.0
    if first == 0 and last < 0:  return -100.0
    
    # FIX: use abs(first) as denominator so businesses that started at a loss
    # (negative baseline) don't have their growth sign flipped.
    # Client spec: "Uses the absolute value of the baseline to correctly handle
    # businesses that started at a loss."
    denom = abs(first)
    return round(((last - first) / denom) * 100, 1)

def _calc_pct_change(baseline, current):
    try:
        baseline, current = float(baseline), float(current)
        if baseline == 0 and current == 0: return 0.0
        if baseline == 0 and current > 0: return 100.0
        if baseline == 0 and current < 0: return -100.0
        return round(((current - baseline) / baseline) * 100, 1)
    except:
        return 0.0

def _safe_round(v):
    try:
        f = float(v)
        return round(f) if pd.notna(f) else None
    except:
        return None

def _safe_float(v):
    try:
        f = float(v)
        return f if pd.notna(f) else None
    except:
        return None

# ──────────────────────────────────────────────────────────────────────────────
#  Main KPI Calculator
# ──────────────────────────────────────────────────────────────────────────────

def calculate_kpis(df: pd.DataFrame, time_range="all", custom_from=None, custom_to=None) -> dict:
    df = df.copy()
    df["Date"] = df["Reporting Month"].apply(parse_reporting_month)
    df = df[df["Business Name"].notna() & (df["Business Name"].str.strip() != "") & (df["Business Name"].str.lower() != "unknown")].copy()

    global_s_date = None
    global_e_date = None
    if time_range != "all":
        valid_dates = df["Date"].dropna()
        if not valid_dates.empty:
            m_max = valid_dates.max()
            s_date = None
            e_date = m_max
            if time_range == '6': s_date = m_max - pd.DateOffset(months=5)
            elif time_range == '12': s_date = m_max - pd.DateOffset(months=11)
            elif time_range == 'ytd': s_date = pd.to_datetime(f"{m_max.year}-01-01")
            elif time_range == 'custom' and custom_from and custom_to:
                try: s_date, e_date = pd.to_datetime(custom_from), pd.to_datetime(custom_to)
                except: pass
            if s_date:
                global_s_date = s_date
                global_e_date = e_date
                df = df[(df["Date"].isna()) | ((df["Date"] >= s_date) & (df["Date"] <= e_date))].copy()

    df["Month_Index"] = 0
    for biz_name, biz_idx in df.groupby("Business Name").groups.items():
        sorted_idx = df.loc[biz_idx].sort_values("Date").index
        valid_dates = df.loc[sorted_idx, "Date"].dropna()
        if valid_dates.empty: continue
        start = valid_dates.min()
        for idx in sorted_idx:
            d = df.at[idx, "Date"]
            if pd.notna(d):
                df.at[idx, "Month_Index"] = ((d.year - start.year) * 12 + (d.month - start.month) + 1)

    # Program Extended TS
    valid_global = df[df["Date"].notna()].copy()
    program_series = {}
    if not valid_global.empty:
        pm = valid_global.groupby("Month_Index").agg({"Monthly Sales (R)": "sum", "Monthly Net Profit": "sum", "Total Jobs": "sum", "Female Jobs": "sum", "Youth Jobs": "sum", "Total Subscribers Students": "sum", "Total Subscribers Teachers": "sum", "New Subscribers Students": "sum", "New Subscribers Teachers": "sum", "SA Schools": "sum", "Q1-3 Schools": "sum"}).sort_index()
        program_series = {
            "months": [int(m) for m in pm.index.tolist()],
            "sales": [round(float(v)) for v in pm["Monthly Sales (R)"]],
            "profit": [round(float(v)) for v in pm["Monthly Net Profit"]],
            "jobs_total": [round(float(v)) for v in pm["Total Jobs"]],
            "jobs_female": [round(float(v)) for v in pm["Female Jobs"]],
            "jobs_youth": [round(float(v)) for v in pm["Youth Jobs"]],
            "reach_learners": [round(float(v)) for v in pm["Total Subscribers Students"]],
            "reach_educators": [round(float(v)) for v in pm["Total Subscribers Teachers"]],
            "reach_new_learners_cum": [round(float(v)) for v in pm["New Subscribers Students"].cumsum()],
            "reach_new_educators_cum": [round(float(v)) for v in pm["New Subscribers Teachers"].cumsum()],
            "reach_sa_schools": [round(float(v)) for v in pm["SA Schools"]],
            "reach_q13_schools": [round(float(v)) for v in pm["Q1-3 Schools"]]
        }

    cohort_summaries, cohort_detail, venture_data, red_flags, investment_ledger, all_time_series = [], {}, [], [], [], []
    prog_total_jobs = prog_new_jobs = prog_female_jobs = prog_youth_jobs = prog_female_new = prog_youth_new = 0
    prog_total_sub = prog_new_sub = prog_total_schools = prog_female_stu = prog_total_stu = prog_rural_stu = prog_disability_stu = 0
    grand_total_sales = 0.0
    cohort_growth_metrics = {}

    EXPECTED_COHORTS = ["Cohort 1", "Cohort 2", "Cohort 3", "Cohort 4"]
    for cohort_name in EXPECTED_COHORTS:
        cdf = df[df["Cohort"] == cohort_name].copy()
        if cdf.empty:
            cohort_detail[cohort_name] = _empty_cohort_detail()
            cohort_summaries.append({
                "Cohort": cohort_name, "Ventures": 0, "Total Sales": 0.0, "Total Profit": 0.0,
                "Total Jobs": 0, "Jobs Pct Change": 0.0,
                "Total Learners": 0, "Total Educators": 0, "New Learners": 0, "New Educators": 0,
                "Median Sales Growth": "Insufficient Data", "Median Profit Growth": "Insufficient Data"
            })
            continue

        coh_total_jobs = coh_total_learners = coh_total_educators = 0
        coh_sg_list, coh_pg_list, coh_months_list = [], [], []
        f_sales, f_profit, f_reach, f_jobs = [], [], [], []
        growth_table, jobs_table, users_table, disagg_table, coh_investments = [], [], [], [], []
        padded_cohort_dfs = []

        for biz_name, bg in cdf.groupby("Business Name"):
            bs = bg.sort_values("Date")
            valid_bs = bs[bs["Date"].notna()].copy()

            if not valid_bs.empty:
                valid_bs = valid_bs.drop_duplicates(subset=["Date"], keep="last")
                pad_s = global_s_date if global_s_date is not None and not pd.isna(global_s_date) else valid_bs["Date"].min()
                pad_e = global_e_date if global_e_date is not None and not pd.isna(global_e_date) else valid_bs["Date"].max()
                all_months = pd.date_range(start=pad_s, end=pad_e, freq='MS')
                valid_bs = valid_bs.set_index("Date").reindex(all_months).ffill().fillna(0).reset_index(names=["Date"])
                bs = valid_bs
                padded_cohort_dfs.append(bs)
                
            n = len(bs)
            sg = _calculate_growth(bs["Monthly Sales (R)"])
            pg = _calculate_growth(bs["Monthly Net Profit"])
            if isinstance(sg, (int, float)): coh_sg_list.append(sg)
            if isinstance(pg, (int, float)): coh_pg_list.append(pg)
            coh_months_list.append(n)

            biz_sales = float(bs["Monthly Sales (R)"].sum())
            grand_total_sales += biz_sales

            # Use latest available (non-NaN) for health metrics
            def _latest(col, default=0.0):
                valid = bs[col].dropna()
                return float(valid.iloc[-1]) if not valid.empty else default

            def _latest_nv(col, default=0.0):
                """Latest Non-zero/NaN Value — for demographics that shouldn't disappear."""
                valid = bs[col].dropna()
                non_zero = valid[valid > 0]
                return float(non_zero.iloc[-1]) if not non_zero.empty else float(valid.iloc[-1]) if not valid.empty else default

            def _first(col, default=0.0):
                valid = bs[col].dropna()
                return float(valid.iloc[0]) if not valid.empty else default

            f_jobs_val = _first("Total Jobs")
            c_jobs_val = _latest("Total Jobs")
            n_jobs = int(c_jobs_val - f_jobs_val) if n >= 2 else 0

            f_fem_val = _first("Female Jobs")
            c_fem_val = _latest("Female Jobs")
            n_fem = int(c_fem_val - f_fem_val) if n >= 2 else 0

            c_yth_val = _latest("Youth Jobs")
            j_pct = _calc_pct_change(f_jobs_val, c_jobs_val)

            c_stu = _latest("Total Subscribers Students")
            c_tea = _latest("Total Subscribers Teachers")
            # FIX: sum from valid_bs (actual records only) not bs (padded with ffill/zeros)
            # Padded rows duplicate the last real value, inflating the subscriber count
            _actual = valid_bs if not valid_bs.empty else bs
            v_new_subs = float(_actual["New Subscribers Students"].sum()) + float(_actual["New Subscribers Teachers"].sum())

            prog_total_jobs += int(c_jobs_val)
            prog_new_jobs   += n_jobs
            prog_female_jobs += int(c_fem_val)
            prog_youth_jobs  += int(c_yth_val)
            prog_female_new  += n_fem
            prog_youth_new   += n_fem # Approx
            prog_total_sub   += (c_stu + c_tea)
            prog_new_sub     += v_new_subs
            prog_total_schools += _latest("Total Schools")
            prog_female_stu  += _latest_nv("Female Students")
            prog_total_stu   += c_stu
            prog_rural_stu   += _latest_nv("Rural Students")
            prog_disability_stu += _latest_nv("Disability Students")

            coh_total_jobs += int(c_jobs_val)
            coh_total_learners += int(c_stu)
            coh_total_educators += int(c_tea)

            biz_flags = []
            if isinstance(sg, (int, float)) and sg < 0:   biz_flags.append("Negative Sales Growth ⚠️")
            if isinstance(sg, (int, float)) and sg >= 20:  biz_flags.append("Strong Sales Growth ✨")
            if isinstance(pg, (int, float)) and pg < 0:   biz_flags.append("Negative Profit Growth ⚠️")
            if isinstance(pg, (int, float)) and pg >= 20:  biz_flags.append("Strong Profit Growth ✨")
            if (c_stu + c_tea) > 0 and ((v_new_subs / max(n, 1)) * 12) < 8000: biz_flags.append("Low Learner Reach ⚠️")
            if biz_flags: red_flags.append({"Business Name": biz_name, "Cohort": cohort_name, "Flags": biz_flags})

            venture_data.append({"Business Name": biz_name, "Cohort": cohort_name, "Total Sales (R)": biz_sales, "Sales Growth %": sg, "Profit Growth %": pg, "Latest Jobs": n_jobs, "Jobs Pct Change": j_pct, "Female Jobs": int(c_fem_val), "Youth Jobs": int(c_yth_val), "Total Subscribers": int(c_stu + c_tea), "Months": n})
            growth_table.append({"name": biz_name, "sales_growth": sg, "profit_growth": pg, "months": n, "flags": biz_flags})
            jobs_table.append({"name": biz_name, "total": int(c_jobs_val), "new": n_jobs, "pct_change": j_pct, "new_female": n_fem, "youth": int(c_yth_val)})
            users_table.append({"name": biz_name, "tot_learners": int(c_stu), "tot_educators": int(c_tea), "new_learners": int(float(bs["New Subscribers Students"].sum())), "new_educators": int(float(bs["New Subscribers Teachers"].sum())), "flags": []})
            disagg_table.append({"name": biz_name, "female": int(_latest_nv("Female Students")), "rural": int(_latest_nv("Rural Students")), "disability": int(_latest_nv("Disability Students"))})

            m_str = bs["Date"].dt.strftime("%Y-%m").tolist()
            f_sales.append({"name": biz_name, "growth": sg, "months": n, "data": [{"x": m, "y": _safe_round(v)} for m, v in zip(m_str, bs["Monthly Sales (R)"])]})
            f_profit.append({"name": biz_name, "growth": pg, "months": n, "data": [{"x": m, "y": _safe_round(v)} for m, v in zip(m_str, bs["Monthly Net Profit"])]})
            if not valid_bs.empty:
                vbm = valid_bs.groupby(valid_bs["Date"].dt.strftime("%Y-%m")).agg({"Total Subscribers Students": "sum", "Total Subscribers Teachers": "sum", "New Subscribers Students": "sum", "New Subscribers Teachers": "sum", "SA Schools": "sum", "Q1-3 Schools": "sum", "Total Jobs": "sum", "Female Jobs": "sum", "Youth Jobs": "sum"}).sort_index()
                f_reach.append({"name": biz_name, "months": vbm.index.tolist(), "total_learners": [_safe_round(v) for v in vbm["Total Subscribers Students"]], "total_educators": [_safe_round(v) for v in vbm["Total Subscribers Teachers"]], "new_learners_cum": [_safe_round(v) for v in vbm["New Subscribers Students"].cumsum()], "new_educators_cum": [_safe_round(v) for v in vbm["New Subscribers Teachers"].cumsum()], "sa_schools": [_safe_round(v) for v in vbm["SA Schools"]], "q13_schools": [_safe_round(v) for v in vbm["Q1-3 Schools"]]})
                f_jobs.append({"name": biz_name, "months": vbm.index.tolist(), "total": [_safe_round(v) for v in vbm["Total Jobs"]], "female": [_safe_round(v) for v in vbm["Female Jobs"]], "youth": [_safe_round(v) for v in vbm["Youth Jobs"]]})

            for _, row in bs.iterrows():
                gv = _safe_float(row.get("Grants Value", 0))
                if gv and gv > 0:
                    inv_item = {
                        "name": biz_name,
                        "value": gv,
                        "investor": row.get("Grant Funder") or "Not Specified",
                        "month": row["Date"].strftime("%b %Y") if pd.notna(row.get("Date")) else "N/A"
                    }
                    coh_investments.append(inv_item)
                    investment_ledger.append({
                        "Business Name": biz_name, 
                        "Cohort": cohort_name, 
                        "Total Sales": _safe_float(row.get("Monthly Sales (R)")), 
                        "Net Profit": _safe_float(row.get("Monthly Net Profit")), 
                        "Grants & Investments": gv,
                        "Investor": inv_item["investor"],
                        "Date": inv_item["month"]
                    })
                if pd.notna(row["Date"]): all_time_series.append({"cohort": cohort_name, "month": row["Date"].strftime("%Y-%m"), "sales": _safe_float(row["Monthly Sales (R)"]), "profit": _safe_float(row["Monthly Net Profit"]), "jobs": _safe_float(row["Total Jobs"])})

        med_sg = round(median(coh_sg_list), 1) if coh_sg_list else "Insufficient Data"
        med_pg = round(median(coh_pg_list), 1) if coh_pg_list else "Insufficient Data"
        avg_mo = sum(coh_months_list) / len(coh_months_list) if coh_months_list else 0
        cohort_growth_metrics[cohort_name] = {"median_sg": med_sg, "median_pg": med_pg, "exposure": avg_mo}

        coh_valid = cdf[cdf["Date"].notna()]
        coh_base_j, coh_curr_j = 0, 0
        if not coh_valid.empty:
            for b_name, b_group in coh_valid.groupby("Business Name"):
                tj = b_group.sort_values("Date")["Total Jobs"].dropna()
                if not tj.empty:
                    coh_base_j += tj.iloc[0]
                    coh_curr_j += tj.iloc[-1]
            
            cg_r = coh_valid.groupby("Date")[["Total Subscribers Students", "Total Subscribers Teachers"]].sum().sort_index()
            last_c = cg_r.iloc[-1]
            coh_total_learners = int(last_c["Total Subscribers Students"])
            coh_total_educators = int(last_c["Total Subscribers Teachers"])
            coh_total_jobs = int(coh_curr_j)
        else:
            coh_total_learners = coh_total_educators = coh_total_jobs = 0
            
        coh_jobs_pct = _calc_pct_change(coh_base_j, coh_curr_j)

        cohort_summaries.append({
            "Cohort": cohort_name, "Ventures": len(coh_months_list), "Total Sales": float(cdf["Monthly Sales (R)"].sum()), "Total Profit": float(cdf["Monthly Net Profit"].sum()),
            "Total Jobs": coh_total_jobs,
            "Jobs Pct Change": coh_jobs_pct,
            "Total Learners": coh_total_learners,
            "Total Educators": coh_total_educators,
            "New Learners": int(cdf["New Subscribers Students"].sum()),
            "New Educators": int(cdf["New Subscribers Teachers"].sum()),
            "Median Sales Growth": med_sg, "Median Profit Growth": med_pg
        })

        if padded_cohort_dfs:
            coh_padded_df = pd.concat(padded_cohort_dfs, ignore_index=True)
            cg = coh_padded_df.groupby(coh_padded_df["Date"].dt.strftime("%Y-%m")).agg({"Monthly Sales (R)": "sum", "Monthly Net Profit": "sum", "Total Jobs": "sum", "Female Jobs": "sum", "Youth Jobs": "sum", "Total Subscribers Students": "sum", "Total Subscribers Teachers": "sum", "New Subscribers Students": "sum", "New Subscribers Teachers": "sum", "SA Schools": "sum", "Q1-3 Schools": "sum"}).sort_index()
            cohort_aggregate = {"months": cg.index.tolist(), "sales": [_safe_round(v) for v in cg["Monthly Sales (R)"]], "profit": [_safe_round(v) for v in cg["Monthly Net Profit"]]}
            jobs_bar = {"months": cg.index.tolist(), "total": [_safe_round(v) for v in cg["Total Jobs"]], "female": [_safe_round(v) for v in cg["Female Jobs"]], "youth": [_safe_round(v) for v in cg["Youth Jobs"]]}
            reach = {"months": cg.index.tolist(), "total_learners": [_safe_round(v) for v in cg["Total Subscribers Students"]], "total_educators": [_safe_round(v) for v in cg["Total Subscribers Teachers"]], "new_learners_cum": [_safe_round(v) for v in cg["New Subscribers Students"].cumsum()], "new_educators_cum": [_safe_round(v) for v in cg["New Subscribers Teachers"].cumsum()], "sa_schools": [_safe_round(v) for v in cg["SA Schools"]], "q13_schools": [_safe_round(v) for v in cg["Q1-3 Schools"]]}
        else:
            cohort_aggregate = {"months": [], "sales": [], "profit": []}
            jobs_bar = {"months": [], "total": [], "female": [], "youth": []}
            reach = {"months": [], "total_learners": [], "total_educators": [], "new_learners_cum": [], "new_educators_cum": [], "sa_schools": [], "q13_schools": []}

        cohort_detail[cohort_name] = {
            "cohort_median_sg": med_sg, "cohort_median_pg": med_pg, "cohort_months": int(avg_mo), "cohort_jobs_pct": coh_jobs_pct,
            "jobs_latest_total": coh_total_jobs,   # authoritative: sum of each biz's latest known jobs value
            "fellows_sales": f_sales, "fellows_profit": f_profit, "fellows_reach": f_reach, "fellows_jobs": f_jobs,
            "cohort_aggregate": cohort_aggregate, "growth_table": growth_table, "jobs_bar": jobs_bar, "jobs_table": jobs_table, "investments_table": coh_investments, "reach": reach, "users_table": users_table, "disaggregation": disagg_table
        }

    ts_num = ts_den = tp_num = tp_den = 0.0
    for m in cohort_growth_metrics.values():
        e = m["exposure"]
        if isinstance(m["median_sg"], (int, float)): ts_num += m["median_sg"] * e; ts_den += e
        if isinstance(m["median_pg"], (int, float)): tp_num += m["median_pg"] * e; tp_den += e
    prog_sg_twa = round(ts_num / ts_den, 1) if ts_den > 0 else "Insufficient Data"
    prog_pg_twa = round(tp_num / tp_den, 1) if tp_den > 0 else "Insufficient Data"

    prog_base_j, prog_curr_j = 0, 0
    df_valid_final = df[df["Date"].notna()]
    if not df_valid_final.empty:
        for b_name, b_group in df_valid_final.groupby("Business Name"):
            tj = b_group.sort_values("Date")["Total Jobs"].dropna()
            if not tj.empty:
                prog_base_j += tj.iloc[0]
                prog_curr_j += tj.iloc[-1]
        
        pr_r = df_valid_final.groupby("Date")[["Total Subscribers Students", "Total Subscribers Teachers", "Total Schools"]].sum().sort_index()
        last_pr = pr_r.iloc[-1]
        prog_total_sub = int(last_pr["Total Subscribers Students"] + last_pr["Total Subscribers Teachers"])
        prog_total_schools = int(last_pr["Total Schools"]) if "Total Schools" in last_pr else 0
        prog_total_jobs = int(prog_curr_j)
        
    prog_jobs_pct = _calc_pct_change(prog_base_j, prog_curr_j)

    return {
        "Program_Overview": {"Total_Sales_ZAR": int(grand_total_sales or 0), "Net_Jobs_Created": int(prog_new_jobs or 0), "Average_Sales_Growth_%": prog_sg_twa, "Average_Profit_Growth_%": prog_pg_twa, "Total_Ventures": int(df["Business Name"].nunique()), "Program_TWA": prog_sg_twa},
        "Venture_Data": venture_data, "Cohort_Summaries": cohort_summaries, "Investment_Ledger": investment_ledger, "Jobs_Summary": {"Total Jobs": int(prog_total_jobs or 0), "New Jobs": int(prog_new_jobs or 0), "Jobs Pct Change": prog_jobs_pct, "Female Jobs": int(prog_female_jobs or 0), "Youth Jobs": int(prog_youth_jobs or 0), "New Female Jobs": int(prog_female_new or 0), "New Youth Jobs": int(prog_youth_new or 0)}, "Reach_Summary": {"Total Subscribers": int(prog_total_sub or 0), "New Subscribers": int(prog_new_sub or 0), "Total Schools": int(prog_total_schools or 0), "Female %": round((prog_female_stu / prog_total_stu) * 100, 1) if prog_total_stu else 0, "Rural %": round((prog_rural_stu / prog_total_stu) * 100, 1) if prog_total_stu else 0, "Disability %": round((prog_disability_stu / prog_total_stu) * 100, 1) if prog_total_stu else 0}, "Time_Series": {"cohort": {}, "program": {}, "program_extended": program_series}, "Red_Flags": red_flags, "Cohort_Detail": cohort_detail
    }

def _empty_cohort_detail():
    return {"cohort_median_sg": "Insufficient Data", "cohort_median_pg": "Insufficient Data", "cohort_months": 0, "fellows_sales": [], "fellows_profit": [], "fellows_reach": [], "fellows_jobs": [], "cohort_aggregate": {"months": [], "sales": [], "profit": []}, "growth_table": [], "jobs_bar": {"months": [], "total": [], "female": [], "youth": []}, "jobs_table": [], "investments_table": [], "reach": {"months": [], "total_learners": [], "total_educators": [], "new_learners_cum": [], "new_educators_cum": [], "sa_schools": [], "q13_schools": []}, "users_table": [], "disaggregation": []}

if __name__ == "__main__":
    from data_fetcher import fetch_dashboard_data
    print("Fetching …")
    raw = fetch_dashboard_data()
    print("\nCalculating KPIs …")
    result = calculate_kpis(raw)
    ov = result["Program_Overview"]
    print(f"\n--- Program Overview ---")
    print(f"  Ventures:      {ov['Total_Ventures']}")
    print(f"  Sales Growth:  {ov['Average_Sales_Growth_%']}")
    print(f"  Profit Growth: {ov['Average_Profit_Growth_%']}")
    print(f"  Net Jobs:      {ov['Net_Jobs_Created']}")
    print(f"  Program TWA:   {ov['Program_TWA']}")
    print(f"\n--- Cohort Summaries ---")
    for cs in result["Cohort_Summaries"]:
        print(f"  {cs['Cohort']}: {cs['Ventures']} ventures, SG={cs['Median Sales Growth']}, PG={cs['Median Profit Growth']}")
