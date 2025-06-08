
from email_handler import download_latest_sales_report

result = download_latest_sales_report()

if result:
    print("✅ File downloaded:")
    print("Path:", result["path"])
    print("Name:", result["filename"])
    print("Date:", result["date"])
else:
    print("❌ No sales report found.")
