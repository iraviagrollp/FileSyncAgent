# All 7 report definitions — menu paths confirmed from flows/Navigations/Fusil navigations.xlsx.
#
# date_mode:   "from_to"  — set both From Date and To Date
#              "as_at"    — set single "As At Date" field (Customer Balances)
#              "none"     — no date fields on this screen (Stocks, Customer Accounts)
#
# view_mode:   "f1"       — click View (F1) to load data (standard)
#              "auto"     — data loads automatically on navigation (Customer Accounts)
#
# export_key:  pywinauto send_keys string for the export shortcut
#              "^x" = Ctrl+X (standard), "^o" = Ctrl+O (Customer Accounts)

REPORTS = [
    {
        "type":       "sale",
        "menu_path":  ["Reports", "RGF", "Sales", "RGF Sales Book"],
        "date_mode":  "from_to",
        "view_mode":  "f1",
        "export_key": "^x",
    },
    {
        "type":       "sale_returns",
        "menu_path":  ["Reports", "RGF", "Sales", "RGF Sales Return Book"],
        "date_mode":  "from_to",
        "view_mode":  "f1",
        "export_key": "^x",
    },
    {
        "type":       "purchase",
        "menu_path":  ["Reports", "RGF", "Purchase", "RGF Purchase Book"],
        "date_mode":  "from_to",
        "view_mode":  "f1",
        "export_key": "^x",
    },
    {
        "type":       "purchase_returns",
        "menu_path":  ["Reports", "RGF", "Purchase", "RGF Purchase Return Book"],
        "date_mode":  "from_to",
        "view_mode":  "f1",
        "export_key": "^x",
    },
    {
        "type":       "stocks",
        "menu_path":  ["Reports", "RGF", "Stock Reports", "RGF Current Stock Balances"],
        "date_mode":  "none",
        "view_mode":  "f1",
        "export_key": "^x",
    },
    {
        "type":       "customer_balances",
        "menu_path":  ["Reports", "FI Finance", "Balances", "Customer Balances"],
        "date_mode":  "as_at",
        "view_mode":  "f1",
        "export_key": "^x",
    },
    {
        "type":       "customer_accounts",
        "menu_path":  ["Masters", "General", "Customer Accounts"],
        "date_mode":  "none",
        "view_mode":  "auto",   # list loads on navigation; no View button
        "export_key": "^o",     # Ctrl+O, not Ctrl+X
    },
]

# Human-readable display names for the summary table
REPORT_DISPLAY_NAME = {
    "sale":              "Sales",
    "sale_returns":      "Sales Returns",
    "purchase":          "Purchases",
    "purchase_returns":  "Purchase Returns",
    "stocks":            "Current Stock Balances",
    "customer_balances": "Customer Balances",
    "customer_accounts": "Customer Accounts",
}

# Leading prefix of each exported filename — used to locate the file after export.
FILENAME_PREFIX = {
    "sale":              "RGF Sales Book",
    "sale_returns":      "RGF Sales Return Book",
    "purchase":          "RGF Purchase Book",
    "purchase_returns":  "RGF Purchase Return Book",
    "stocks":            "RGF Current Stock Balances",
    "customer_accounts": "Customer Accounts Export File",
    "customer_balances": "Customer Balances",
}
