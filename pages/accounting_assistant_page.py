import streamlit as st
import pandas as pd
import os
from pathlib import Path
import fitz  # PyMuPDF
import google.generativeai as genai
import re # New import for regex
import json
import io # New import for in-memory file operations

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Constants
LEARNED_RULES_PATH = "learned_rules.json"
JOURNAL_RULES_PATH = "journal_rules.json"

# GAAP Category Mapping
GAAP_CATEGORY_MAPPING = {
    "Revenue": [
        "Revenue - Gaming - Slots",
        "Revenue - POS - Credit Card",
        "Revenue - Delivery - Grubhub",
        "Revenue - Delivery - UberEats",
        "Revenue - Delivery - DoorDash",
        "Revenue - General - In-Store"
    ],
    "Cost of Goods Sold": [
        "Cost of Goods Sold - Food Vendor - Sysco",
        "Cost of Goods Sold - Packaging - Greco",
        "Cost of Goods Sold - Beverages",
        "Cost of Goods Sold - Alcohol"
    ],
    "Gross Profit": [], # Calculated
    "Operating Expenses - Payroll": [
        "Payroll - Manual Check - Hourly",
        "Payroll - ADP - Salaried"
    ],
    "Operating Expenses - Utilities": [
        "Utilities - Electric - Ameren",
        "Utilities - Gas Service",
        "Utilities - Water - American Water"
    ],
    "Operating Expenses - Facilities": [
        "Facilities - Rent - Real Estate",
        "Facilities - Waste Disposal - Contracted",
        "Facilities - Waste Disposal - LRS", # Added
        "Facilities - Security - ADT" # Added
    ],
    "Operating Expenses - Marketing": [
        "Marketing - Digital - Facebook Ads",
        "Marketing - Digital - General",
        "Marketing - Print - Graphics Vendor",
        "Marketing - Print - Materials",
        "Marketing - Social Media - Social Page Solutions",
        "Marketing - Call Tracking - CallForce"
    ],
    "Operating Expenses - Merchant Fees": [
        "Merchant Fees - Rewards Network",
        "Merchant Fees - EBF Holdings",
        "Merchant Fees - Shift4",
        "Merchant Fees - Nexus" # Added
    ],
    "Operating Expenses - Bank Fees": [
        "Bank Fees - ATM Withdrawal",
        "Bank Fees - Miscellaneous - Service Charge",
        "Bank Fees - Miscellaneous",
        "Bank Fees - Miscellaneous - ACH Transfer", # Added for transfers
        "Bank Fees - Stop Payment" # Added for stop payment fee
    ],
    "Operating Expenses - Accounting": [ # New category
        "Accounting - Bookkeeping Services"
    ],
    "Operating Expenses - Technology": [ # New category
        "Technology - POS Hardware - Ziosk",
        "Technology - POS Software - Arrow",
        "Technology - Loyalty Platform - Paytronix"
    ],
    "Operating Expenses - Shipping": [ # New category
        "Shipping - Freight - Beelman"
    ],
    "Operating Expenses - Janitorial": [ # New category
        "Janitorial - Cleaning Services",
        "Janitorial - Sanitation Vendor - PHS"
    ],
    "Operating Expenses - Insurance": [ # New category
        "Insurance - General Liability"
    ],
    "Operating Expenses - Fuel & Travel": [ # New category
        "Fuel - Travel Expenses"
    ],
    "Operating Expenses - Corporate Allocation": [ # New category
        "Corporate Allocation - Overhead G&A"
    ],
    "Operating Expenses - Other": [ # New category for remaining
        "Banking - Debit Transaction", # Moved here
        "Banking - Other Income", # Keep if needed for balance, otherwise remove or re-categorize
        "Meals & Entertainment - Staff Food", # Add if it's an expense
        "Promotional Supplies - Graduation Merchandise" # Add if it's an expense
    ],
    "Net Operating Income": [] # Calculated
}

# Vendor to category mappings
VENDOR_CATEGORIES = {
    "greco": "Cost of Goods Sold",
    "american water": "Utilities",
    "waste management": "Trash Removal",
    "w/d svc": "Bank/Service Fees",
    "prairie state": "Gaming Revenue",
    "shift4": "Revenue"  # Adding Shift4 here as well for consistency
}

