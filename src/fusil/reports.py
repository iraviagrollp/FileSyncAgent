# All 7 report definitions — menu paths confirmed from flows/Navigations/Fusil navigations.xlsx.
# Note: Customer Accounts navigates via "Masters" (not "Reports").
# Note: Purchase Returns path was a typo in the source spreadsheet; corrected from the actual filename.

REPORTS = [
    {
        "type": "sale",
        "menu_path": ["Reports", "RGF", "Sales", "RGF Sales Book"],
    },
    {
        "type": "sale_returns",
        "menu_path": ["Reports", "RGF", "Sales", "RGF Sales Return Book"],
    },
    {
        "type": "purchase",
        "menu_path": ["Reports", "RGF", "Purchase", "RGF Purchase Book"],
    },
    {
        "type": "purchase_returns",
        "menu_path": ["Reports", "RGF", "Purchase", "RGF Purchase Return Book"],
    },
    {
        "type": "stocks",
        "menu_path": ["Reports", "RGF", "Stock Reports", "RGF Current Stock Balances"],
    },
    {
        "type": "customer_balances",
        "menu_path": ["Reports", "FI Finance", "Balance", "Customer Balances"],
    },
    {
        "type": "customer_accounts",
        "menu_path": ["Masters", "General", "Customer Accounts"],
    },
]

# Leading prefix of each exported filename — used to locate the file after export.
# Match by prefix and take the most-recently-modified .xlsx in the export folder.
FILENAME_PREFIX = {
    "sale":              "RGF Sales Book",
    "sale_returns":      "RGF Sales Return Book",
    "purchase":          "RGF Purchase Book",
    "purchase_returns":  "RGF Purchase Return Book",
    "stocks":            "RGF Current Stock Balances",
    "customer_accounts": "Customer Accounts Export File",
    "customer_balances": "Customer Balances",
}
