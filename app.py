import os
import streamlit as st
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from email.mime.base import MIMEBase
from email import encoders
from app_logic import process_payroll_report
from email_handler import download_latest_attachment, download_latest_sales_report, generate_financial_summary_email, download_latest_menu_sales_report
from schedule_handler import download_latest_employee_schedule, parse_employee_schedule, generate_ai_schedule_changes, generate_formatted_excel_schedule
from menu_handler import parse_menu_sales_report
import pandas as pd
from datetime import datetime
from pathlib import Path
from io import BytesIO
import plotly.graph_objects as go # New import for Plotly
import google.generativeai as genai
from pages.accounting_assistant_page import accounting_assistant_page

load_dotenv()

# Initialize Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

st.set_page_config(page_title="Rosati's Executive Dashboard", layout="wide")

# Initialize session state variables if they don't exist
if "file_path" not in st.session_state:
    st.session_state.file_path = None

# Custom CSS for bigger font and polished look
st.markdown("""
<style>
    /* General font size for the whole app */
    html, body, [class*="st-"] {
        font-size: 18px; /* Adjust as needed, e.g., 16px, 18px, 20px */
    }
    /* Headings */
    h1 {
        font-size: 3em; /* Larger H1 */
        color: #FF4B4B; /* Streamlit primary color */
    }
    h2 {
        font-size: 2.5em; /* Larger H2 */
    }
    h3 {
        font-size: 2em; /* Larger H3 */
    }
    h4 {
        font-size: 1.5em; /* Larger H4 */
    }
    /* Text input and text area */
    .stTextInput>div>div>input,
    .stTextArea>div>div>textarea {
        font-size: 1.1em;
    }
    /* Buttons */
    .stButton>button {
        font-size: 1.1em;
        padding: 0.75em 1.5em;
    }
    /* Dataframe */
    .stDataFrame {
        font-size: 1em;
    }
    /* Success/Error/Warning messages */
    .stAlert {
        font-size: 1.1em;
    }
    /* Sidebar radio buttons */
    .stRadio > label > div {
        font-size: 1.1em;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to send email
def send_email(to_email, subject, body, attachment_path=None):
    try:
        # Use Gmail SMTP settings
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        username = os.getenv("EMAIL_USER")
        password = os.getenv("EMAIL_PASS")

        if not all([username, password]):
            raise ValueError("Email credentials not found in environment variables")

        msg = MIMEMultipart()
        msg["From"] = username
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(attachment_path)}")
                msg.attach(part)

        # Create SMTP connection with timeout
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
        server.starttls()
        server.login(username, password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to send email: {str(e)}")
        return False

# Helper function to generate sales excel for download/attachment
def generate_sales_excel_download(df, filename="Rosatis_Sales_Report.xlsx"):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sales Data')
    output.seek(0)

    # Save to a specific path for attachment
    download_dir = Path("downloads")
    download_dir.mkdir(parents=True, exist_ok=True)
    file_path = download_dir / filename
    with open(file_path, "wb") as f:
        f.write(output.read())
    return str(file_path)

def generate_ai_analysis(df):
    """Generate AI-powered financial analysis using Google's Gemini."""
    try:
        # Prepare key metrics for analysis
        metrics = {
            'total_sales': df['Total Sales'].sum(),
            'avg_daily_sales': df['Total Sales'].mean(),
            'total_labor_cost': df['Labor Cost'].sum() if 'Labor Cost' in df.columns else 0,
            'avg_labor_percent': df['Labor %'].mean() if 'Labor %' in df.columns else 0,
            'total_voids': df['Voids Amount'].sum() if 'Voids Amount' in df.columns else 0,
            'avg_delivery_charge': df['Delivery Charges'].mean() if 'Delivery Charges' in df.columns else 0,
            'best_day': df.loc[df['Total Sales'].idxmax()]['Date'].strftime('%B %d, %Y') if not df.empty else 'N/A',
            'worst_day': df.loc[df['Total Sales'].idxmin()]['Date'].strftime('%B %d, %Y') if not df.empty else 'N/A',
            'best_sales': df['Total Sales'].max() if not df.empty else 0,
            'worst_sales': df['Total Sales'].min() if not df.empty else 0
        }

        # Create prompt for Gemini
        prompt = f"""As a financial analyst for a pizza restaurant, analyze the following metrics and provide detailed insights and recommendations:

Total Sales: ${metrics['total_sales']:,.2f}
Average Daily Sales: ${metrics['avg_daily_sales']:,.2f}
Total Labor Cost: ${metrics['total_labor_cost']:,.2f}
Average Labor Percentage: {metrics['avg_labor_percent']:,.2f}%
Total Voids: ${metrics['total_voids']:,.2f}
Average Delivery Charge: ${metrics['avg_delivery_charge']:,.2f}
Best Sales Day: {metrics['best_day']} (${metrics['best_sales']:,.2f})
Worst Sales Day: {metrics['worst_day']} (${metrics['worst_sales']:,.2f})

Please provide:
1. A detailed analysis of the business performance
2. Key insights about sales patterns and labor efficiency
3. Specific, actionable recommendations for improvement
4. Areas of concern that need attention

Format the response in a professional, easy-to-read manner suitable for a business report."""

        # Call Gemini API with the new model name
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        st.error(f"Failed to generate AI analysis: {e}")
        return "AI analysis could not be generated at this time."

# Sidebar for navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Payroll Processor", "Sales Dashboard", "Financial Summary Email", "Schedule Maker", "AI Bartender", "Menu Analysis", "Action Plan & Marketing Strategy", "Accounting Assistant"])


if page == "Payroll Processor":
    st.title("Rosati's Payroll Processor - Powered by Kush's AI Clone")

    # New: Input for Accountant Email
    accountant_email_default = os.getenv("ACCOUNTANT_EMAIL", "")
    accountant_email_input = st.text_input("Accountant Email:", value=accountant_email_default)

    # New: Text area for Email Body
    default_email_body = (
        "Hi Accountant,\n\n"
        "Please find the latest payroll report attached.\n\n"
        "- Sent by Kush's AI Clone 🤖\n"
        "Even in Chicago, I am still the hero. 💼\n"
    )
    email_body_input = st.text_area("Email Body:", value=default_email_body, height=150)

    uploaded_file = st.file_uploader("Upload Payroll Excel File", type=[".xlsx"])

    email_file_button = st.button("📬 Pull Latest from Email")
    process_button = st.button("⚙️ Process Payroll Report")
    send_button = st.button("✉️ Email Report to Accountant")

    if uploaded_file:
        with open(os.path.join("temp_uploaded_file.xlsx"), "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.session_state.file_path = "temp_uploaded_file.xlsx"
        st.success("File uploaded successfully!")

    if email_file_button:
        file_path = download_latest_attachment()
        if file_path:
            st.session_state.file_path = file_path
            st.success(f"📩 Pulled file: {os.path.basename(file_path)}")
        else:
            st.error("❌ No matching payroll email with attachment found.")

    if process_button and st.session_state.file_path:
        try:
            # Removed custom_rates parameter as it's no longer needed for auto-rate assignment
            final_df, output_path = process_payroll_report(st.session_state.file_path)
            st.success("✅ Payroll report processed successfully!")
            st.dataframe(final_df)
            with open(output_path, "rb") as f:
                st.download_button("⬇️ Download Final Report", f, file_name="Final_Payroll_Report.xlsx")

        except Exception as e:
            st.error(f"❌ Failed to process: {e}")

    if send_button and st.session_state.get("file_path") and "Final_Payroll_Report.xlsx" in os.listdir("."):
        if not accountant_email_input:
            st.error("❌ Please enter the accountant's email address.")
        else:
            try:
                # Use the new send_email helper function
                send_email(accountant_email_input, "Rosati's Payroll Report - AI Generated", email_body_input, attachment_path="Final_Payroll_Report.xlsx")
                st.success(f"📤 Email sent to {accountant_email_input} successfully!")
            except Exception as e:
                st.error(f"❌ Failed to send email: {e}")

elif page == "Sales Dashboard":
    st.title("📊 Rosati's Executive Sales Dashboard")

    uploaded_file_sales = st.sidebar.file_uploader("Upload Sales Report (.xlsx)", type=["xlsx"], key="sales_uploader")
    use_gmail = st.sidebar.button("📬 Import from Gmail", key="import_sales_email")

    xlsx_path = None
    last_received = None

    if uploaded_file_sales:
        # For uploaded file, we need to save it to a temporary path to use with pd.ExcelFile
        temp_upload_path = Path("downloads") / "temp_sales_upload.xlsx"
        temp_upload_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_upload_path, "wb") as f:
            f.write(uploaded_file_sales.getbuffer())
        xlsx_path = str(temp_upload_path)
        last_received = "Manual upload"
    elif use_gmail:
        sales_info = download_latest_sales_report()
        if sales_info:
            xlsx_path = sales_info # Assuming download_latest_sales_report returns path directly now
            last_received = os.path.basename(sales_info) + " from email"
        else:
            st.warning("No sales report found in Gmail.")

    if xlsx_path:
        try:
            # Dynamic header detection
            xlsx = pd.ExcelFile(xlsx_path, engine="openpyxl")
            sheet_name = xlsx.sheet_names[0]
            auto_header_row = None
            for i in range(5, 15): # Search for header between row 6 and 16 (0-indexed)
                try:
                    row_data = xlsx.parse(sheet_name, header=i, nrows=1)
                    if "Date" in row_data.columns:
                        auto_header_row = i
                        break
                except Exception as e:
                    continue

            if auto_header_row is None:
                st.error("Could not detect header row containing 'Date' column. Please check the Excel file.")
                st.stop()

            df = xlsx.parse(sheet_name, header=auto_header_row, engine="openpyxl")
            df.columns = [str(col).replace("\n", " ").strip() for col in df.columns] # Clean column names

            # Using a dictionary for mapping to handle potential variations and ensure consistency
            column_mapping = {
                'Total Sales': 'Total Sales',
                'Total\nSales': 'Total Sales',
                'Del Chg': 'Delivery Charges',
                'Labor': 'Labor Hours', # Renamed 'Labor' to 'Labor Hours'
                'Unnamed: 30': 'Labor Cost', # Explicitly map 'Unnamed: 30' to 'Labor Cost'
                'Unnamed: 31': 'Labor %',    # Explicitly map 'Unnamed: 31' to 'Labor %'
                'Cash & Carry': 'Cash & Carry',
                'Pickup': 'Pickup',
                'Delivery': 'Delivery',
                'Liable Taxes': 'Taxable Sales',
                'Non Liable Taxes': 'Non-Taxable Sales',
                'Voids': 'Voids Amount',
                'Chk\nCnt': 'Transaction Count',
                'Check Cnt': 'Transaction Count'
            }
            df.rename(columns=column_mapping, inplace=True) # Apply renaming here
            
            # --- NEW: Extract Total Labor Cost and Labor % from the 'Total' row before filtering ---
            total_labor_cost_summary = 0.0
            avg_labor_percent_summary = 0.0
            
            # More robustly filter for the actual 'Total' row
            # Look for 'Date' column exactly being 'Total' and ensure Labor Cost is not NaN
            total_row_candidates = df[df["Date"].astype(str).str.strip() == "Total"].copy()

            # Convert 'Labor Cost' and 'Labor %' columns in total_row_candidates to numeric
            if 'Labor Cost' in total_row_candidates.columns:
                total_row_candidates['Labor Cost'] = pd.to_numeric(total_row_candidates['Labor Cost'], errors='coerce').fillna(0.0)
            if 'Labor %' in total_row_candidates.columns:
                total_row_candidates['Labor %'] = pd.to_numeric(total_row_candidates['Labor %'], errors='coerce').fillna(0.0)
            
            if not total_row_candidates.empty:
                # Get the last row in case there are multiple 'Total' entries (e.g., subtotals)
                actual_total_row = total_row_candidates.tail(1)

                if 'Labor Cost' in actual_total_row.columns:
                    total_labor_cost_summary = actual_total_row['Labor Cost'].iloc[0] # Now directly numeric
                if 'Labor %' in actual_total_row.columns:
                    avg_labor_percent_summary = actual_total_row['Labor %'].iloc[0] # Now directly numeric
            # --- END NEW EXTRACTION ---

            df = df.dropna(how="all").copy()

            # Filter out rows that contain 'Total' in the 'Date' column (summary rows) for daily calculations
            if 'Date' in df.columns:
                df = df[~df["Date"].astype(str).str.contains("Total", case=False, na=False)]
                df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
                df = df[df["Date"].notna()].sort_values("Date")

            # Convert numeric columns to numeric, coercing errors
            # This list now correctly refers to the mapped columns after renaming
            numeric_cols = ['Total Sales', 'Labor Cost', 'Labor %', 'Cash & Carry', 'Pickup', 'Delivery', 
                            'Delivery Charges', 'Taxable Sales', 'Non-Taxable Sales', 'Voids Amount', 'Transaction Count'] 
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            # Calculate additional metrics (for daily data only)
            df['7d MA'] = df["Total Sales"].rolling(window=7, min_periods=1).mean()
            df['Day'] = df['Date'].dt.day_name()
            df['Month'] = df['Date'].dt.month_name()

            # Calculate Daily Labor Percentage (for daily data only) - RE-ADDED and ensured uses proper columns
            df['Labor %'] = df.apply(lambda row: (row['Labor Cost'] / row['Total Sales'] * 100) if row['Total Sales'] > 0 else 0, axis=1)

            # Ensure the processed DataFrame is stored in session state for other pages
            st.session_state.processed_sales_df = df
            st.session_state.sales_file_name = os.path.basename(xlsx_path) # Store the filename

            # KPI Cards
            st.subheader("Key Performance Indicators")
            col1, col2, col3 = st.columns(3)
            total_sales = df['Total Sales'].sum() # This will be sum of daily sales after filtering
            avg_daily_sales = df['Total Sales'].mean()
            
            # Use extracted summary values for KPI display
            col1.metric("Total Sales", f"${total_sales:,.2f}") # Aligned to 2 decimal places
            col2.metric("Avg Daily Sales", f"${avg_daily_sales:,.2f}") # Aligned to 2 decimal places
            col3.metric("Total Labor Cost", f"${total_labor_cost_summary:,.2f}") # Aligned to 2 decimal places
            
            col4, col5, col6 = st.columns(3)
            col4.metric("Avg Labor %", f"{avg_labor_percent_summary:,.2f}%") 
            # total_voids_amount and avg_delivery_charge can be calculated from the filtered daily data
            total_voids_amount = df['Voids Amount'].sum() if 'Voids Amount' in df.columns else 0
            avg_delivery_charge = df['Delivery Charges'].mean() if 'Delivery Charges' in df.columns else 0

            col5.metric("Total Voids Impact", f"${total_voids_amount:,.2f}") # Aligned to 2 decimal places
            col6.metric("Avg Delivery Charge", f" ${avg_delivery_charge:,.2f}") # Aligned to 2 decimal places

            # Best and Worst Sales Day
            if not df.empty and 'Total Sales' in df.columns:
                daily_summary_df = df.groupby("Date")["Total Sales"].sum().reset_index()
                if not daily_summary_df.empty:
                    best_day = daily_summary_df.loc[daily_summary_df["Total Sales"].idxmax()]
                    worst_day = daily_summary_df.loc[daily_summary_df["Total Sales"].idxmin()]
                    st.subheader("🏆 Daily Sales Performance Summary")
                    st.markdown(f"## **Best Sales Day:** {best_day['Date'].strftime('%B %d, %Y')} with ${best_day['Total Sales']:,.2f}") # Increased to H2
                    st.markdown(f"## **Worst Sales Day:** {worst_day['Date'].strftime('%B %d, %Y')} with ${worst_day['Total Sales']:,.2f}") # Increased to H2
                else:
                    st.info("Not enough data to determine best/worst sales day.")


            # Daily Sales & 7-Day Trend
            st.subheader("📈 Daily Sales & 7-Day Trend")
            fig_daily_sales = go.Figure()
            fig_daily_sales.add_trace(go.Scatter(x=df["Date"], y=df["Total Sales"], mode='lines+markers', name='Daily Sales'))
            fig_daily_sales.add_trace(go.Scatter(x=df["Date"], y=df["7d MA"], mode='lines', name='7-Day Avg', line=dict(dash='dash')))
            fig_daily_sales.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=400, 
                                          xaxis=dict(title_font_size=16, tickfont_size=14),
                                          yaxis=dict(title_font_size=16, tickfont_size=14),
                                          legend=dict(font_size=14),
                                          xaxis_title="Date", yaxis_title="Total Sales ($")
            st.plotly_chart(fig_daily_sales, use_container_width=True)

            # Sales by Day of Week
            st.subheader("📊 Sales by Day of Week")
            weekday_sales = df.groupby("Day")["Total Sales"].mean().reindex(
                ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
            fig_weekday_sales = go.Figure([go.Bar(x=weekday_sales.index, y=weekday_sales.values, 
                                                 text=[f"${v:,.0f}" for v in weekday_sales.values], textposition='outside', textfont_size=20)]) # Increased text font size
            fig_weekday_sales.update_layout(height=350, yaxis_title="Average Sales ($",
                                            xaxis=dict(title_font_size=16, tickfont_size=14),
                                            yaxis=dict(title_font_size=16, tickfont_size=14))
            st.plotly_chart(fig_weekday_sales, use_container_width=True)

            # Order Type Breakdown (Stacked Bar Chart)
            order_type_cols = ['Cash & Carry', 'Pickup', 'Delivery', 'Table'] # Added 'Table'
            # Filter for only columns that actually exist in the DataFrame
            existing_order_type_cols = [col for col in order_type_cols if col in df.columns]
            if existing_order_type_cols:
                st.subheader("📈 Order Type Breakdown (Daily)")
                fig_order_type = go.Figure()
                
                # Define consistent colors for order types
                order_type_colors = {
                    'Table': '#1f77b4', # Blue
                    'Pickup': '#ff7f0e', # Orange
                    'Cash & Carry': '#2ca02c', # Green
                    'Delivery': '#d62728' # Red
                }

                for col in existing_order_type_cols:
                    fig_order_type.add_trace(go.Bar(x=df["Date"], y=df[col], name=col, marker_color=order_type_colors.get(col, '#cccccc')))
                fig_order_type.update_layout(barmode='stack', height=400, 
                                             xaxis_title="Date", yaxis_title="Sales ($",
                                             xaxis=dict(title_font_size=16, tickfont_size=14),
                                             yaxis=dict(title_font_size=16, tickfont_size=14),
                                             legend=dict(font_size=14))
                st.plotly_chart(fig_order_type, use_container_width=True)
            else:
                st.info("No order type breakdown data available.")

            # AI Analysis (if desired)
            st.subheader("🧠 AI Financial Analysis")
            if 'processed_sales_df' in st.session_state:
                # Generate AI analysis using the processed sales data
                analysis_text = generate_ai_analysis(st.session_state.processed_sales_df)
                st.markdown(analysis_text)
                st.download_button(
                    label="Download AI Analysis",
                    data=analysis_text,
                    file_name="AI_Financial_Analysis.txt",
                    mime="text/plain"
                )
            else:
                st.info("Upload a sales report to generate AI analysis.")

        except Exception as e:
            st.error(f"❌ Failed to process sales file: {e}")
    else:
        st.info("Please upload a sales report or import one from Gmail.")

elif page == "Financial Summary Email":
    st.title("📧 Send Financial Summary Email")

    target_email = st.text_input("Recipient Email:", os.getenv("ACCOUNTANT_EMAIL", ""))
    email_subject = st.text_input("Email Subject:", "Rosati's Financial Summary - AI Generated")
    email_body = st.text_area("Email Body:", height=200, value=(
        "Dear Team,\n\n"
        "Please find the attached financial summary based on the latest sales data.\n\n"
        "Best regards,\n"
        "Kush's AI Clone 🤖"
    ))

    if st.button("📧 Generate and Send Summary Email"):
        if not st.session_state.get('processed_sales_df') is None and not st.session_state.get('processed_sales_df').empty:
            analysis_text = generate_ai_analysis(st.session_state['processed_sales_df'])
            # Generate sales report for attachment
            sales_report_path = generate_sales_excel_download(st.session_state['processed_sales_df'])

            # Send email with AI analysis in body and sales report as attachment
            if generate_financial_summary_email(analysis_text, target_email, email_subject):
                # If you still want to attach the sales report, you'll need a separate function call for that
                # For now, we're assuming the user wants ONLY the summary in the body and no other attachments based on the request
                st.success(f"Financial summary email sent successfully to {target_email}!")
            else:
                st.error("Failed to send financial summary email.")
        else:
            st.warning("Please process a sales report first to generate a financial summary.")

elif page == "Schedule Maker":
    st.title("🗓️ Rosati's Employee Schedule Maker")

    if "schedule_df" not in st.session_state:
        st.session_state.schedule_df = pd.DataFrame()
    if "schedule_file_path" not in st.session_state:
        st.session_state.schedule_file_path = None

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📬 Download Latest Schedule from Email"):
            with st.spinner("Downloading schedule..."):
                file_path = download_latest_employee_schedule()
                if file_path:
                    df = parse_employee_schedule(file_path)
                    if not df.empty:
                        st.session_state.schedule_file_path = file_path
                        st.session_state.schedule_df = df
                        st.success("Schedule downloaded and loaded successfully!")
                        if 'Date' in st.session_state.schedule_df.columns:
                            dates = pd.to_datetime(st.session_state.schedule_df['Date'].dropna())
                            if not dates.empty:
                                st.session_state.start_date = dates.min()
                                st.session_state.end_date = dates.max()
                    else:
                        st.error("Could not parse the downloaded schedule.")
                else:
                    st.error("Failed to download schedule from email.")

    with col2:
        uploaded_schedule_file = st.file_uploader("Upload Schedule Excel File", type=["xlsx"], key="schedule_uploader")
        if uploaded_schedule_file:
            temp_upload_path = Path("downloads") / "uploaded_employee_schedule.xlsx"
            temp_upload_path.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_upload_path, "wb") as f:
                f.write(uploaded_schedule_file.getbuffer())
            df = parse_employee_schedule(str(temp_upload_path))
            if not df.empty:
                st.session_state.schedule_file_path = str(temp_upload_path)
                st.session_state.schedule_df = df
                st.success("Schedule uploaded and loaded successfully!")
                if 'Date' in st.session_state.schedule_df.columns:
                    # Assuming 'Date' column is available and contains relevant dates for the schedule period
                    dates = pd.to_datetime(st.session_state.schedule_df['Date'].dropna())
                    if not dates.empty:
                        st.session_state.start_date = dates.min()
                        st.session_state.end_date = dates.max()

            else:
                st.error("Could not parse the uploaded schedule.")

    if not st.session_state.schedule_df.empty:
        st.subheader("Current Employee Schedule")
        editable_df = st.data_editor(st.session_state.schedule_df, key="schedule_editor")

        user_ai_prompt = st.text_area("Describe any changes or a new schedule you want AI to generate:", height=100)
        if st.button("✨ Generate AI Schedule Changes"):
            if user_ai_prompt:
                with st.spinner("Generating AI schedule changes..."):
                    updated_df = generate_ai_schedule_changes(editable_df, user_ai_prompt)
                    st.session_state.schedule_df = updated_df
                    st.success("AI schedule changes generated!")
            else:
                st.warning("Please enter a prompt for AI schedule generation.")

        # Download formatted Excel schedule
        if st.button("⬇️ Download Formatted Schedule"):
            if st.session_state.schedule_file_path:
                with st.spinner("Generating formatted Excel schedule..."):
                    # Ensure the latest state of the DataFrame is used for download
                    output_buffer = generate_formatted_excel_schedule(st.session_state.schedule_df, st.session_state.schedule_file_path)
                    st.download_button(
                        label="Download Schedule",
                        data=output_buffer.getvalue(),
                        file_name="Formatted_Employee_Schedule.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    st.success("Formatted schedule generated for download!")
            else:
                st.warning("Please upload or download a schedule first.")

elif page == "Menu Analysis":
    st.title("🍕 Menu Analysis Dashboard")

    # File upload and download options
    col1, col2 = st.columns(2)
    with col1:
        uploaded_menu_file = st.file_uploader("Upload Menu Analysis Report (.xlsx)", type=["xlsx"], key="menu_uploader")
    with col2:
        if st.button("📬 Import from Gmail"):
            with st.spinner("Downloading latest menu sales report..."):
                menu_file_path = download_latest_menu_sales_report()
                if menu_file_path:
                    st.session_state.menu_file_path = menu_file_path
                    st.success(f"Downloaded menu analysis report: {os.path.basename(menu_file_path)}")
                else:
                    st.warning("No menu analysis report found in Gmail.")

    # Process the menu analysis file
    menu_file_path = st.session_state.get('menu_file_path')
    if uploaded_menu_file:
        temp_upload_path = Path("downloads") / "temp_menu_upload.xlsx"
        temp_upload_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_upload_path, "wb") as f:
            f.write(uploaded_menu_file.getbuffer())
        menu_file_path = str(temp_upload_path)
        st.session_state.menu_file_path = menu_file_path

    if menu_file_path:
        try:
            # Use the new parsing function
            df = parse_menu_sales_report(menu_file_path)
            
            # Store processed menu DataFrame and filename in session state
            st.session_state.processed_menu_df = df
            st.session_state.menu_file_name = os.path.basename(menu_file_path)
            
            if df.empty:
                st.warning("Parsed menu data is empty. Please check the file content or format.")
            else:
                # Display key metrics
                st.subheader("📊 Key Menu Performance Metrics")
                col1, col2, col3 = st.columns(3)
                
                # Calculate and display metrics (adjust column names based on your actual data)
                if 'Total Sales' in df.columns:
                    total_sales = df['Total Sales'].sum()
                    col1.metric("Total Menu Sales", f"${total_sales:,.2f}")
                
                if 'Quantity' in df.columns:
                    total_items = df['Quantity'].sum()
                    col2.metric("Total Items Sold", f"{total_items:,.0f}")
                
                if 'Price' in df.columns and 'Quantity' in df.columns:
                    # Ensure Price and Quantity are numeric before calculation
                    df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
                    df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce').fillna(0)

                    # Avoid division by zero
                    if df['Quantity'].sum() > 0:
                        avg_price = (df['Price'] * df['Quantity']).sum() / df['Quantity'].sum()
                        col3.metric("Average Item Price", f"${avg_price:,.2f}")
                    else:
                        col3.metric("Average Item Price", "$0.00")

                # Top Selling Items
                st.subheader("🏆 Top Selling Items")
                if 'Item Name' in df.columns and 'Quantity' in df.columns:
                    top_items = df.groupby('Item Name')['Quantity'].sum().sort_values(ascending=False).head(10)
                    fig_top_items = go.Figure(data=[go.Bar(x=top_items.index, y=top_items.values)])
                    fig_top_items.update_layout(
                        title="Top 10 Items by Quantity Sold",
                        xaxis_title="Item Name",
                        yaxis_title="Quantity Sold",
                        height=400
                    )
                    st.plotly_chart(fig_top_items, use_container_width=True)

                # Sales by Category (if category information is available)
                if 'Category' in df.columns and 'Total Sales' in df.columns:
                    st.subheader("📈 Sales by Category")
                    category_sales = df.groupby('Category')['Total Sales'].sum().sort_values(ascending=False)
                    fig_category = go.Figure(data=[go.Bar(x=category_sales.index, y=category_sales.values)])
                    fig_category.update_layout(
                        title="Sales Distribution by Category",
                        xaxis_title="Category",
                        yaxis_title="Total Sales ($)",
                        height=400
                    )
                    st.plotly_chart(fig_category, use_container_width=True)

                # Price Analysis
                if 'Price' in df.columns:
                    st.subheader("💰 Price Analysis")
                    col1, col2 = st.columns(2)
                    with col1:
                        avg_price = df['Price'].mean()
                        st.metric("Average Item Price", f"${avg_price:,.2f}")
                    with col2:
                        price_range = df['Price'].max() - df['Price'].min()
                        st.metric("Price Range", f"${price_range:,.2f}")

                # Raw Data View
                with st.expander("View Raw Menu Data"):
                    st.dataframe(df)

        except Exception as e:
            st.error(f"❌ An unexpected error occurred while processing the menu analysis file: {e}")
    else:
        st.info("Please upload a menu analysis report or import one from Gmail.")

