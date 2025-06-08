import pandas as pd
import streamlit as st
import re
from datetime import datetime
from pathlib import Path
import google.generativeai as genai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def generate_ai_analysis(df: pd.DataFrame, metrics: dict, date_range: tuple = None) -> str:
    """Generate AI-powered analysis using Google's Gemini."""
    try:
        # Prepare data for analysis
        top_items = df.nlargest(5, 'Total Sales')[['Item Name', 'Quantity', 'Total Sales', 'Price']]
        bottom_items = df.nsmallest(5, 'Total Sales')[['Item Name', 'Quantity', 'Total Sales', 'Price']]
        
        # Calculate additional metrics
        total_items = len(df)
        avg_price = metrics['avg_price']
        total_sales = metrics['total_sales']
        
        # Create prompt for Gemini
        prompt = f"""As an investment banking analyst specializing in restaurant operations, provide a detailed analysis and recommendations based on the following menu sales data:

Period: {date_range[0].strftime('%B %d, %Y')} to {date_range[1].strftime('%B %d, %Y')}

Key Metrics:
- Total Sales: ${total_sales:,.2f}
- Total Items Sold: {metrics['total_items']:,.0f}
- Average Item Price: ${avg_price:,.2f}
- Total Menu Items: {total_items}

Top 5 Items by Sales:
{top_items.to_string()}

Bottom 5 Items by Sales:
{bottom_items.to_string()}

Please provide:
1. A detailed analysis of the business performance
2. Specific marketing and promotional recommendations
3. Menu optimization suggestions
4. Pricing strategy insights
5. Growth opportunities

Format the response in a professional, investment banking style with clear sections and bullet points where appropriate."""

        # Call Gemini API
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        st.error(f"Failed to generate AI analysis: {e}")
        return "AI analysis could not be generated at this time."

def display_ai_analysis(analysis: str) -> None:
    """Display the AI analysis in a formatted way."""
    st.markdown("---")
    st.markdown("### 🎯 Kush's Investment Banking Level Analysis")
    st.markdown(analysis)
    st.markdown("---")

def extract_date_range(filename: str) -> tuple:
    """Extract date range from filename in format YYYYMMDD_YYYYMMDD."""
    try:
        match = re.search(r'(\d{8})_(\d{8})', filename)
        if match:
            start_date = datetime.strptime(match.group(1), '%Y%m%d')
            end_date = datetime.strptime(match.group(2), '%Y%m%d')
            return start_date, end_date
        return None, None
    except Exception as e:
        st.warning(f"Could not extract date range from filename: {e}")
        return None, None

def find_header_row(df_raw: pd.DataFrame) -> int:
    """Find the header row in the raw DataFrame."""
    for i in range(df_raw.shape[0]):
        non_nan_count = df_raw.iloc[i].dropna().shape[0]
        if non_nan_count > 3:  # Header should have at least 3 non-empty values
            return i
    return -1

def clean_and_rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Clean column names and rename them to standard format."""
    # Clean column names
    df.columns = [str(col).strip().lower() for col in df.columns]
    
    # Drop unnamed columns
    df = df.loc[:, ~df.columns.str.contains('^unnamed', case=False)]
    
    # Map column names
    column_mapping = {
        'item description': 'Item Name',
        'qty': 'Quantity',
        'sales': 'Total Sales'
    }
    
    return df.rename(columns=column_mapping)

def calculate_metrics(df: pd.DataFrame) -> dict:
    """Calculate summary metrics from the DataFrame."""
    total_menu_sales = df['Total Sales'].sum()
    total_items_sold = df['Quantity'].sum()
    average_item_price = total_menu_sales / total_items_sold if total_items_sold > 0 else 0
    
    return {
        'total_sales': total_menu_sales,
        'total_items': total_items_sold,
        'avg_price': average_item_price
    }

def display_metrics(metrics: dict, date_range: tuple = None) -> None:
    """Display metrics in a clean, organized format."""
    if date_range:
        start_date, end_date = date_range
        st.write(f"Report Period: {start_date.strftime('%B %d, %Y')} to {end_date.strftime('%B %d, %Y')}")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Menu Sales", f"${metrics['total_sales']:,.2f}")
    with col2:
        st.metric("Total Items Sold", f"{metrics['total_items']:,.0f}")
    with col3:
        st.metric("Average Item Price", f"${metrics['avg_price']:,.2f}")

def parse_menu_sales_report(file_path: str) -> pd.DataFrame:
    """Parse the menu sales analysis Excel file into a pandas DataFrame."""
    try:
        # Extract date range from filename
        filename = Path(file_path).name
        date_range = extract_date_range(filename)
        
        # Read the Excel file
        df_raw = pd.read_excel(file_path, sheet_name='Sheet1', header=None, engine='openpyxl')
        
        # Find header row
        header_row_index = find_header_row(df_raw)
        if header_row_index == -1:
            st.error("Could not detect a clear header row in the menu sales report.")
            return pd.DataFrame()
        
        # Read file with correct header
        df = pd.read_excel(file_path, sheet_name='Sheet1', header=header_row_index, engine='openpyxl')
        
        # Clean and rename columns
        df = clean_and_rename_columns(df)
        
        # Validate required columns
        required_columns = ['Item Name', 'Quantity', 'Total Sales']
        if not all(col in df.columns for col in required_columns):
            missing_cols = [col for col in required_columns if col not in df.columns]
            st.error(f"Missing required columns: {missing_cols}")
            return pd.DataFrame()
        
        # Convert numeric columns
        for col in ['Quantity', 'Total Sales']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Calculate price
        df['Price'] = (df['Total Sales'] / df['Quantity']).round(2)
        df.loc[df['Quantity'] == 0, 'Price'] = 0
        
        # Clean data
        df = df[df['Item Name'].notna() & (df['Quantity'] > 0)]
        
        # Calculate and display metrics
        metrics = calculate_metrics(df)
        display_metrics(metrics, date_range)
        
        # Generate and display AI analysis
        if date_range:
            analysis = generate_ai_analysis(df, metrics, date_range)
            display_ai_analysis(analysis)
        
        st.success("Menu sales report parsed successfully!")
        return df
        
    except Exception as e:
        st.error(f"Error parsing menu sales report: {e}")
        return pd.DataFrame() 