# P&L Line Item Definitions and their corresponding detailed categories
P_AND_L_STRUCTURE = [
    {"Category": "Revenues", "Type": "Header"},
    {"Category": "Cash sales", "Map": ["Revenue - General - In-Store"], "Type": "Value", "Indent": 1},
    {"Category": "Credit sales", "Map": ["Revenue - POS - Credit Card", "Revenue - Delivery - Grubhub", "Revenue - Delivery - UberEats", "Revenue - Delivery - DoorDash", "Revenue - Gaming - Slots", "Revenue - Credit Card Reimbursement"], "Type": "Value", "Indent": 1},
    {"Category": "Total Revenue", "Formula": "SUM(B{cash_sales_row}:B{credit_sales_row})", "Type": "Calculated", "Indent": 0},
    {"Category": "Cost of goods sold", "Type": "Header"},
    {"Category": "Cost of goods sold", "Map": ["Cost of Goods Sold - Food Vendor - Sysco", "Cost of Goods Sold - Packaging - Greco", "Cost of Goods Sold - Beverages", "Cost of Goods Sold - Alcohol", "COGS - Beverage Vendor - Breakthru", "COGS - Food Vendor - Fivestar", "COGS - CO2 Supplier - NuCO2", "COGS - Beverage Vendor - Koerner", "COGS - Alcohol Vendor - Southern Glazer", "COGS - Beverage Vendor - Stokes", "COGS - Supplies - Webstaurant Store"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Gross profit", "Formula": "B{total_revenue_row}-B{cogs_row}", "Type": "Calculated", "Indent": 0, "Bolding": True},

    {"Category": "Operating expenses", "Type": "Header"},
    {"Category": "Salaries", "Map": ["Payroll - Manual Check - Hourly", "Payroll - ADP - Salaried"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Advertising", "Map": ["Marketing - Digital - Facebook Ads", "Marketing - Digital - General", "Marketing - Print - Graphics Vendor", "Marketing - Print - Materials", "Marketing - Social Media - Social Page Solutions", "Marketing - Call Tracking - CallForce"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Office rent", "Map": ["Facilities - Rent - Real Estate"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Utilities", "Map": ["Utilities - Electric - Ameren", "Utilities - Gas Service", "Utilities - Water - American Water"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Office Supplies", "Map": [], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Depreciation", "Map": [], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Merchant Fees - Rewards Network", "Map": ["Merchant Fees - Rewards Network"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Merchant Fees - Shift4", "Map": ["Merchant Fees - Shift4"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Merchant Fees - Nexus", "Map": ["Merchant Fees - Nexus"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Bank Fees - ATM Withdrawal", "Map": ["Bank Fees - ATM Withdrawal"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Bank Fees - Misc. Service Charge", "Map": ["Bank Fees - Miscellaneous - Service Charge", "Bank Fees - Miscellaneous", "Bank Fees - Miscellaneous - ACH Transfer", "Bank Fees - Stop Payment"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Accounting - Bookkeeping Services", "Map": ["Accounting - Bookkeeping Services"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Technology - POS Hardware - Ziosk", "Map": ["Technology - POS Hardware - Ziosk"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Technology - POS Software - Arrow", "Map": ["Technology - POS Software - Arrow"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Technology - Loyalty Platform - Paytronix", "Map": ["Technology - Loyalty Platform - Paytronix"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Shipping - Freight - Beelman", "Map": ["Shipping - Freight - Beelman"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Janitorial - Cleaning Services", "Map": ["Janitorial - Cleaning Services"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Janitorial - Sanitation Vendor - PHS", "Map": ["Janitorial - Sanitation Vendor - PHS"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Insurance - General Liability", "Map": ["Insurance - General Liability"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Fuel - Travel Expenses", "Map": ["Fuel - Travel Expenses"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Corporate Allocation - Overhead G&A", "Map": ["Corporate Allocation - Overhead G&A"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Facilities - Waste Disposal - LRS", "Map": ["Facilities - Waste Disposal - LRS"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Meals & Entertainment - Staff Food", "Map": ["Meals & Entertainment - Staff Food"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Promotional Supplies - Graduation Merchandise", "Map": ["Promotional Supplies - Graduation Merchandise"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Banking - Debit Transaction", "Map": ["Banking - Debit Transaction"], "Type": "Value", "IsExpense": True, "Indent": 1}, # Now explicitly an expense line

    {"Category": "Total operating expenses", "Formula": "SUM(B{salaries_row}:B{banking_debit_transaction_row})", "Type": "Calculated", "Indent": 0},
    {"Category": "Operating profit", "Formula": "B{gross_profit_row}-B{total_opex_row}", "Type": "Calculated", "Indent": 0, "Bolding": True},

    {"Category": "Other Income/Expenses", "Type": "Header"},
    {"Category": "Interest Income", "Map": [], "Type": "Value", "Indent": 1},
    {"Category": "Interest expenses", "Map": [], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Banking - Loan Payment - EBF", "Map": ["Banking - Loan Payment - EBF"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Net Income before Tax", "Formula": "B{operating_profit_row}+B{interest_income_row}-B{interest_expenses_row}-B{ebf_loan_payment_row}", "Type": "Calculated", "Indent": 0, "Bolding": True},
    {"Category": "Income tax expenses", "Map": ["Tax - State Withholding Payment"], "Type": "Value", "IsExpense": True, "Indent": 1},
    {"Category": "Net Income after Tax", "Formula": "B{net_income_before_tax_row}-B{income_tax_expenses_row}", "Type": "Calculated", "Indent": 0, "Bolding": True},
]

# Hardcoded overrides for specific vendors and patterns
hardcoded_overrides = {
    # Merchant fees
    'rewards network': 'Merchant Fees - Rewards Network',
    
    # COGS - Alcohol
    'robert chick fritz': 'COGS - Alcohol',
    'southern': 'COGS - Alcohol',
    'breakthru': 'COGS - Alcohol',
    'stokes': 'COGS - Alcohol',
    
    # COGS - Supplies and Beverages
    'webstaurant': 'COGS - Supplies - Webstaurant Store',
    'koerner distribut': 'COGS - Beverage Vendor - Koerner',
    'nuco2': 'COGS - CO2 Supplier - NuCO2',
    
    # Janitorial and Sanitation
    'auto chlor': 'Janitorial - Sanitation Supplies - AutoChlor',
    'clean ar': 'Janitorial - Contracted - Clean AR',
    'phs enterprises': 'Janitorial - Sanitation Vendor - PHS',
    
    # Banking and Returns
    'repeat return': 'Banking - Returned Payment - NSF',
    'od return item credit': 'Banking - Returned Payment - NSF',
    'ebf holdings': 'Banking - Loan Payment - EBF',
    
    # Maintenance and Hardware
    'pace true value': 'Maintenance - Hardware - Pace True Value',
    
    # Marketing and Technology
    'call force': 'Marketing - Call Tracking - CallForce',
    'paytronix': 'Technology - Loyalty Platform - Paytronix',
    'arrow pos': 'Technology - POS Software - Arrow',
    'social page': 'Marketing - Social Media - Social Page Solutions',
    
    # Professional Services
    'accurate account': 'Accounting - Bookkeeping Services',
    
    # Utilities and Insurance
    'illinois-america': 'Utilities - Water - American Water',
    'liberty mutual': 'Insurance - General Liability',
    
    # Taxes and Government
    'il dept of revenu': 'Tax - State Withholding Payment',
    
    # Payroll
    'robert chick': 'Payroll - Manual Check - Hourly',
    
    # Promotional
    'herff jones': 'Promotional Supplies - Graduation Merchandise',
    
    # Meals & Entertainment
    'tacos el manantial': 'Meals & Entertainment - Staff Food',
    
    # Check number patterns
    r'check(?:\s*#)?\s*(\d+)': 'Payroll - Manual Check - Hourly'
}

def load_learned_rules():
    try:
        with open(LEARNED_RULES_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_learned_rules(rules):
    with open(LEARNED_RULES_PATH, "w") as f:
        json.dump(rules, f, indent=2)

def load_journal_rules():
    try:
        with open(JOURNAL_RULES_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def hardcoded_overrides(description, amount, check_number=None):
    desc = str(description).lower()
    is_credit = amount > 0 if isinstance(amount, (int, float)) else False

    # Very specific vendor/description matches (highest precedence)
    if "ebf holdings" in desc:
        return "Banking - Loan Payment - EBF"
    if "rewards network settlement" in desc and is_credit:
        return "Revenue - Credit Card Reimbursement"
    if "rewards network" in desc: # For debit rewards network
        return "Merchant Fees - Rewards Network"
    if "breakthru bevera" in desc:
        return "COGS - Beverage Vendor - Breakthru"
    if "lrs sanitation" in desc:
        return "Facilities - Waste Disposal - LRS"
    if "accurate account" in desc:
        return "Accounting - Bookkeeping Services"
    if "fivestar coop" in desc:
        return "COGS - Food Vendor - Fivestar"
    if "ziosk llc" in desc:
        return "Technology - POS Hardware - Ziosk"
    if "state of illinois il dept of revenue" in desc or "il dept of revenu" in desc:
        return "Tax - State Withholding Payment"
    if "nexus payments" in desc:
        return "Merchant Fees - Nexus"
    if "beelman logistics" in desc:
        return "Shipping - Freight - Beelman"
    if "call force" in desc:
        return "Marketing - Call Tracking - CallForce"
    if "southern glazer" in desc:
        return "COGS - Alcohol Vendor - Southern Glazer"
    if "paytronix" in desc:
        return "Technology - Loyalty Program - Paytronix"
    if "clean ar" in desc:
        return "Janitorial - Cleaning Services"
    if "arrow pos" in desc:
        return "Technology - POS Software - Arrow"
    if "adt security" in desc:
        return "Facilities - Security - ADT"
    if "social page" in desc:
        return "Marketing - Social Media - Social Page Solutions"
    if "nuco2" in desc:
        return "COGS - CO2 Vendor - NuCO2"
    if "koerner distribut" in desc:
        return "COGS - Beverage Vendor - Koerner"
    if "phs enterprises" in desc:
        return "Janitorial - Sanitation Vendor - PHS"
    if "stop payment fee" in desc:
        return "Banking - Returned Payment - Stop Payment"
    if "pos deb card# 1567" in desc:
        return "Fuel - Travel Expenses"
    if "pbg - g&a" in desc:
        return "Corporate Allocation - Overhead G&A"
    if "stokes distribut" in desc:
        return "COGS - Beverage Vendor - Stokes"
    if "eft ach account" in desc:
        return "Banking - Automated Clearing House (ACH) Transfer"
    if "atm w/d" in desc:
        return "Bank Fees - ATM Withdrawal"
    if "webstaurant" in desc:
        return "COGS - Supplies - Webstaurant Store"
    if "auto chlor" in desc:
        return "Janitorial - Sanitation Supplies - AutoChlor"
    if "repeat return" in desc:
        return "Banking - Returned Payment - NSF"
    if "od return item credit" in desc:
        return "Banking - Returned Payment - NSF"
    if "pace true value" in desc:
        return "Maintenance - Hardware - Pace True Value"
    if "herff jones" in desc:
        return "Promotional Supplies - Graduation Merchandise"
    if "tacos el manantial" in desc:
        return "Meals & Entertainment - Staff Food"

    # Remaining debit transactions that should never be revenue
    if not is_credit:
        if "sale" in desc or "deposit" in desc:
            return "Banking - Debit Transaction"

    # Alcohol vendors (general)
    if any(vendor in desc for vendor in ["robert chick", "fritz", "southern"]):
        return "Cost of Goods Sold - Alcohol"

    # Payroll related (handle Robert Chick as payroll if it's a check)
    if pd.notnull(check_number):
        if "robert chick fri" in desc:
            return "Payroll - Manual Check - Hourly"
        return "Payroll - Manual Check - Hourly"

    # Other rules (reorder slightly for specificity if needed)
    if "prairie state" in desc or "prairiestategami vgtpayment" in desc:
        return "Revenue - Gaming - Slots"
    if "shift4" in desc:
        return "Revenue - POS - Credit Card" if is_credit else "Merchant Fees - Shift4"
    if "grubhub" in desc:
        return "Revenue - Delivery - Grubhub"
    if "ubereats" in desc or "uber usa" in desc:
        return "Revenue - Delivery - UberEats"
    if "doordash" in desc:
        return "Revenue - Delivery - DoorDash"
    if "adp" in desc or "payroll" in desc:
        return "Payroll - ADP - Salaried"
    if "sysco" in desc or "yzbizinc" in desc:
        return "Cost of Goods Sold - Food Vendor - Sysco"
    if "greco" in desc:
        return "Cost of Goods Sold - Packaging - Greco"
    if "beverage" in desc:
        return "Cost of Goods Sold - Beverages"
    if "rent" in desc or "lease" in desc:
        return "Facilities - Rent - Real Estate"
    if "ameren" in desc:
        return "Utilities - Electric - Ameren"
    if "gas" in desc:
        return "Utilities - Gas Service"
    if "american water" in desc or "illinois-america" in desc:
        return "Utilities - Water - American Water"
    if "waste management" in desc:
        return "Facilities - Waste Disposal - Contracted"
    if "w/d svc" in desc or "atm w/d" in desc:
        return "Bank Fees - ATM Withdrawal"
    if "facebook" in desc:
        return "Marketing - Digital - Facebook Ads"
    if "marketing" in desc:
        return "Marketing - Digital - General"
    if "graphics" in desc:
        return "Marketing - Print - Graphics Vendor"
    if "print" in desc:
        return "Marketing - Print - Materials"
    if "od item return" in desc or "nsf" in desc or "return item fee" in desc:
        return "Banking - Returned Payment - NSF"
    if "service charge" in desc:
        return "Bank Fees - Miscellaneous - Service Charge"
    if "fee" in desc:
        return "Bank Fees - Miscellaneous"
    if "transfer" in desc:
        return "Banking - Inter-Account Transfer"
    if "sale" in desc or "deposit" in desc:
        return "Revenue - General - In-Store"

    return None

def get_smart_category(description, amount, check_number, learned_rules, journal_rules):
    # Step 1: Check hardcoded overrides
    override = hardcoded_overrides(description, amount, check_number)
    if override:
        return override

    # Step 2: Check learned rules
    desc_lower = description.lower()
    for keyword, category in learned_rules.items():
        if keyword in desc_lower:
            return category

    # Step 3: Check journal rules
    for keyword, category in journal_rules.items():
        if keyword in desc_lower:
            return category

    # If no match found, use AI categorization
    return None

def update_learned_rules(description, category, learned_rules):
    # Extract key words from description
    words = description.lower().split()
    # Filter out common words and short words
    stop_words = ["a", "an", "the", "and", "or", "in", "on", "at", "for", "with", "to", "of", "from", "by", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "not", "but", "if", "then", "else", "when", "where", "how", "what", "which", "who", "whom", "this", "that", "these", "those", "can", "could", "will", "would", "should", "may", "might", "must", "about", "above", "after", "again", "against", "all", "am", "an", "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves"]
    key_words = [w for w in words if len(w) > 3 and w not in stop_words]
    
    # Update rules. Only add new patterns, don't overwrite if already exists
    # This prioritizes existing learned rules or manual overrides
    for word in key_words:
        # Check if the word is already a known vendor category or part of a hardcoded override (implicit check)
        # This prevents learning "shift4" to "Revenue" if it's already "Merchant Fees - Shift4" in hardcoded
        if word not in learned_rules or learned_rules[word] != category: # Only update if new or different
            learned_rules[word] = category
    
    return learned_rules

def parse_pdf_statement(file_path):
    text_content = ""
    try:
        doc = fitz.open(file_path)
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            text_content += page.get_text()
        doc.close()
    except Exception as e:
        st.error(f"Error extracting text from PDF: {e}")
        return None
    return text_content

def parse_structured_pdf_data(pdf_text):
    transactions = []
    # Basic regex patterns to find date, description, and amount
    # This is a very simplistic example and will need adjustment for real-world bank statements
    # Assumes a pattern like: DD/MM/YYYY Description Amount (positive or negative)
    # Or similar patterns. Real-world PDFs are much harder.
    # Example pattern: Date (DD/MM/YY or DD-MM-YY), Description, Amount (with optional currency and thousands separator)
    # This pattern is highly specific and likely needs customisation for each bank statement format
    # Let's try to capture lines that look like transactions.

    # Improved regex: Matches Date, then description (greedy), then amount
    # Date formats: MM/DD/YYYY, MM-DD-YYYY, MM/DD/YY, MM-DD-YY
    # Amount: possibly with ',' for thousands, '.' for decimal, and optional '-' for negative
    # Description: anything in between date and amount

    # This regex is a starting point. Bank statements vary widely.
    # It assumes date at the beginning of the line, then description, then amount at the end.
    pattern = re.compile(r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+(.*?)\s+([\-]?\$?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)')

    for line in pdf_text.split('\n'):
        match = pattern.search(line.strip())
        if match:
            try:
                date_str, description, amount_str = match.groups()
                # Clean amount string: remove '$', ',', then convert to float
                amount = float(amount_str.replace('$', '').replace(',', ''))
                transactions.append({
                    'Date': pd.to_datetime(date_str, errors='coerce'),
                    'Description': description.strip(),
                    'Amount': amount
                })
            except Exception as e:
                st.warning(f"Could not parse line: {line.strip()} - {e}")

    if transactions:
        return pd.DataFrame(transactions).dropna(subset=['Date'])
    return pd.DataFrame(columns=['Date', 'Description', 'Amount'])

def standardize_dataframe_columns(df):
    # Create a mapping from normalized original column names to target standard names
    standard_column_names = {
        'date': 'date',
        'transactiondate': 'date',
        'postingdate': 'date',
        'processeddate': 'date',
        'description': 'description',
        'transactiondescription': 'description',
        'details': 'description',
        'memo': 'description',
        'amount': 'amount',
        'debit': 'debit',
        'credit': 'credit',
        'withdrawal': 'debit',
        'deposit': 'credit'
    }

    # Rename columns based on the mapping
    renamed_columns = {}
    for col in df.columns:
        # Use re.sub for regex replacement on a string
        normalized_col = re.sub(r'[^a-z0-9]+', '', col.strip().lower())
        if normalized_col in standard_column_names:
            renamed_columns[col] = standard_column_names[normalized_col]
        else:
            renamed_columns[col] = col

    df.rename(columns=renamed_columns, inplace=True)
    
    # Convert all column names to lowercase
    df.columns = df.columns.str.lower()

    # Process amount column only once
    if 'debit' in df.columns and 'credit' in df.columns:
        df['debit'] = pd.to_numeric(df['debit'], errors='coerce').fillna(0)
        df['credit'] = pd.to_numeric(df['credit'], errors='coerce').fillna(0)
        df['amount'] = df['credit'] - df['debit']
        df.drop(columns=['debit', 'credit'], inplace=True)
    elif 'debit' in df.columns and 'amount' not in df.columns:
        df['amount'] = -pd.to_numeric(df['debit'], errors='coerce').fillna(0)
        df.drop(columns=['debit'], inplace=True)
    elif 'credit' in df.columns and 'amount' not in df.columns:
        df['amount'] = pd.to_numeric(df['credit'], errors='coerce').fillna(0)
        df.drop(columns=['credit'], inplace=True)
    elif 'amount' in df.columns:
        # Ensure amount is numeric
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)

    return df

def categorize_transaction(description, amount, check_number, learned_rules, journal_rules):
    # First try to use learned rules and hardcoded overrides
    smart_category = get_smart_category(description, amount, check_number, learned_rules, journal_rules)
    if smart_category:
        return smart_category

    # If no match found, use AI with improved prompt
    try:
        is_credit = amount > 0 if isinstance(amount, (int, float)) else False
        
        # For debits, default to Banking - Debit Transaction if no specific category is found
        if not is_credit:
            return "Banking - Debit Transaction"
            
        # For credits, try AI categorization
        prompt = f"""
        You are an expert forensic accountant specializing in restaurant audits.

        Based on the following transaction description, assign the most specific accounting category possible.

        Description: "{description}"
        Amount: {amount} ({'Credit' if is_credit else 'Debit'})

        IMPORTANT RULES:
        1. NEVER categorize a debit transaction as revenue (unless it's a specific credit card reimbursement). General debits should be "Banking - Debit Transaction"
        2. Rewards Network *debits* are "Merchant Fees - Rewards Network". Rewards Network *settlements that are credits* are "Revenue - Credit Card Reimbursement"
        3. For any credit transaction that doesn't clearly match a revenue category, use "Revenue - Miscellaneous"
        4. For any debit transaction that doesn't clearly match an expense category, use "Banking - Debit Transaction"

        Use precision category naming such as:
        - Revenue - Delivery - Grubhub
        - Revenue - POS - Credit Card
        - Revenue - Credit Card Reimbursement
        - Revenue - Gaming - Slots
        - Revenue - Miscellaneous
        - Cost of Goods Sold - Food Vendor - Sysco
        - Cost of Goods Sold - Alcohol
        - COGS - Beverage Vendor - Breakthru
        - COGS - Food Vendor - Fivestar
        - COGS - CO2 Vendor - NuCO2
        - COGS - Beverage Vendor - Koerner
        - COGS - Alcohol Vendor - Southern Glazer
        - COGS - Beverage Vendor - Stokes
        - Payroll - ADP - Salaried
        - Payroll - Manual Check - Hourly
        - Utilities - Electric - Ameren
        - Utilities - Gas Service
        - Utilities - Water - American Water
        - Facilities - Rent - Real Estate
        - Facilities - Waste Disposal - Contracted
        - Facilities - Waste Disposal - LRS
        - Facilities - Security - ADT
        - Marketing - Digital - Facebook Ads
        - Marketing - Digital - General
        - Marketing - Print - Graphics Vendor
        - Marketing - Print - Materials
        - Marketing - Call Tracking - CallForce
        - Marketing - Social Media - Social Page Solutions
        - Banking - Returned Payment - NSF
        - Banking - Debit Transaction
        - Banking - Returned Payment - Stop Payment
        - Banking - Automated Clearing House (ACH) Transfer
        - Bank Fees - ATM Withdrawal
        - Bank Fees - Miscellaneous - Service Charge
        - Bank Fees - Miscellaneous
        - Merchant Fees - Rewards Network
        - Merchant Fees - EBF Holdings
        - Merchant Fees - Shift4
        - Merchant Fees - Nexus
        - Accounting - Bookkeeping Services
        - Technology - POS Hardware - Ziosk
        - Technology - POS Software - Arrow
        - Technology - Loyalty Program - Paytronix
        - Tax - State Withholding Payment
        - Shipping - Freight - Beelman
        - Janitorial - Cleaning Services
        - Janitorial - Sanitation Vendor - PHS
        - Insurance - General Liability
        - Fuel - Travel Expenses
        - Corporate Allocation - Overhead G&A

        Return ONLY the exact accounting category string. Do not include punctuation or commentary.
        """
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        category = response.text.strip()

        # Double-check: If it's a debit and somehow got categorized as a revenue, reset it
        if not is_credit and category.startswith("Revenue"):
            st.warning(f"AI incorrectly categorized debit as Revenue for: {description}. Resetting to Banking - Debit Transaction.")
            category = "Banking - Debit Transaction"
        
        return category
    except Exception as e:
        st.error(f"Failed to categorize transaction with AI: {e}")
        # For debits, default to Banking - Debit Transaction
        if not is_credit:
            return "Banking - Debit Transaction"
        # For credits, default to Revenue - Miscellaneous
        return "Revenue - Miscellaneous"

def get_financial_insight(df, query):
    if df.empty:
        return "No financial data available to provide insights."
    
    # Prepare a summary of the financial data for Gemini
    # This is a simplified representation. For more detailed insights,
    # you'd provide more specific data points, trends, etc.
    data_summary = df.to_string(index=False)[:2000] # Limit data to avoid token limits

    prompt = f"""You are a financial analyst. Based on the following transaction data, answer the user's query.

Transaction Data (first few rows/summary):
{data_summary}

User Query: {query}

Provide a concise and insightful answer."""

    try:
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        st.error(f"Failed to get AI insight: {e}")
        return "Could not generate insight at this time."

def get_category_sum(df, categories, is_expense=False):
    if not categories:
        return 0.0
    
    # Ensure we're working with a copy to avoid modifying the original
    df = df.copy()
    
    # Ensure column names are lowercase
    df.columns = df.columns.str.lower()
    
    # Remove any duplicate transactions based on date, description, and amount
    df = df.drop_duplicates(subset=['date', 'description', 'amount'])
    
    # Get the sum for the specified categories
    total = df[df['category'].isin(categories)]['amount'].sum()
    
    # Return absolute value for expenses, actual value for income
    return abs(total) if is_expense else total

def generate_pnl_statement(categorized_df):
    # This function now just prepares the data, Excel formatting happens during writing
    pnl_data = []
    row_references = {}
    current_row_index = 0 # Starting from 0 for internal list tracking

    # Iterate through the P&L structure to collect values and prepare for Excel writing
    for item in P_AND_L_STRUCTURE:
        category_name = item["Category"]
        indent = " " * (item.get("Indent", 0) * 4) # 4 spaces per indent level
        display_category = f"{indent}{category_name}"

        # Convert category name to a valid placeholder name for formulas
        # This ensures keys in row_references match placeholders in formulas
        placeholder_key = category_name.lower().replace(" ", "_").replace("-", "_").replace("&", "and").replace("(", "").replace(")", "").replace(".", "").replace("/", "_") # Add more replacements as needed
        
        # For calculated rows, store a placeholder for the row reference
        if item["Type"] == "Calculated":
            row_references[f"{placeholder_key}_row"] = current_row_index + 6 # +6 because Excel starts at row 6 after title/headers
            pnl_data.append({"Category": display_category, "Amount": item["Formula"]}) # Store formula string
        elif item["Type"] == "Header":
            pnl_data.append({"Category": display_category, "Amount": ""})
            row_references[f"{placeholder_key}_row"] = current_row_index + 6 # Store for potential reference even if it's a header
        elif item["Type"] == "Value":
            amount = get_category_sum(categorized_df, item["Map"], item.get("IsExpense", False))
            pnl_data.append({"Category": display_category, "Amount": amount})
            row_references[f"{placeholder_key}_row"] = current_row_index + 6 # Store 1-based row index for Excel, +6 for offset

        current_row_index += 1
    
    # Now, fill in the row references into the formulas
    for i, row_dict in enumerate(pnl_data):
        if isinstance(row_dict["Amount"], str) and "{" in row_dict["Amount"]:
            # Use the already populated row_references directly
            formula = row_dict["Amount"].format(**row_references)
            pnl_data[i]["Amount"] = '=' + formula # Prepend '=' to make it an Excel formula

    return pnl_data

def accounting_assistant_page():
    st.title("Accounting Assistant")
    st.write("Upload your bank statements to analyze and categorize transactions.")

    uploaded_files = st.file_uploader("Upload bank statements (CSV, Excel, PDF)", type=["csv", "xlsx", "pdf"], accept_multiple_files=True)

    if uploaded_files:
        all_transactions = []
        for uploaded_file in uploaded_files:
            file_details = {"FileName": uploaded_file.name, "FileType": uploaded_file.type, "FileSize": uploaded_file.size}
            st.write(file_details)

            if uploaded_file.type == "application/pdf":
                transactions = parse_pdf_statement(uploaded_file)
            else:
                transactions = pd.read_csv(uploaded_file) if uploaded_file.type == "text/csv" else pd.read_excel(uploaded_file)

            all_transactions.append(transactions)

        if all_transactions:
            df = pd.concat(all_transactions, ignore_index=True)
            df = standardize_dataframe_columns(df.copy())

            # Ensure required columns exist
            required_columns = ['date', 'description', 'amount']
            if not all(col in df.columns for col in required_columns):
                st.error(f"Missing required columns. Please ensure your statement has: {', '.join(required_columns)}")
                st.write("Available columns:", df.columns.tolist())
                return

            # Convert date column to datetime
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df.dropna(subset=['date'], inplace=True)
            
            # Explicitly convert 'amount' to numeric
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)

            # Extract check number if available
            df['check_number'] = df.apply(
                lambda row: re.search(r'check(?:\s*#)?\s*(\d+)', str(row['description']).lower()).group(1) 
                if re.search(r'check(?:\s*#)?\s*(\d+)', str(row['description']).lower()) 
                else None, 
                axis=1
            )

            # Load learned and journal rules
            learned_rules = load_learned_rules()
            journal_rules = load_journal_rules()

            # Process transactions month by month to show progress
            progress_text = "Processing and categorizing transactions..."
            my_bar = st.progress(0, text=progress_text)

            processed_transactions = []
            total_rows = len(df)

            for i, row in enumerate(df.itertuples(index=False), 1):
                # Ensure column names are consistently lowercase after standardization
                category = categorize_transaction(row.description, row.amount, row.check_number, learned_rules, journal_rules)
                processed_transactions.append(row._asdict() | {'category': category})
                my_bar.progress(i / total_rows, text=f"{progress_text} {i}/{total_rows}")
            
            categorized_df = pd.DataFrame(processed_transactions)

            st.success("Transactions processed successfully!")

            # Display categorized transactions
            st.subheader("Categorized Transactions (First 100 rows)")
            st.dataframe(categorized_df.head(100))

            # Generate P&L Statement
            st.subheader("Profit & Loss Statement")
            pnl_data_for_display = generate_pnl_statement(categorized_df)
            pnl_df_for_display = pd.DataFrame(pnl_data_for_display)
            st.dataframe(pnl_df_for_display)

            # Download P&L as Excel
            output = io.BytesIO()
            # Convert pnl_data_for_display (which is a list of dicts) to DataFrame for excel export
            pnl_df_for_excel = pd.DataFrame(pnl_data_for_display)
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                worksheet = writer.book.add_worksheet('P&L Statement')

                # Define formats
                header_format = writer.book.add_format({'bold': True, 'font_name': 'Arial', 'font_size': 10, 'border': 1})
                value_format = writer.book.add_format({'font_name': 'Arial', 'font_size': 10, 'num_format': '#,##0.00', 'border': 1})
                bold_format = writer.book.add_format({'bold': True, 'font_name': 'Arial', 'font_size': 10, 'border': 1})

                # Write headers with specific column widths and format
                headers = ["Category", "Amount"]
                for col_num, header in enumerate(headers):
                    worksheet.write(0, col_num, header, header_format)
                    worksheet.set_column(col_num, col_num, 25 if col_num == 0 else 15) # Adjust column widths
                
                # Set default row height and hide gridlines
                worksheet.set_default_row(15) # Default row height
                worksheet.hide_gridlines(2) # Hide all gridlines

                # Write data
                for row_num, row_data in enumerate(pnl_df_for_excel.itertuples(index=False), start=1):
                    category_cell = row_data[0]
                    amount_cell = row_data[1]
                    
                    # Determine format based on bolding instruction in P_AND_L_STRUCTURE
                    current_pnl_item = P_AND_L_STRUCTURE[row_num - 1] # Adjust index for P_AND_L_STRUCTURE
                    cell_format = bold_format if current_pnl_item.get('Bolding', False) else value_format

                    # Write Category. For headers, use bold format.
                    if current_pnl_item.get('Type') == 'Header':
                        worksheet.write(row_num, 0, category_cell, bold_format)
                        worksheet.write(row_num, 1, amount_cell, bold_format) # Also write amount for headers in bold if any
                    elif isinstance(amount_cell, str) and amount_cell.startswith('='):
                        worksheet.write_formula(row_num, 0, category_cell, cell_format) # Write category for formula rows too
                        worksheet.write_formula(row_num, 1, amount_cell, cell_format)
                    else:
                        worksheet.write(row_num, 0, category_cell, cell_format)
                        worksheet.write(row_num, 1, amount_cell, cell_format)


            output.seek(0)
            st.download_button(
                label="Download P&L Statement (Excel)",
                data=output.getvalue(),
                file_name="profit_and_loss_statement.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            # Save learned rules
            save_learned_rules(learned_rules)
            # Save journal rules (assuming they are modified)
            # save_journal_rules(journal_rules)

if __name__ == "__main__":
    accounting_assistant_page() 