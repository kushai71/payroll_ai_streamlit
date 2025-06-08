import imaplib
import email
from email.header import decode_header
import os
from io import BytesIO
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Load environment variables
load_dotenv()
EMAIL_USER = os.getenv("EMAIL_USER") or "kushai7103@gmail.com"
EMAIL_PASS = os.getenv("EMAIL_PASS") or "junv rcsu gavb wgjd"
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))

def normalize(text):
    try:
        return text.encode('utf-8', errors='ignore').decode()
    except:
        return str(text)

def download_attachment_by_filename_or_subject(filter_text, allowed_extensions=(".xlsx", ".csv")):
    mail = None
    try:
        if not os.path.exists("downloads"):
            os.makedirs("downloads")

        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        # Search for all emails (we'll filter by subject/filename later)
        result, data = mail.search(None, "ALL")
        email_ids = data[0].split()

        if not email_ids:
            st.warning(f"No emails found.")
            return None

        # Process emails from newest to oldest
        for mail_id in reversed(email_ids):
            result, msg_data = mail.fetch(mail_id, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = msg.get('subject', '')

            # Check if subject contains the filter text
            if filter_text.lower() in subject.lower():
                st.write(f"Found email by subject: {subject} from {msg.get('from', 'Unknown Sender')}")
                for part in msg.walk():
                    if part.get("Content-Disposition") and "attachment" in part.get("Content-Disposition"):
                        filename = part.get_filename()
                        if filename and filename.lower().endswith(allowed_extensions):
                            filepath = os.path.join("downloads", filename)
                            with open(filepath, "wb") as f:
                                f.write(part.get_payload(decode=True))
                            st.write(f"Found attachment: {filename}")
                            return filepath

            # If not found in subject, check attachment filenames
            for part in msg.walk():
                if part.get("Content-Disposition") and "attachment" in part.get("Content-Disposition"):
                    filename = part.get_filename()
                    if filename and filter_text.lower() in filename.lower() and filename.lower().endswith(allowed_extensions):
                        st.write(f"Found email by filename: {filename} from {msg.get('from', 'Unknown Sender')}")
                        filepath = os.path.join("downloads", filename)
                        with open(filepath, "wb") as f:
                            f.write(part.get_payload(decode=True))
                        st.write(f"Found attachment: {filename}")
                        return filepath

        st.warning(f"No {allowed_extensions} attachment found with '{filter_text}' in subject or filename.")
        return None

    except Exception as e:
        st.error(f"Error fetching email with filter '{filter_text}': {str(e)}")
        return None
    finally:
        if mail:
            try:
                mail.close()
                mail.logout()
            except:
                pass

def fetch_email_with_body_snippet(snippet, allowed_extensions=(".xlsx",)):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        result, data = mail.search(None, "ALL")
        if result != "OK":
            print("Failed to search inbox.")
            return None, None

        mail_ids = data[0].split()[::-1]

        for mail_id in mail_ids:
            result, msg_data = mail.fetch(mail_id, "(RFC822)")
            if result != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Check body for matching snippet
            body_found = False
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain" and not part.get_filename():
                        try:
                            body = part.get_payload(decode=True).decode(errors='ignore')
                            if snippet in body:
                                body_found = True
                                break
                        except:
                            continue
            else:
                try:
                    body = msg.get_payload(decode=True).decode(errors='ignore')
                    if snippet in body:
                        body_found = True
                except:
                    pass

            if not body_found:
                continue

            # Return the first valid attachment
            for part in msg.walk():
                if part.get("Content-Disposition") and "attachment" in part.get("Content-Disposition"):
                    filename = part.get_filename()
                    if filename and filename.lower().endswith(allowed_extensions):
                        return filename, BytesIO(part.get_payload(decode=True))

        return None, None
    except Exception as e:
        print("❌ Error fetching email:", str(e))
        return None, None
    finally:
        if mail:
            try:
                mail.close()
                mail.logout()
            except:
                pass

def download_latest_attachment():
    mail = None  # Initialize mail to None
    try:
        # Ensure 'downloads' directory exists
        if not os.path.exists("downloads"):
            os.makedirs("downloads")

        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        # Search for emails containing the specific text in body
        result, data = mail.search(None, '(BODY "The report Payroll is attached.")')
        email_ids = data[0].split()

        if not email_ids:
            st.warning("No emails found containing 'The report Payroll is attached.'")
            return None

        latest_email_id = email_ids[-1]
        result, data = mail.fetch(latest_email_id, "(RFC822)")
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        st.write(f"Found email: {msg.get('subject', 'No Subject')} from {msg.get('from', 'Unknown Sender')}")

        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue
            filename = part.get_filename()
            if filename and filename.endswith(".xlsx"):
                filepath = os.path.join("downloads", filename) # Save to downloads folder
                with open(filepath, "wb") as f:
                    f.write(part.get_payload(decode=True))
                st.write(f"Found Excel attachment: {filename}")
                return filepath

        st.warning("No Excel attachment found in the email.")
        return None

    except Exception as e:
        st.error(f"Error fetching email: {str(e)}")
        return None
    finally:
        if mail:
            try:
                mail.close()
                mail.logout()
            except:
                pass

def download_latest_sales_report():
    mail = None
    try:
        if not os.path.exists("downloads"):
            os.makedirs("downloads")

        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        result, data = mail.search(None, '(BODY "The report History Sales Overview is attached.")')
        email_ids = data[0].split()

        if not email_ids:
            st.warning("No emails found containing 'The report History Sales Overview is attached.'")
            return None

        latest_email_id = email_ids[-1]
        result, data = mail.fetch(latest_email_id, "(RFC822)")
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        st.write(f"Found sales email: {msg.get('subject', 'No Subject')} from {msg.get('from', 'Unknown Sender')}")

        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue
            filename = part.get_filename()
            if filename and filename.lower().endswith(".xlsx"):
                filepath = os.path.join("downloads", filename)
                with open(filepath, "wb") as f:
                    f.write(part.get_payload(decode=True))
                st.write(f"Found Excel sales attachment: {filename}")
                return filepath

        st.warning("No Excel sales attachment found in the email.")
        return None

    except Exception as e:
        st.error(f"Error fetching sales email: {str(e)}")
        return None
    finally:
        if mail:
            try:
                mail.close()
                mail.logout()
            except:
                pass

def generate_financial_summary_email(summary_text: str, recipient_email: str, subject: str = "Financial Summary Report", email_body_content: str = "") -> bool:
    """
    Generates and sends an email with the financial summary in a simple paragraph format.
    """
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_USER
        msg['To'] = recipient_email
        msg['Subject'] = subject

        # Create a preview by taking the first 200 characters
        # Use the provided email_body_content or default to summary_text if not provided
        actual_body_for_preview = email_body_content if email_body_content else summary_text
        preview = actual_body_for_preview[:200] + "..." if len(actual_body_for_preview) > 200 else actual_body_for_preview

        # Format the email body in simple paragraphs, using the provided content or default
        final_email_body = f"""Dear Recipient,

{email_body_content if email_body_content else "Here is your financial summary report:"}

{summary_text}

Best regards,
Your Payroll AI Assistant

---
Preview: {preview}
"""

        msg.attach(MIMEText(final_email_body, 'plain'))

        # Use SMTP settings for sending emails
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)

        st.success(f"Financial summary email sent successfully to {recipient_email}!")
        return True
    except Exception as e:
        st.error(f"Failed to send financial summary email: {e}")
        return False

def download_latest_menu_sales_report():
    """Downloads the latest menu sales analysis Excel file from email."""
    st.info("Attempting to download latest menu sales report...")
    filter_text = "The report Menu Sales Analysis is attached."
    filename, file_data = fetch_email_with_body_snippet(filter_text, allowed_extensions=(".xlsx",))
    if filename and file_data:
        # Ensure downloads directory exists
        if not os.path.exists("downloads"):
            os.makedirs("downloads")
        
        # Save the file
        filepath = os.path.join("downloads", filename)
        with open(filepath, "wb") as f:
            f.write(file_data.getvalue())
        st.success(f"Downloaded menu sales report: {filename}")
        return filepath
    return None
