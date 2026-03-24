import data_fetcher
import logic_engine

try:
    print("Fetching data from Airtable...")
    df = data_fetcher.fetch_dashboard_data()
    print("Processing mathematical rules strictly...")
    res = logic_engine.calculate_kpis(df)

    c1 = next((c for c in res["Cohort_Summaries"] if c["Cohort"] == "Cohort 1"), None)
    c1_details = res["Cohort_Detail"].get("Cohort 1", {})
    c1_new_jobs = sum(j["new"] for j in c1_details.get("jobs_table", []))

    prog = res["Program_Overview"]
    jobs = res["Jobs_Summary"]
    reach = res["Reach_Summary"]

    print("\n=====================================================")
    print("OUTPUT REQUIREMENTS (STRICT EXCEL SPECIFICATION)")
    print("=====================================================\n")

    print("[ COHORT 1 ]")
    if c1:
        print(f"Sales Growth % (cohort median) : {c1.get('Median Sales Growth')}")
        print(f"Profit Growth % (cohort median): {c1.get('Median Profit Growth')}")
        print(f"Total Jobs (current)           : {c1.get('Total Jobs')}")
        print(f"New Jobs                       : {c1_new_jobs}")
        print(f"Jobs Growth %                  : {c1.get('Jobs Pct Change')}%")
    else:
        print("Cohort 1 data not found.")

    print("\n[ PROGRAMME OVERVIEW ]")
    print(f"Total Jobs (current)           : {jobs.get('Total Jobs')}")
    print(f"New Jobs                       : {jobs.get('New Jobs')}")
    print(f"Jobs Growth %                  : {jobs.get('Jobs Pct Change')}%")
    print(f"Total Subscribers (Active)     : {reach.get('Total Subscribers')}")
    print(f"Cumulative Subscribers (New)   : {reach.get('New Subscribers')}")
    print(f"Total Schools                  : {reach.get('Total Schools')}")
    print(f"Programme TWA (Sales)          : {prog.get('Average_Sales_Growth_%')}")
    print(f"Programme TWA (Profit)         : {prog.get('Average_Profit_Growth_%')}")

except Exception as e:
    print(f"Error: {e}")
