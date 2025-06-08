import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import google.generativeai as genai
import os
from dotenv import load_dotenv
from pathlib import Path
import re
from pages.accounting_assistant_page import accounting_assistant_page

# Load environment variables
load_dotenv()

# Initialize Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

st.set_page_config(page_title="Action Plan & Marketing Strategy", layout="wide")

def generate_action_plan(sales_df, menu_df, sales_file_name, menu_file_name):
    """Generate a comprehensive action plan using AI."""
    try:
        # Extract date ranges from filenames
        sales_date_match = re.search(r'(\d{8})_(\d{8})', sales_file_name)
        menu_date_match = re.search(r'(\d{8})_(\d{8})', menu_file_name)
        
        sales_period = f"{datetime.strptime(sales_date_match.group(1), '%Y%m%d').strftime('%B %d, %Y')} to {datetime.strptime(sales_date_match.group(2), '%Y%m%d').strftime('%B %d, %Y')}"
        menu_period = f"{datetime.strptime(menu_date_match.group(1), '%Y%m%d').strftime('%B %d, %Y')} to {datetime.strptime(menu_date_match.group(2), '%Y%m%d').strftime('%B %d, %Y')}"

        # Calculate key metrics
        total_sales = sales_df['Total Sales'].sum() # Assuming 'Total Sales' is now correctly in sales_df
        avg_daily_sales = sales_df['Total Sales'].mean()
        total_items_sold = menu_df['Quantity'].sum()
        avg_item_price = menu_df['Total Sales'].sum() / total_items_sold if total_items_sold > 0 else 0

        # Get top and bottom performing items
        top_items = menu_df.nlargest(5, 'Total Sales')[['Item Name', 'Quantity', 'Total Sales', 'Price']]
        bottom_items = menu_df.nsmallest(5, 'Total Sales')[['Item Name', 'Quantity', 'Total Sales', 'Price']]

        # Create prompt for Gemini
        prompt = f"""As a strategic business consultant specializing in restaurant operations, create a comprehensive action plan and marketing strategy based on the following data:

Sales Period: {sales_period}
Menu Analysis Period: {menu_period}

Key Performance Metrics:
- Total Sales: ${total_sales:,.2f}
- Average Daily Sales: ${avg_daily_sales:,.2f}
- Total Items Sold: {total_items_sold:,.0f}
- Average Item Price: ${avg_item_price:,.2f}

Top 5 Performing Items:
{top_items.to_string()}

Bottom 5 Performing Items:
{bottom_items.to_string()}

Please provide a detailed action plan with the following sections:

1. Executive Summary
   - Key findings and opportunities
   - Critical areas for improvement

2. Marketing Strategy
   - Target audience analysis
   - Promotional recommendations
   - Social media strategy
   - Customer engagement initiatives

3. Menu Optimization
   - Item performance analysis
   - Menu engineering recommendations
   - Pricing strategy adjustments
   - New item suggestions

4. Operational Improvements
   - Efficiency recommendations
   - Cost optimization opportunities
   - Staff training suggestions

5. Growth Initiatives
   - Short-term growth opportunities
   - Long-term strategic initiatives
   - Competitive positioning

6. Implementation Timeline
   - Immediate actions (0-30 days)
   - Short-term initiatives (1-3 months)
   - Long-term projects (3-6 months)

Format the response in a professional business consulting style with clear sections, bullet points, and actionable recommendations."""

        # Call Gemini API
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        st.error(f"Failed to generate action plan: {e}")
        return "Action plan could not be generated at this time."

def main():
    st.title("🎯 Action Plan & Marketing Strategy")
    st.markdown("### Comprehensive Business Strategy Dashboard")

    # Load data from session state if available
    sales_df = st.session_state.get('processed_sales_df', None)
    sales_file_name = st.session_state.get('sales_file_name', None)
    menu_df = st.session_state.get('processed_menu_df', None)
    menu_file_name = st.session_state.get('menu_file_name', None)

    if menu_df is not None:
        st.write(f"Menu Data Columns in Action Plan Page: {menu_df.columns.tolist()}")

    if sales_df is not None and sales_file_name is not None and menu_df is not None and menu_file_name is not None:
        # Generate and display action plan
        with st.spinner("Generating comprehensive action plan..."):
            action_plan = generate_action_plan(sales_df, menu_df, sales_file_name, menu_file_name)
            
            # Display action plan in a nice format
            st.markdown("---")
            st.markdown(action_plan)
            st.markdown("---")

            # Add download button for the action plan
            st.download_button(
                label="📥 Download Action Plan",
                data=action_plan,
                file_name="action_plan.txt",
                mime="text/plain"
            )
    else:
        st.error("Please ensure sales and menu data have been processed and are available in the Sales Dashboard and Menu Analysis pages respectively.")

    if page == "Accounting Assistant":
        accounting_assistant_page()

if __name__ == "__main__":
    main() 