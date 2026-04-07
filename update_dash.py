import os

log_path = r"C:\Users\ELCOT\.gemini\antigravity\brain\b41f9a99-b493-48a0-a774-dd1892bdc05b\.system_generated\logs\overview.txt"
dest_path = r"c:\Users\ELCOT\Downloads\injini-mel-dashboard-main\injini-mel-dashboard-main\templates\dashboard.html"

with open(log_path, 'r', encoding='utf-8') as f:
    text = f.read()

requests = text.split("<USER_REQUEST>")
for req in reversed(requests):
    if "<!DOCTYPE html>" in req and "this the updated codde" in req:
        start = req.find("<!DOCTYPE html>")
        # The user's text ends with "this the updated codde for dashboard update this and run in local host"
        end_marker = "this the updated codde"
        end = req.find(end_marker, start)
        if end == -1:
            end = len(req)
        
        html_content = req[start:end].strip()
        
        with open(dest_path, 'w', encoding='utf-8') as out:
            out.write(html_content)
        print(f"Successfully updated dashboard.html, length: {len(html_content)}")
        break
else:
    print("Could not find the HTML content in the logs.")