elif page == "AI Bartender":
    st.title("🍹 AI Bartender - Your Mixology Guide")
    st.write("Ask me how to make any drink, and I'll give you the recipe!")

    drink_name = st.text_input("Enter a drink name (e.g., 'Margarita', 'Old Fashioned', 'Mojito'):")

    if st.button("Get Recipe"):
        if drink_name:
            with st.spinner(f"Getting recipe for {drink_name}..."):
                try:
                    prompt = f"""You are an expert bartender. Provide a detailed, step-by-step recipe for making a {drink_name}. Include ingredients with exact measurements, instructions, and any garnish suggestions. Respond in a clear, concise, and friendly manner."""
                    model = genai.GenerativeModel('gemini-1.5-pro-latest')
                    response = model.generate_content(prompt)
                    st.subheader(f"Recipe for {drink_name}:")
                    st.write(response.text)
                except Exception as e:
                    st.error(f"Failed to fetch recipe: {e}")
        else:
            st.warning("Please enter a drink name.")

elif page == "Action Plan & Marketing Strategy":
    st.title("📈 Action Plan & Marketing Strategy")

    if 'processed_sales_df' in st.session_state and 'processed_menu_df' in st.session_state:
        sales_df = st.session_state.processed_sales_df
        menu_df = st.session_state.processed_menu_df

        st.write("### Sales Data Overview")
        st.dataframe(sales_df.head())

        st.write("### Menu Data Overview")
        st.dataframe(menu_df.head())

        st.subheader("Generate Action Plan")
        prompt = st.text_area("Enter your specific needs for the action plan:", 
                              value="Generate a marketing strategy and action plan based on the sales and menu analysis. Focus on increasing sales on weekdays and promoting high-profit margin items.",
                              height=150)
        if st.button("Generate Action Plan"):
            if prompt:
                with st.spinner("Generating action plan..."):
                    # Combine relevant data for Gemini
                    combined_data = f"Sales Data (first 10 rows):\n{sales_df.head(10).to_string()}\n\nMenu Data (first 10 rows):\n{menu_df.head(10).to_string()}\n\nUser Request: {prompt}"
                    
                    try:
                        model = genai.GenerativeModel('gemini-1.5-pro-latest')
                        response = model.generate_content(combined_data)
                        st.write("### Generated Action Plan")
                        st.markdown(response.text)
                        st.download_button(
                            label="Download Action Plan",
                            data=response.text,
                            file_name="Action_Plan_Marketing_Strategy.txt",
                            mime="text/plain"
                        )
                    except Exception as e:
                        st.error(f"Failed to generate action plan: {e}")
            else:
                st.warning("Please enter a prompt for the action plan.")
    else:
        st.info("Please upload and process both Sales and Menu Analysis reports to generate an action plan.")

elif page == "Accounting Assistant":
    accounting_assistant_page()
