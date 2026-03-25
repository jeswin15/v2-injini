
import pandas as pd
from logic_engine import calculate_kpis
from jinja2 import Environment, FileSystemLoader
import os

# 1. Load data
raw = pd.read_excel("Raw_Airtable_Extract.xlsx")

# 2. Calculate KPIs (simulate all ranges)
for r in ["all", "6", "12", "ytd"]:
    print(f"Testing range: {r}")
    kpi_data = calculate_kpis(raw, time_range=r)
    
    for cname, cd in kpi_data['Cohort_Detail'].items():
        jt = cd.get('jobs_table', [])
        if jt:
            print(f"  {cname} jobs_table[0] keys: {list(jt[0].keys())}")
        else:
            print(f"  {cname} jobs_table is empty")

    # 3. Setup Jinja2
    env = Environment(loader=FileSystemLoader('templates'))
    
    # Mocking _safe_json and DotDict as they are in app.py
    class DotDict(dict):
        def __getattr__(self, key):
            try: return self[key]
            except KeyError: raise AttributeError(key)

    def _safe_json(data): return "MOCK_JSON"

    template = env.get_template('dashboard.html')
    
    try:
        html = template.render(
            kpis=DotDict(
                Program_Overview=DotDict(kpi_data['Program_Overview']),
                Venture_Data=kpi_data['Venture_Data'],
            ),
            cohort_summaries=kpi_data['Cohort_Summaries'],
            investment_ledger=kpi_data['Investment_Ledger'],
            jobs_summary=kpi_data['Jobs_Summary'],
            reach_summary=kpi_data['Reach_Summary'],
            time_series_json="[]",
            red_flags=kpi_data['Red_Flags'],
            cohort_detail=kpi_data['Cohort_Detail'],
            cohort_detail_json="{}",
            current_range=r
        )
        print(f"  Range {r}: Render SUCCESS")
    except Exception as e:
        print(f"  Range {r}: Render FAILED: {e}")
        import traceback
        traceback.print_exc()
