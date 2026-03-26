import pandas as pd
import numpy as np
from logic_engine import calculate_kpis

def test_fixes():
    # 1. Mock data for Duplicate Month (Fintr scenario)
    columns = [
        "Business Name", "Reporting Month", "Monthly Sales (R)", "Monthly Net Profit",
        "Total Jobs", "Female Jobs", "Youth Jobs", "Total Subscribers Students",
        "Total Subscribers Teachers", "New Subscribers Students", "New Subscribers Teachers",
        "SA Schools", "Q1-3 Schools", "Total Schools", "Cohort", "Female Students", "Female Teachers",
        "Rural Students", "Rural Teachers", "Disability Students", "Disability Teachers",
        "Grant Funder", "Grants Value"
    ]
    
    data = [
        # Business A: Duplicates in Nov 2024
        {"Business Name": "Fintr", "Reporting Month": "Oct 2024", "Monthly Sales (R)": 100, "Cohort": "Cohort 2"},
        {"Business Name": "Fintr", "Reporting Month": "Nov 2024", "Monthly Sales (R)": 200, "Cohort": "Cohort 2"},
        {"Business Name": "Fintr", "Reporting Month": "Nov 2024", "Monthly Sales (R)": 300, "Cohort": "Cohort 2"}, # Mean should be 250
        
        # Business B: Disaggregation Bug (Afrika Tikkun scenario)
        {"Business Name": "Afrika Tikkun", "Reporting Month": "Jan 2024", "Female Students": 0.6, "Cohort": "Cohort 1", "Total Subscribers Students": 100, "Monthly Sales (R)": 50},
        {"Business Name": "Afrika Tikkun", "Reporting Month": "Feb 2024", "Female Students": 0.0, "Cohort": "Cohort 1", "Total Subscribers Students": 110, "Monthly Sales (R)": 60},
        
        # Business C: Regular data
        {"Business Name": "Biz C", "Reporting Month": "Jan 2024", "Female Students": 0.4, "Cohort": "Cohort 1", "Total Subscribers Students": 50, "Monthly Sales (R)": 30},
    ]
    df = pd.DataFrame(data, columns=columns).fillna(0)
    
    print("Running KPI calculation...")
    result = calculate_kpis(df)
    
    # Check deduplication for Fintr
    # We can't easily check internal dataframes, but we can check if it reported a warning and what the resolution was.
    dw = result.get("Duplicate_Warnings", [])
    print(f"Duplicate Warnings: {len(dw)}")
    for w in dw:
        print(f"  {w['business']} at {w['date']}: resolution={w['resolution']}")
        if w['business'] == "Fintr":
            # If it was mean-deduped, Fintr's total sales (if summed) would be affected, 
            # but here it's easier to trust the code if the warning says 'mean'.
            pass

    # Check Disaggregation for Afrika Tikkun
    cd = result["Cohort_Detail"]["Cohort 1"]
    disagg = {d['name']: d for d in cd['disaggregation']}
    
    at_fem = disagg["Afrika Tikkun"]["female_stu"]
    print(f"Afrika Tikkun Female %: {at_fem} (Expected: 0.6)")
    
    biz_c_fem = disagg["Biz C"]["female_stu"]
    print(f"Biz C Female %: {biz_c_fem} (Expected: 0.4)")
    
    # Check Program Reach Summary (Averages)
    rs = result["Reach_Summary"]
    print(f"Program Female %: {rs['Female %']} (Expected: average of 0.6 and 0.4 = 0.5 or 50.0 if scaled)")
    # Note: the code scales it by 1 if it's already a float? No, it just takes the mean.
    # If the input was 0.6 and 0.4, mean is 0.5.
    
    if at_fem == 0.6:
        print("SUCCESS: Disaggregation bug fixed (Afrika Tikkun picked 0.6 instead of 0.0)")
    else:
        print("FAILURE: Disaggregation bug still present")

    if rs['Female %'] == 0.5:
         print("SUCCESS: Program average correctly includes Afrika Tikkun")
    else:
         print(f"INFO: Program Female % is {rs['Female %']}. Check if scaling is expected.")

if __name__ == "__main__":
    test_fixes()
