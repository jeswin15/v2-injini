import data_fetcher
import logic_engine
import pandas as pd
import warnings

warnings.filterwarnings('ignore')

try:
    print("Fetching Data from Airtable...")
    df = data_fetcher.fetch_dashboard_data()
    
    try:
        df.to_excel("Raw_Airtable_Extract.xlsx", index=False)
        print("Saved Raw_Airtable_Extract.xlsx")
    except Exception as e:
        df.to_csv("Raw_Airtable_Extract.csv", index=False)
        print("Saved Raw_Airtable_Extract.csv (Fallback to CSV)")

    res = logic_engine.calculate_kpis(df)

    rows = []
    for cohort in ["Cohort 1", "Cohort 2", "Cohort 3", "Cohort 4"]:
        cd = res["Cohort_Detail"].get(cohort, {})
        growths = {r["name"]: {"sales": r["sales_growth"], "profit": r["profit_growth"]} for r in cd.get("growth_table", [])}
        
        for row in cd.get("jobs_table", []):
            name = row["name"]
            sg = growths.get(name, {}).get("sales", "N/A")
            pg = growths.get(name, {}).get("profit", "N/A")
            rows.append({
                "Cohort": cohort,
                "Business Name": name,
                "Sales Growth %": sg,
                "Profit Growth %": pg,
                "Baseline Jobs": row["total"] - row["new"],
                "Current Jobs": row["total"],
                "New Jobs": row["new"],
                "Jobs Growth %": row["pct_change"]
            })

    out_df = pd.DataFrame(rows)
    try:
        out_df.to_excel("Processed_Dashboard_Audit.xlsx", index=False)
        print("Saved Processed_Dashboard_Audit.xlsx")
    except:
        out_df.to_csv("Processed_Dashboard_Audit.csv", index=False)
        print("Saved Processed_Dashboard_Audit.csv (Fallback to CSV)")

except Exception as e:
    print(f"Error during export: {e}")
