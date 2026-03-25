
import pandas as pd
from logic_engine import calculate_kpis, _empty_cohort_detail
from jinja2 import Environment, FileSystemLoader
import os

# 1. Setup Jinja2
env = Environment(loader=FileSystemLoader('templates'))

# Mocking _safe_json and DotDict as they are in app.py
class DotDict(dict):
    def __getattr__(self, key):
        try: return self[key]
        except KeyError: raise AttributeError(key)

def _safe_json(data): return "MOCK_JSON"

template = env.get_template('dashboard.html')

# 2. Test Empty Cohort Detail
print("Testing empty cohort detail...")
empty_cd = _empty_cohort_detail()
# Ensure jobs_table and disaggregation be empty lists
empty_cd['jobs_table'] = []
empty_cd['disaggregation'] = []

kpi_data = {
    'Program_Overview': {
        'Total_Sales_ZAR': 0, 'Net_Jobs_Created': 0,
        'Average_Sales_Growth_%': 0, 'Average_Profit_Growth_%': 0,
        'Total_Ventures': 0
    },
    'Venture_Data': [],
    'Cohort_Summaries': [],
    'Investment_Ledger': [],
    'Jobs_Summary': {
        'Total Jobs': 0, 'New Jobs': 0, 'Jobs Pct Change': 0,
        'Female Jobs': 0, 'Youth Jobs': 0, 'New Female Jobs': 0, 'New Youth Jobs': 0
    },
    'Reach_Summary': {
        'Total Subscribers': 0, 'Total Learners': 0, 'Total Educators': 0,
        'New Subscribers': 0, 'Total Schools': 0
    },
    'Time_Series': [],
    'Cohort_Detail': {
        'Cohort 1': empty_cd,
        'Cohort 2': empty_cd,
        'Cohort 3': empty_cd,
        'Cohort 4': empty_cd,
    },
    'Red_Flags': []
}

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
        current_range="all"
    )
    print("  Empty Render SUCCESS")
except Exception as e:
    print(f"  Empty Render FAILED: {e}")
    import traceback
    traceback.print_exc()
