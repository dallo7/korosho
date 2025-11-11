import dash
from dash import dcc, html, Input, Output, State, dash_table, callback_context, ALL
import dash_bootstrap_components as dbc
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime
import base64
import io
import random
import json
import plotly.express as px
from contextlib import contextmanager
from fpdf import FPDF

# --- CONSTANTS ---
VERIFICATION_STEPS = [
    "Initiating Inter-Bank Verification API...",
    "Querying NBC Network for account status...",
    "Matching farmer details against bank records...",
    "Identifying and flagging inaccurate accounts...",
    "Verification Complete. Results updated."
]

PAYMENT_STEPS = [
    "Initiating Capital Pay secure engine...",
    "Pre-processing and validating verified data...",
    "Connecting to inter-bank payment gateway...",
    "Securely settling respective farmers' accounts...",
    "Transactions successful! Finalizing report..."
]

COST_PER_ROW_USD = 1.50
EXCHANGE_RATE_TSH_TO_USD = 2500
PAYMENT_COMMISSION_RATE = 0.025

COOPERATIVE_UNIONS = ['CORECU Ltd', 'LMCU Ltd', 'TAMCU Ltd', 'RUNALI Ltd', 'MAMCU Ltd', 'TANECU Ltd']
FARM_PRODUCTS = ['Peas', 'Sesame', 'Cashew']

ASSET_URLS = {
    'BACKGROUND1': '/assets/BACKGROUND1.png',
    'BACKGROUND2': '/assets/BACKGROUND2.png',
    'CIRCLE': '/assets/CIRCLE.png',
    'CP_LOGO': '/assets/CP LOGO.png',
    'KOROSHO_LOGO': '/assets/KOROSHO LOGO.png',
    'NBC_LOGO': '/assets/NBC LOGO.png'
}

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
app.title = "Farmers Account Verification Portal"
server = app.server


# PDF Generation (FPDF2)
class PDF(FPDF):
    """Custom FPDF class to create a standard header for documents."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load all three logo paths
        self.cp_logo_path = ASSET_URLS['CP_LOGO'].lstrip('/')
        self.korosho_logo_path = ASSET_URLS['KOROSHO_LOGO'].lstrip('/')
        self.nbc_logo_path = ASSET_URLS['NBC_LOGO'].lstrip('/')

        self.coop_name = ""
        self.doc_type = "INVOICE"
        self.ref = ""
        self.date_str = ""

    def set_doc_details(self, coop_name, doc_type, ref, date_str):
        self.coop_name = coop_name
        self.doc_type = doc_type.upper()
        self.ref = ref
        self.date_str = date_str

    def header(self):
        # --- 3-LOGO HEADER (Adjusted Spacing/Fonts) ---
        self.set_y(8)  # Start header content a bit higher

        # Left Logos
        try:
            self.image(self.cp_logo_path, 10, self.get_y(), 33)
        except Exception:
            self.cell(40, 10, '[CP Logo]')
        try:
            self.image(self.korosho_logo_path, 45, self.get_y(), 12)
        except Exception:
            self.cell(60)
            self.cell(40, 10, '[K Logo]')

        # Right Logo
        try:
            self.image(self.nbc_logo_path, 170, self.get_y(), 30)
        except Exception:
            self.cell(0, 10, '[NBC Logo]', 0, 0, 'R')

        # Main Title (Centered between the logos, but right-aligned in its cell)
        self.set_font('Arial', 'B', 24)
        self.set_text_color(0, 74, 153)
        self.set_xy(80, 10)  # Positioned to fit between left logos and NBC logo
        self.cell(90, 10, f'VERIFICATION {self.doc_type}', 0, 1, 'R')  # Adjusted width

        # Removed: 'Capital Pay / KOROSHO-JE / NBC' text directly under the title

        self.set_line_width(0.5)
        self.set_draw_color(0, 74, 153)
        self.line(10, 28, 200, 28)  # Adjusted line position
        self.ln(20)  # Increase spacing after the line

    def footer(self):
        self.set_y(-15)  # Position 1.5 cm from bottom

        # Draw a horizontal line
        self.set_line_width(0.2)
        self.set_draw_color(128)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2)  # Move down a bit

        # Page Number (Center)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

        # --- "Powered by" + Logo (Right) ---
        text = "Powered by "
        text_width = self.get_string_width(text) + 1  # Add padding
        logo_width = 10

        # Set cursor X position to the start of the right-aligned block
        self.set_x(200 - (text_width + logo_width))
        self.set_font('Arial', '', 8)  # Regular font
        self.set_text_color(0, 0, 0)  # Black text
        self.cell(text_width, 10, text, 0, 0, 'R')

        try:
            # Place image right after the text cell
            self.image(self.cp_logo_path, self.get_x(), self.get_y() + 2.5, logo_width)
        except Exception:
            pass

    def add_bill_to_section(self):
        """Helper to add the 'BILL TO' and 'INVOICE #' block."""

        current_y = self.get_y()

        # --- Column 1: BILL TO (Left-Aligned) ---
        self.set_font('Arial', '', 9)
        self.set_text_color(119, 119, 119)
        self.cell(100, 5, 'BILL TO', 0, 1, 'L')

        self.set_font('Arial', 'B', 12)
        self.set_text_color(0, 0, 0)
        self.cell(100, 7, self.coop_name, 0, 1, 'L')

        # --- Column 2: RECEIPT DETAILS (Right-Aligned) ---
        self.set_y(current_y)

        # --- Row 1: Receipt # ---
        self.set_x(130)
        self.set_font('Arial', '', 9)
        self.set_text_color(119, 119, 119)
        self.cell(30, 7, f'{self.doc_type} #:', 0, 0, 'R')

        self.set_font('Arial', 'B', 11)
        self.set_text_color(0, 0, 0)
        self.cell(40, 7, self.ref, 0, 1, 'L')

        # --- Row 2: Date ---
        self.set_x(130)
        self.set_font('Arial', '', 9)
        self.set_text_color(119, 119, 119)
        self.cell(30, 7, 'DATE:', 0, 0, 'R')

        self.set_font('Arial', 'B', 11)
        self.set_text_color(0, 0, 0)
        self.cell(40, 7, self.date_str, 0, 1, 'L')

        self.ln(10)


def generate_service_invoice_pdf(ref, date, coop_name, rows, amount, status):
    """Generates the Verification Invoice PDF using fpdf2."""
    pdf = PDF('P', 'mm', 'A4')
    pdf.set_doc_details(coop_name, "INVOICE", ref, date)
    pdf.add_page()
    pdf.add_bill_to_section()

    pdf.set_font('Arial', 'B', 9)
    pdf.set_fill_color(244, 244, 244)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(120, 8, 'Description', 1, 0, 'L', fill=True)
    pdf.cell(20, 8, 'Quantity', 1, 0, 'R', fill=True)
    pdf.cell(25, 8, 'Unit Price', 1, 0, 'R', fill=True)
    pdf.cell(25, 8, 'Total', 1, 1, 'R', fill=True)

    pdf.set_font('Arial', '', 10)
    pdf.cell(120, 10, 'Bank Account Verification Service', 1, 0, 'L')
    pdf.cell(20, 10, f'{rows:,}', 1, 0, 'R')
    pdf.cell(25, 10, f'${COST_PER_ROW_USD:,.2f}', 1, 0, 'R')
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(25, 10, f'${amount:,.2f}', 1, 1, 'R')
    pdf.ln(10)

    current_y = pdf.get_y()
    pdf.set_font('Arial', 'B', 14)
    if status == "paid":
        pdf.set_fill_color(40, 167, 69)  # Green
        pdf.set_text_color(255, 255, 255)
        status_text = "PAID"
    else:
        pdf.set_fill_color(255, 193, 7)  # Yellow
        pdf.set_text_color(51, 51, 51)
        status_text = "UNPAID"
    pdf.cell(40, 10, status_text, 0, 0, 'C', fill=True)

    pdf.set_y(current_y)
    pdf.set_x(120)
    pdf.set_font('Arial', '', 14)
    pdf.set_text_color(85, 85, 85)
    pdf.cell(45, 10, 'AMOUNT PAYABLE', 0, 0, 'R')  # Changed from 'TOTAL DUE'
    pdf.set_font('Arial', 'B', 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(35, 10, f'${amount:,.2f}', 0, 1, 'R')
    pdf.set_line_width(0.5)
    pdf.set_draw_color(170, 170, 170)
    pdf.line(120, pdf.get_y(), 200, pdf.get_y())

    # --- PAYMENT INSTRUCTIONS BLOCK ---
    pdf.set_y(pdf.get_y() + 15)  # Move down from the total
    current_y = pdf.get_y()

    # Column 1: Payment Instructions
    pdf.set_font('Arial', 'B', 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(80, 7, "Payment Instructions:", 0, 1, 'L')

    pdf.set_font('Arial', '', 9)
    pdf.set_text_color(51, 51, 51)
    pdf.multi_cell(80, 5,
                   "Please make payment in USD to the account below. "
                   "Ensure to include the Invoice Reference number in your payment details.",
                   0, 'L'
                   )

    # Column 2: Bank Details (in a shaded box)
    pdf.set_xy(100, current_y)
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(244, 244, 244)
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.3)

    pdf.cell(100, 7, "Bank Details (USD Account)", 1, 1, 'L', fill=True)
    pdf.set_x(100)
    pdf.set_font('Arial', '', 9)
    pdf.cell(40, 6, "Beneficiary:", 'L', 0, 'L')
    pdf.cell(60, 6, "Capital Pay / KOROSHO-JE", 'R', 1, 'L')
    pdf.set_x(100)
    pdf.cell(40, 6, "Bank Name:", 'L', 0, 'L')
    pdf.cell(60, 6, "NBC Tanzania", 'R', 1, 'L')
    pdf.set_x(100)
    pdf.cell(40, 6, "Account Number:", 'L', 0, 'L')
    pdf.cell(60, 6, "0123 4567 8901 (USD)", 'R', 1, 'L')
    pdf.set_x(100)
    pdf.cell(40, 6, "SWIFT Code:", 'LB', 0, 'L')
    pdf.cell(60, 6, "NLCBTZXXXX", 'RB', 1, 'L')

    # --- NEW DISCLAIMER BLOCK ---
    pdf.set_y(-40)  # Position 4cm from bottom, above footer
    pdf.set_font('Arial', 'I', 8)
    pdf.set_text_color(128)
    pdf.multi_cell(0, 4,
                   "This is a computer-generated invoice and is valid without a signature. "
                   "Please pay the 'Amount Payable' to the bank details provided. "
                   "This invoice is for verification services only.",
                   0, 'C'
                   )
    pdf.ln(3)
    pdf.set_font('Arial', 'B', 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 5, "Thank you for your business!", 0, 1, 'C')
    # --- END OF NEW BLOCK ---

    return pdf.output(dest='S').encode('latin1')


def generate_payment_receipt_pdf(ref, date, coop_name, total_tsh, commission_usd, status="unpaid"):
    """Generates the Payment Receipt PDF using fpdf2."""
    pdf = PDF('P', 'mm', 'A4')
    pdf.set_doc_details(coop_name, "RECEIPT", ref, date)
    pdf.add_page()
    pdf.add_bill_to_section()

    pdf.set_fill_color(232, 245, 233)
    pdf.set_text_color(21, 87, 36)
    pdf.set_draw_color(212, 237, 218)
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 8, 'This receipt confirms fees associated with the processing of farmer payments.', 1, 'L',
                   fill=True)
    pdf.ln(5)

    pdf.set_font('Arial', 'B', 9)
    pdf.set_fill_color(244, 244, 244)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(130, 8, 'Description', 1, 0, 'L', fill=True)
    pdf.cell(20, 8, 'Currency', 1, 0, 'C', fill=True)
    pdf.cell(40, 8, 'Amount', 1, 1, 'R', fill=True)

    pdf.set_font('Arial', '', 10)
    pdf.cell(130, 10, 'Total Farmer Payouts Processed', 1, 0, 'L')
    pdf.cell(20, 10, 'TSH', 1, 0, 'C')
    pdf.cell(40, 10, f'{total_tsh:,.2f}', 1, 1, 'R')

    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(232, 245, 233)
    pdf.cell(130, 10, f'Payment Processing Fee ({PAYMENT_COMMISSION_RATE * 100}%)', 1, 0, 'L', fill=True)
    pdf.cell(20, 10, 'USD', 1, 0, 'C', fill=True)
    pdf.cell(40, 10, f'${commission_usd:,.2f}', 1, 1, 'R', fill=True)
    pdf.ln(10)

    # --- NEW STATUS BLOCK & AMOUNT PAYABLE (mimicking service invoice) ---
    current_y = pdf.get_y()
    pdf.set_font('Arial', 'B', 14)
    if status == "paid":
        pdf.set_fill_color(40, 167, 69)  # Green
        pdf.set_text_color(255, 255, 255)
        status_text = "PAID"
    else:
        pdf.set_fill_color(255, 193, 7)  # Yellow
        pdf.set_text_color(51, 51, 51)
        status_text = "UNPAID"
    pdf.cell(40, 10, status_text, 0, 0, 'C', fill=True)

    pdf.set_y(current_y)
    pdf.set_x(120)
    pdf.set_font('Arial', '', 14)
    pdf.set_text_color(85, 85, 85)
    pdf.cell(45, 10, 'AMOUNT PAYABLE (USD)', 0, 0, 'R')

    pdf.set_font('Arial', 'B', 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(35, 10, f'${commission_usd:,.2f}', 0, 1, 'R')
    pdf.set_line_width(0.5)
    pdf.set_draw_color(170, 170, 170)
    pdf.line(120, pdf.get_y(), 200, pdf.get_y())

    # --- DISCLAIMER & THANK YOU (Adjusted Position) ---
    pdf.set_y(pdf.get_y() + 15)  # Move down from the total
    pdf.set_font('Arial', 'I', 8)
    pdf.set_text_color(128)
    pdf.multi_cell(0, 4,
                   "This receipt is computer-generated and confirms the successful processing of commission fees for farmer payouts. "
                   "This document is not a tax invoice for the farmer payouts themselves. "
                   "All fees are final.",
                   0, 'C'
                   )
    pdf.ln(3)
    pdf.set_font('Arial', 'B', 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 5, "Thank you for your partnership!", 0, 1, 'C')
    # --- END OF UPDATED ELEMENTS ---

    return pdf.output(dest='S').encode('latin1')


def create_invoice_modal_layout(ref, date, coop_name, rows, amount, status):
    """Creates the Dash layout for the service invoice modal."""
    status_color = "success" if status == "paid" else "warning"
    return [
        dbc.ModalHeader(f"Download Invoice: {ref}"),
        dbc.ModalBody([
            dbc.Alert(f"You are about to download the invoice for {coop_name}.", color="info"),
            html.Ul([
                html.Li(f"Reference: {ref}"),
                html.Li(f"Date: {date}"),
                html.Li(f"Rows: {rows:,}"),
                html.Li(f"Amount: ${amount:,.2f}"),
                html.Li(["Status: ", dbc.Badge(status.upper(), color=status_color)]),
            ])
        ]),
        dbc.ModalFooter([
            dbc.Button("Close", id={'type': 'admin-download-modal-close', 'index': 1}, color="secondary"),
            dbc.Button("Download Invoice (PDF)", id="download-pdf-button", color="primary")
        ])
    ]


def create_receipt_modal_layout(ref, date, coop_name, total_tsh, commission_usd):
    """Creates the Dash layout for the payment receipt modal."""
    return [
        dbc.ModalHeader(f"Download Receipt: {ref}"),
        dbc.ModalBody([
            dbc.Alert(f"You are about to download the payment receipt for {coop_name}.", color="info"),
            html.Ul([
                html.Li(f"Reference: {ref}"),
                html.Li(f"Date: {date}"),
                html.Li(f"Total Payout Processed: TSH {total_tsh:,.2f}"),
                html.Li(f"Commission Fee Paid: ${commission_usd:,.2f}"),
            ])
        ]),
        dbc.ModalFooter([
            dbc.Button("Close", id={'type': 'admin-download-modal-close', 'index': 2}, color="secondary"),
            dbc.Button("Download Receipt (PDF)", id="download-pdf-button", color="primary")
        ])
    ]


# Utility & DB Functions

@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect('farmers_payment_module.db')
    try:
        yield conn
    finally:
        conn.close()


def update_approver_credentials(user_id, new_password, new_passphrase, new_pin):
    """Updates password, passphrase, and PIN for an approver."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        hashed_password = hashlib.sha256(new_password.encode()).hexdigest()
        hashed_passphrase = hashlib.sha256(new_passphrase.encode()).hexdigest()
        hashed_pin = hashlib.sha256(new_pin.encode()).hexdigest()
        cursor.execute(
            "UPDATE users SET password = ?, passphrase = ?, pin = ?, temp_password = NULL WHERE id = ?",
            (hashed_password, hashed_passphrase, hashed_pin, user_id)
        )
        conn.commit()


def check_user_passphrase(user_id, passphrase_attempt):
    """Checks if the provided passphrase matches the one in the DB."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT passphrase FROM users WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        if not result:
            return False
        stored_hash = result[0]
        hashed_attempt = hashlib.sha256(passphrase_attempt.encode()).hexdigest()
        return stored_hash == hashed_attempt


def check_user_pin(user_id, pin_attempt):
    """Checks if the provided PIN matches the one in the DB."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT pin FROM users WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        if not result:
            return False
        stored_hash = result[0]
        hashed_attempt = hashlib.sha256(pin_attempt.encode()).hexdigest()
        return stored_hash == hashed_attempt


def serialize_session(session_data):
    if session_data is None: return None
    s = json.dumps(session_data)
    key = 42
    obfuscated = "".join(chr(ord(c) ^ key) for c in s)
    return obfuscated


def deserialize_session(obfuscated_data):
    if obfuscated_data is None: return None
    try:
        key = 42
        s = "".join(chr(ord(c) ^ key) for c in obfuscated_data)
        return json.loads(s)
    except Exception:
        return None


def deserialize_session(obfuscated_data):
    if obfuscated_data is None: return None
    try:
        key = 42
        s = "".join(chr(ord(c) ^ key) for c in obfuscated_data)
        return json.loads(s)
    except Exception:
        return None


def log_activity(user_id, action, details=""):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT cooperative_name FROM users WHERE id = ?", (user_id,))
        cooperative_name = cursor.fetchone()
        cooperative_name = cooperative_name[0] if cooperative_name else "System"

        cursor.execute(
            "INSERT INTO activity_logs (timestamp, user_id, cooperative_name, action, details) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(), user_id, cooperative_name, action, details))
        conn.commit()


def authenticate_user(username, password):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, password, role, cooperative_name, industry FROM users WHERE username = ?",
                       (username,))
        user = cursor.fetchone()

    if user and user[1] == hashlib.sha256(password.encode()).hexdigest():
        return {"id": user[0], "username": username, "role": user[2], "cooperative_name": user[3], "industry": user[4]}
    return None


def create_invoice(conn, batch_id, cooperative_name, row_count, timestamp):
    amount_usd = row_count * COST_PER_ROW_USD
    cursor = conn.cursor()

    coop_short_name = cooperative_name.split()[0].upper()
    cursor.execute("SELECT COUNT(*) FROM invoices WHERE cooperative_name = ?", (cooperative_name,))
    next_id = cursor.fetchone()[0] + 1
    invoice_ref = f"{coop_short_name}-{next_id:04d}-{datetime.now().year}"

    cursor.execute(
        "INSERT INTO invoices (batch_id, cooperative_name, submission_timestamp, row_count, amount_usd, status, invoice_reference) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (batch_id, cooperative_name, timestamp, row_count, amount_usd, 'unpaid', invoice_ref)
    )
    return amount_usd, invoice_ref


def create_payment_commission(conn, batch_id, cooperative_name, total_amount_tsh):
    commission_tsh = total_amount_tsh * PAYMENT_COMMISSION_RATE
    commission_usd = commission_tsh / EXCHANGE_RATE_TSH_TO_USD
    coop_short = cooperative_name.split()[0].upper()
    ref_num = f"CP-PAY-{coop_short}-{batch_id}"

    cursor = conn.cursor()
    cursor.execute(
        "UPDATE invoices SET payment_commission_usd = ?, payment_commission_reference = ? WHERE batch_id = ?",
        (commission_usd, ref_num, batch_id)
    )
    return commission_usd, ref_num


def simulate_bank_verification(df):
    if not {'farmer_name', 'bank_name', 'account_number', 'amount'}.issubset(df.columns):
        return None
    df['verification_status'] = 'verified'
    df['verification_reason'] = None
    reasons = ["Account Closed", "Name Mismatch", "Invalid Bank Code", "System Check Failed"]
    for index in df.index:
        if random.random() < 0.15:  # 15% chance of failure
            df.loc[index, 'verification_status'] = 'failed'
            df.loc[index, 'verification_reason'] = random.choice(reasons)
    return df


def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS users")
        cursor.execute("DROP TABLE IF EXISTS submission_batches")
        cursor.execute("DROP TABLE IF EXISTS farmer_payments")
        cursor.execute("DROP TABLE IF EXISTS payment_history")
        cursor.execute("DROP TABLE IF EXISTS activity_logs")
        cursor.execute("DROP TABLE IF EXISTS invoices")

        cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                cooperative_name TEXT,
                industry TEXT,
                temp_password TEXT,
                passphrase TEXT,
                pin TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE submission_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cooperative_id INTEGER,
                filename TEXT,
                record_count INTEGER,
                total_amount REAL,
                submission_timestamp TIMESTAMP,
                status TEXT,
                admin_notes TEXT,
                cooperative_notes TEXT,
                FOREIGN KEY (cooperative_id) REFERENCES users (id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE farmer_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER,
                farmer_name TEXT NOT NULL,
                bank_name TEXT NOT NULL,
                account_number TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending', 
                verification_status TEXT DEFAULT 'unverified', 
                verification_reason TEXT,
                failure_reason TEXT,
                FOREIGN KEY (batch_id) REFERENCES submission_batches (id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER UNIQUE NOT NULL,
                cooperative_name TEXT,
                submission_timestamp TIMESTAMP,
                row_count INTEGER,
                amount_usd REAL,
                status TEXT DEFAULT 'unpaid',
                payment_date TIMESTAMP,
                invoice_reference TEXT,
                payment_commission_usd REAL,
                payment_commission_reference TEXT,
                FOREIGN KEY (batch_id) REFERENCES submission_batches (id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE payment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER,
                cooperative_name TEXT,
                filename TEXT,
                record_count INTEGER,
                total_amount REAL,
                processing_timestamp TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP,
                user_id INTEGER,
                cooperative_name TEXT,
                action TEXT,
                details TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # --- Passwords and Auth ---
        admin_pass_unhashed = "admin123"
        coop_pass_unhashed = "coop123"
        admin_password = hashlib.sha256(admin_pass_unhashed.encode()).hexdigest()
        coop_password = hashlib.sha256(coop_pass_unhashed.encode()).hexdigest()

        # --- Default Auth Credentials ---
        admin_passphrase_unhashed = "adminpass"
        admin_pin_unhashed = "987654"
        coop_passphrase_unhashed = "cooppass"
        coop_pin_unhashed = "123456"

        admin_passphrase = hashlib.sha256(admin_passphrase_unhashed.encode()).hexdigest()
        admin_pin = hashlib.sha256(admin_pin_unhashed.encode()).hexdigest()
        coop_passphrase = hashlib.sha256(coop_passphrase_unhashed.encode()).hexdigest()
        coop_pin = hashlib.sha256(coop_pin_unhashed.encode()).hexdigest()

        users_to_add = [
            # (username, password, role, cooperative_name, industry, temp_password, passphrase, pin)
            ("admin", admin_password, "admin", "Farmers Payment Module Admin", "Administration", admin_pass_unhashed,
             admin_passphrase, admin_pin),
            ("corecu_data", coop_password, "coop_uploader", "CORECU Ltd", "Peas", coop_pass_unhashed, None, None),
        ]

        for union_name in COOPERATIVE_UNIONS:
            approver_username = f"{union_name.split()[0].lower()}_finance"
            default_product = "Peas" if union_name == 'CORECU Ltd' else "Administration"
            users_to_add.append(
                (approver_username, coop_password, "coop_approver", union_name, default_product, coop_pass_unhashed,
                 coop_passphrase, coop_pin))

        cursor.execute("DELETE FROM users")
        for user in users_to_add:
            cursor.execute(
                "INSERT INTO users (username, password, role, cooperative_name, industry, temp_password, passphrase, pin) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                user)

        conn.commit()


# Layout Definitions

def create_change_password_modal():
    return dbc.Modal([
        dbc.ModalHeader("Change Finance Manager Credentials"),
        dbc.ModalBody([
            html.P(
                "Set a new, secure password, passphrase, and PIN for your approver account. All fields are required."),
            dbc.Input(id="new-password", placeholder="Enter New Password (min 6 chars)", type="password",
                      className="mb-3"),
            dbc.Input(id="confirm-password", placeholder="Confirm New Password", type="password", className="mb-3"),
            html.Hr(),
            dbc.Input(id="new-passphrase", placeholder="Enter New Passphrase (min 8 chars)", type="password",
                      className="mb-3"),
            dbc.Input(id="new-pin", placeholder="Enter 6-Digit PIN", type="password", className="mb-3", maxLength=6),
            html.Div(id="password-change-alert", className="mt-3")
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="password-close-button", color="secondary", className="me-auto"),
            dbc.Button("Save New Credentials", id="password-save-button", color="primary")
        ])
    ], id="password-modal", is_open=False, backdrop="static")


def create_pin_pad_layout():
    """Helper function to create the dialpad layout."""
    buttons = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'C', '0', '<']
    rows = []
    for i in range(0, len(buttons), 3):
        row_buttons = buttons[i:i + 3]
        rows.append(
            dbc.Row([
                dbc.Col(
                    dbc.Button(
                        b, id={'type': 'pin-pad-button', 'index': b},
                        color="light",
                        className="w-100",
                        size="lg",
                        outline=(b in ['C', '<'])
                    ),
                ) for b in row_buttons
            ], className="mb-2")
        )
    return html.Div(rows)


def create_payment_auth_modal():
    """
    Creates the reusable two-step payment authorization modal (Passphrase -> PIN).
    """
    return dbc.Modal(
        [
            dbc.ModalHeader("Secure Payment Authorization"),
            dbc.ModalBody(
                [
                    dcc.Store(id='payment-auth-step-store', data='passphrase'),
                    dcc.Store(id='pin-input-store', data=''),
                    html.Div(id='auth-modal-alert'),

                    # == Step 1: Passphrase ==
                    html.Div(
                        id='passphrase-step',
                        children=[
                            dbc.Label("Step 1: Enter Passphrase"),
                            dbc.Input(id="auth-passphrase-input", type="password",
                                      placeholder="Enter your passphrase..."),
                            html.Div(id='auth-passphrase-alert', className="mt-2"),
                        ],
                    ),

                    # == Step 2: PIN ==
                    html.Div(
                        id='pin-step',
                        style={'display': 'none'},
                        children=[
                            dbc.Label("Step 2: Enter 6-Digit PIN"),
                            # This is now just a display
                            dbc.Input(id="auth-pin-input", type="password", placeholder="PIN",
                                      maxLength=6, readonly=True, className="text-center fw-bold fs-4 mb-3",
                                      style={'letterSpacing': '0.5em'}),
                            # The dialpad
                            create_pin_pad_layout(),
                            html.Div(id='auth-pin-alert', className="mt-2"),
                        ],
                    ),
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("Cancel", id="auth-cancel-button", color="secondary"),
                    dbc.Button("Next", id="auth-next-button", color="primary"),
                    dbc.Button("Authorize Payment", id="auth-authorize-button", color="success",
                               style={'display': 'none'}),
                ]
            ),
        ],
        id="payment-auth-modal",
        is_open=False,
        backdrop="static",
    )


def create_landing_layout():
    return dbc.Container(
        style={
            'backgroundImage': f'url("{ASSET_URLS["BACKGROUND1"]}")',
            'backgroundSize': 'cover',
            'backgroundPosition': 'center',
            'minHeight': '100vh', 'padding': '0', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
            'position': 'relative', 'color': 'white', 'overflow': 'hidden'
        },
        fluid=True,
        children=[
            html.Div(style={'position': 'absolute', 'top': 0, 'left': 0, 'right': 0, 'bottom': 0,
                            'backgroundColor': 'rgba(0, 0, 0, 0.4)'}),
            html.Div(
                style={'position': 'absolute', 'top': '30px', 'left': '50px', 'right': '50px', 'zIndex': 10,
                       'display': 'flex', 'alignItems': 'center'},
                children=[
                    html.Img(src=ASSET_URLS['CP_LOGO'], style={'height': '40px'}),
                    html.Div(style={'marginLeft': 'auto'}),
                    html.Img(src=ASSET_URLS['KOROSHO_LOGO'], style={'height': '40px', 'borderRadius': '50%'})
                ]
            ),

            dbc.Row(
                [
                    # Column 1: The Text
                    dbc.Col(style={'zIndex': 10}, children=[
                        html.H1("Empowered",
                                style={'fontSize': '3em', 'fontWeight': '300', 'color': '#fff',
                                       'marginBottom': '-10px'}),
                        html.H1("Cooperative Governance",
                                style={'fontSize': '4em', 'fontWeight': '700', 'color': '#fff',
                                       'marginBottom': '20px'}),
                        html.P(
                            "We are a premier Cooperative Joint Enterprise dedicated in providing high-quality Cashew and other produce farming and marketing services in Tanzania.",
                            style={'fontSize': '1.1em', 'maxWidth': '500px', 'color': '#ccc', 'marginBottom': '30px'}),
                        dbc.Button("Get Started", id="get-started-button", color="light", size="lg",
                                   className="text-dark fw-bold")
                    ], width=12, lg=6),

                    # Column 2: The Circle Image
                    dbc.Col(
                        style={'zIndex': 10},
                        children=[
                            html.Img(
                                src=ASSET_URLS['CIRCLE'],
                                style={
                                    'width': '100%',
                                    'maxWidth': '450px',
                                    'opacity': 0.9,

                                    # --- STYLE UPDATE ---
                                    'position': 'relative',
                                    'left': '30px',
                                    'bottom': '70px'  # Moved up again (was 50px)
                                    # --- END OF UPDATE ---
                                }
                            )
                        ],
                        width=12,
                        lg=6,
                        className="d-none d-lg-flex align-items-center justify-content-center"
                    )
                ],
                justify="start",
                className="h-100 align-items-center px-5"
            )
        ]
    )


def create_login_layout():
    return dbc.Container(
        style={'backgroundImage': f'url("{ASSET_URLS["BACKGROUND2"]}")', 'backgroundSize': 'cover',
               'backgroundPosition': 'center', 'minHeight': '100vh', 'padding': '0', 'display': 'flex',
               'flexDirection': 'column', 'alignItems': 'center', 'position': 'relative', 'color': 'white',
               'overflow': 'hidden'},
        fluid=True,
        children=[
            html.Div(
                style={'width': '100%', 'padding': '20px 50px', 'backgroundColor': 'rgba(0, 0, 0, 0.6)', 'zIndex': 10},
                children=[
                    html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': '15px'}, children=[
                        html.Img(src=ASSET_URLS['KOROSHO_LOGO'],
                                 style={'height': '50px', 'borderRadius': '50%', 'border': '2px solid white'}),
                        html.H2("Sign in to KOROSHO-JE Farmers account verification portal.", className="mb-0",
                                style={'fontSize': '1.5em', 'fontWeight': '600', 'color': 'white'})
                    ])
                ]),
            dbc.Row(dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H3("Secure Sign In", className="text-center mb-4 text-white"),
                    dbc.Input(id="login-username", placeholder="Username", type="text", className="mb-3"),
                    dbc.Input(id="login-password", placeholder="Password", type="password", className="mb-3"),
                    html.Div(id="login-alert-placeholder", className="mt-3"),
                    dbc.Button("Login", id="login-button", color="success", className="w-100 mb-2"),
                    dbc.Button("Back to Home", id="go-to-landing-button", color="link",
                               className="w-100 text-white mb-2"),
                ], style={'backgroundColor': 'rgba(20, 20, 20, 0.8)', 'borderRadius': '0.3rem', 'padding': '2.5rem'})
            ], className="shadow-lg border-0"),

                # This sets the width to 50% (6/12) on medium and large screens.
                width={'size': 10, 'sm': 8, 'md': 6, 'lg': 6}

            ), justify="center",
                className="flex-grow-1 align-items-center"),
        ]
    )


def create_branded_navbar(brand_text, is_admin=False):
    logo_color = "primary" if is_admin else "success"
    return dbc.NavbarSimple(
        brand=html.Div(
            [
                html.Span(brand_text, className="me-2"),
                dbc.Badge(html.Span(["Powered by ", html.B("Capital Pay")]),
                          color="light" if is_admin else "info", className="ms-2 text-dark fw-bold")
            ],
            className="d-flex align-items-center"
        ),
        children=[
            dbc.Button("Logout", id="logout-button", color="light", outline=True)
        ],
        color=logo_color,
        dark=True
    )


def create_verification_layout(df, display_filename, coop_note="", reverify=False):
    """Helper function to create the data verification table layout."""
    verified_count = (df['verification_status'] == 'verified').sum()
    failed_count = (df['verification_status'] == 'failed').sum()

    table_columns = [
        {'name': i.replace('_', ' ').title(), 'id': i, 'editable': (i in ['farmer_name', 'account_number'])}
        for i in df.columns if i not in ['status', 'failure_reason']
    ]

    style_data_conditional = [
                                 {'if': {'filter_query': '{verification_status} eq "verified"'},
                                  'backgroundColor': '#e8f5e9', },
                                 {'if': {'filter_query': '{verification_status} eq "failed"'},
                                  'backgroundColor': '#ffebee', 'color': '#d32f2f', 'fontWeight': 'bold'},
                             ] + [
                                 {'if': {'column_id': c, 'filter_query': '{verification_status} eq "failed"'},
                                  'backgroundColor': '#fff8e1', }
                                 for c in ['farmer_name', 'account_number']
                             ]

    # This creates the list (array) that Dash expects
    tooltip_data = [
        {
            column: {
                'value': row['verification_reason'] if row['verification_status'] == 'failed' else '',
                'type': 'markdown'}
            for column in df.columns
        } for row in df.to_dict('records')
    ]

    if reverify:
        alert_header = "Re-Verification Complete!"
        alert_color = "success" if failed_count == 0 else "warning"
        alert_fail_text = f"Rejected Accounts (Needs Correction): {failed_count:,}. Please correct remaining errors."
        alert_fail_class = "mb-1 " + ("text-danger" if failed_count > 0 else "text-success")
    else:
        alert_header = "Verification Results (Immediate Check)"
        alert_color = "info"
        alert_fail_text = f"Rejected Accounts (Needs Correction): {failed_count:,}. Edit the highlighted cells below and click 'Re-Verify' to fix."
        alert_fail_class = "mb-1 text-danger"

    return html.Div([
        html.H5(f"2. Verification & Correction: {display_filename}"),
        dbc.Alert(
            [
                html.H4(alert_header, className="alert-heading"),
                html.P(f"Total Rows: {len(df):,} | Verified Accounts (OK): {verified_count:,}", className="mb-1"),
                html.P(alert_fail_text, className=alert_fail_class),
            ],
            color=alert_color, className="mt-3"
        ),
        dbc.Button("Re-Verify After Correction", id={'type': 'reverify-btn', 'index': 1},
                   color="warning", className="mb-3 me-2"),
        dbc.Label("Note to Approver (Optional)", html_for="coop-note-textarea"),
        dbc.Textarea(id='coop-note-textarea', value=coop_note,
                     placeholder="Add notes for the approver regarding this submission...",
                     className="mb-3"),
        html.Div(dbc.Button("Finalize & Submit to Approver", id="submit-to-approver-button", color="success",
                            disabled=(failed_count > 0)),
                 className="d-flex justify-content-end mb-3"),
        dash_table.DataTable(
            id='editable-datatable',
            data=df.to_dict('records'),
            columns=table_columns,
            page_size=10,
            style_table={'overflowX': 'auto', 'marginTop': '10px'},
            editable=True,
            style_data_conditional=style_data_conditional,
            tooltip_data=tooltip_data,
            tooltip_duration=None,
            export_format="csv",  # --- ADDED ---
        )
    ])


def create_cooperative_layout(session_data):
    role = session_data.get('role')
    title_suffix = "Data Entry Portal" if role == 'coop_uploader' else "Finance Approval Dashboard (Audit Enabled)"
    password_change_button = html.Div(style={'display': 'block' if role == 'coop_approver' else 'none'}, children=[
        dbc.Button("Change Credentials", id="open-password-modal", color="warning", className="mb-3")
    ])

    coop_tabs_children = [
        dbc.Tab(label="📜 Submission History", tab_id="tab-coop-history", children=[
            dcc.Loading(type="default", children=html.Div(id="coop-history-placeholder", className="py-4"))
        ]),
        dbc.Tab(label="📊 Analytics", tab_id="tab-coop-analytics", children=[
            dcc.Loading(type="default", children=html.Div(id="coop-analytics-content", className="py-4"))
        ]),
    ]

    if role == 'coop_approver':
        coop_tabs_children.extend([
            dbc.Tab(label="📝 Activity Logs", tab_id="tab-coop-logs", children=[
                dcc.Loading(type="default", children=html.Div(id="coop-activity-logs-placeholder", className="py-4"))
            ]),
            dbc.Tab(label="👥 User Management", tab_id="tab-coop-user-management", children=[
                dcc.Loading(type="default", children=html.Div(id="coop-user-management-placeholder", className="py-4"))
            ])
        ])

    return html.Div([
        create_branded_navbar(f"{session_data.get('cooperative_name')} - {title_suffix}", is_admin=False),
        dbc.Container([
            dbc.Alert(id="coop-alert", is_open=False, duration=4000),
            password_change_button,
            html.H3("Batch Management", className="my-4"),
            html.Div(id="uploader-content", style={'display': 'block' if role == 'coop_uploader' else 'none'},
                     children=[
                         html.H4("1. Upload New Farmer Data"),
                         dcc.Upload(id='upload-data',
                                    children=html.Div(['Drag and Drop or ', html.A('Select a CSV/Excel File')]),
                                    style={'width': '100%', 'height': '60px', 'lineHeight': '60px',
                                           'borderWidth': '1px',
                                           'borderStyle': 'dashed', 'borderRadius': '5px', 'textAlign': 'center',
                                           'margin': '10px 0'},
                                    multiple=False),
                         dbc.Input(id="file-label-input", placeholder="Enter file label (e.g., 'Jan Week 1')",
                                   type="text", className="mb-3"),
                         html.Div(id="submission-table-placeholder"),
                         html.Hr(),
                     ]),
            html.Div(id="approver-queue", style={'display': 'block' if role == 'coop_approver' else 'none'}, children=[
                html.H4("2. Internal Approval & Payment Queue"),
                dcc.Loading(type="default", children=html.Div(id="coop-approval-placeholder", className="py-2"))
            ]),
            dbc.Tabs(id="coop-tabs", active_tab="tab-coop-history",
                     children=coop_tabs_children),
        ], fluid=True),
        dbc.Modal(id="coop-results-modal", size="xl", is_open=False),
        dbc.Modal(id="approver-details-modal", size="xl", is_open=False),
        create_change_password_modal(),
        create_payment_auth_modal(),
        dbc.Modal([dbc.ModalHeader("Processing Payment"), dbc.ModalBody(id="payment-animation-placeholder"),
                   dbc.ModalFooter(dbc.Button("Close", id="payment-close-button", color="secondary", disabled=True))],
                  id="payment-modal", backdrop="static"),
    ])


def create_admin_user_management_layout(session_data, is_admin=False):
    """Renders the User Management tab content for Admin or Coop Approver."""
    coop_name = session_data.get('cooperative_name')

    with get_db_connection() as conn:
        query = "SELECT id, username, role, cooperative_name, industry, temp_password FROM users WHERE role IN ('coop_uploader', 'coop_approver')"
        params = []
        if not is_admin:
            query += " AND cooperative_name = ?"
            params.append(coop_name)
        query += " ORDER BY cooperative_name, role"

        df = pd.read_sql_query(query, conn, params=params)

    if df.empty:
        df = pd.DataFrame(columns=['id', 'username', 'role', 'cooperative_name', 'industry', 'temp_password'])

    df = df.rename(columns={
        'cooperative_name': 'Cooperative',
        'industry': 'Product',
        'username': 'Username',
        'role': 'Role',
        'temp_password': 'Temporary Password'
    })

    role_map = {'coop_uploader': 'Uploader', 'coop_approver': 'Approver (Finance)'}
    df['Role'] = df['Role'].map(role_map)
    display_cols = ['Cooperative', 'Username', 'Role', 'Product', 'Temporary Password']

    return html.Div([
        html.H4("Create Cooperative Users (Uploader / Approver)", className="mb-4"),
        dbc.Card([
            dbc.CardHeader("New User Details"),
            dbc.CardBody([
                html.Div([
                    dbc.Popover(
                        [
                            dbc.PopoverHeader("Temporary Password Rule"),
                            dbc.PopoverBody(
                                "The initial password generated for Uploader and Approver accounts is a concatenation of the Cooperative's short name (e.g., CORECU) followed by a random 5-digit seed (10000-20000)."
                            ),
                        ],
                        id="password-rule-popover",
                        target="password-rule-icon",
                        trigger="hover",
                        placement="right",
                        is_open=False,
                    ),
                    html.Span(
                        "ℹ️ Password Rule",
                        id="password-rule-icon",
                        style={"cursor": "pointer", "marginLeft": "10px", "fontSize": "0.9em", "fontWeight": "bold"}
                    ),
                ], className="mb-3 d-flex align-items-center justify-content-end"),
                dbc.Row([
                    dbc.Col(dbc.Input(id="new-user-username", placeholder="Username (e.g., newcoop_data)", type="text",
                                      className="mb-3"), md=6),
                    dbc.Col(dbc.Input(id="new-user-password", placeholder="Password will be automatically generated",
                                      type="text", disabled=True, className="mb-3"), md=6),
                ]),
                dbc.Row([
                    dbc.Col(
                        dbc.Select(
                            id="new-user-coop-name",
                            options=[{"label": name, "value": name} for name in COOPERATIVE_UNIONS],
                            placeholder="Select Cooperative Union (Mandatory)",
                            className="mb-3"
                        ) if is_admin else dbc.Input(id="new-user-coop-name", value=coop_name, disabled=True,
                                                     className="mb-3"),
                        md=4
                    ),
                    dbc.Col(dbc.Select(
                        id="new-user-role",
                        options=[
                            {"label": "Uploader (Data Entry)", "value": "coop_uploader"},
                            {"label": "Approver (Finance Manager)", "value": "coop_approver"}
                        ],
                        placeholder="Select Role (Mandatory)",
                        className="mb-3"
                    ), md=4),
                    dbc.Col(dbc.Select(
                        id="new-user-product",
                        options=[{"label": name, "value": name} for name in FARM_PRODUCTS],
                        placeholder="Select Primary Product",
                        className="mb-3"
                    ), md=4),
                ]),
                html.Div(id="admin-create-user-alert", className="mt-3"),
                dbc.Button("Create New User", id="admin-create-user-button", color="primary", className="w-100 mt-3")
            ])
        ], className="mb-5 shadow-sm"),
        html.H4("Existing Cooperative Users"),
        dcc.Loading(type="default", children=dash_table.DataTable(
            id='admin-user-table',
            data=df[display_cols].to_dict('records'),
            columns=[{"name": i, "id": i} for i in display_cols],
            page_size=10,
            style_table={'overflowX': 'auto'},
            style_header={'backgroundColor': '#2c3e50', 'color': 'white', 'fontWeight': 'bold'},
            style_cell={'textAlign': 'left', 'whiteSpace': 'normal', 'height': 'auto'},
            style_data_conditional=[
                {'if': {'column_id': 'Temporary Password'}, 'backgroundColor': '#f7f7f7', },
                {'if': {'filter_query': '{Role} = "Approver (Finance)"'}, 'borderLeft': '5px solid #28a745'}
            ],
            filter_action="native",
            sort_action="native",
            export_format="csv",  # --- ADDED ---
        ))
    ], className="py-4")


def create_admin_layout(session_data):
    return html.Div([
        dbc.Toast(id="password-change-toast", is_open=False, duration=60000, icon="warning",
                  style={"position": "fixed", "top": 90, "right": 20, "width": 400, "zIndex": 9999}),
        dbc.Toast(id="ipn-toast", is_open=False, duration=6000, icon="success",
                  style={"position": "fixed", "top": 20, "right": 20, "width": 350, "zIndex": 9999}),

        create_branded_navbar("Admin Payments Dashboard (Verification Enabled)", is_admin=True),

        dbc.Container([
            dbc.Button("Change Admin Credentials", id="open-password-modal", color="warning", className="mb-3"),
            dcc.Loading(type="default", children=html.Div(id="kpi-cards-placeholder")),
            dcc.Loading(type="default", children=html.Div(id="admin-dashboard-content")),
            html.Hr(),
            dbc.Tabs(id="admin-tabs", active_tab="tab-analytics", children=[
                dbc.Tab(label="📊 Analytics", tab_id="tab-analytics", children=[
                    dcc.Loading(type="default", children=html.Div(id="analytics-tab-content", className="py-4"))
                ]),
                dbc.Tab(label="🧾 Invoices", tab_id="tab-invoices", children=[
                    dcc.Loading(type="default", children=html.Div(id="admin-invoices-placeholder", className="py-4"))
                ]),

                # --- THIS IS THE CORRECTED SECTION ---

                dbc.Tab(label="📄 Master Payment Data", tab_id="tab-master-data", children=[
                    dcc.Loading(type="default", children=html.Div(id="master-data-placeholder", className="py-4"))
                    # The redundant dbc.Collapse wrapper has been removed
                ]),
                dbc.Tab(label="📜 Payment History", tab_id="tab-history", children=[
                    dcc.Loading(type="default", children=html.Div(id="payment-history-placeholder", className="py-4"))
                    # The redundant dbc.Collapse wrapper has been removed
                ]),
                dbc.Tab(label="👥 User Management", tab_id="tab-user-management", children=[
                    dcc.Loading(type="default",
                                children=html.Div(id="admin-user-management-placeholder", className="py-4"))
                ]),
                dbc.Tab(label="📝 User Activity Logs", tab_id="tab-logs", children=[
                    dcc.Loading(type="default",
                                children=html.Div(id="activity-logs-placeholder", className="py-4"))
                ]),
            ]),
        ], fluid=True, className="py-4"),

        # Dummy component to fix the 'coop-alert' error
        html.Div(id="coop-alert", style={'display': 'none'}),

        create_change_password_modal(),
        dbc.Modal(id="details-modal", size="xl", is_open=False),
        dbc.Modal(id="admin-download-modal", children=html.Div(id="admin-download-modal-content"), size="lg",
                  backdrop="static"),
    ])


# Main App Layout & Control

app.layout = html.Div([
    dcc.Store(id="user-session", storage_type="session"),
    dcc.Store(id="batch-to-process"),
    dcc.Store(id='payment-authorization-store'),
    dcc.Store(id='ipn-data-store'),
    dcc.Store(id='show-login-page', data=False, storage_type='session'),
    dcc.Interval(id='payment-interval', interval=1500, n_intervals=0, disabled=True),
    dcc.Store(id='submission-trigger-store'),
    dcc.Store(id='uploader-verified-data'),
    dcc.Store(id='user-management-trigger'),
    dcc.Store(id='current-download-data'),
    dcc.Download(id="download-pdf"),
    html.Div(id={'type': 'log-activity-trigger', 'coop_name': 'dummy', 'action': 'dummy'}, style={'display': 'none'},
             children=0),
    html.Div(id="main-content")
])


# Callbacks

@app.callback(
    Output("main-content", "children"),
    Input("show-login-page", "data"),
    Input("user-session", "data"),
)
def display_page(show_login_page, session_data_obfuscated):
    session_data = deserialize_session(session_data_obfuscated)
    if session_data:
        if session_data.get("role") == "admin":
            return create_admin_layout(session_data)
        elif session_data.get("role") in ["coop_uploader", "coop_approver"]:
            return create_cooperative_layout(session_data)
    if show_login_page:
        return create_login_layout()
    else:
        return create_landing_layout()


@app.callback(
    Output("show-login-page", "data", allow_duplicate=True),
    Input("get-started-button", "n_clicks"),
    prevent_initial_call=True
)
def navigate_to_login(n_clicks):
    if n_clicks:
        return True
    return dash.no_update


@app.callback(
    Output("show-login-page", "data", allow_duplicate=True),
    Input("go-to-landing-button", "n_clicks"),
    prevent_initial_call=True
)
def navigate_to_landing(n_clicks):
    if n_clicks:
        return False
    return dash.no_update


@app.callback(
    Output("user-session", "data", allow_duplicate=True),
    Output("login-alert-placeholder", "children"),
    Input("login-button", "n_clicks"),
    State("login-username", "value"), State("login-password", "value"),
    prevent_initial_call=True
)
def handle_login(n_clicks, username, password):
    if not username or not password: return dash.no_update, dbc.Alert("Fields cannot be empty.", color="warning")
    user = authenticate_user(username, password)
    if user:
        log_activity(user['id'], 'Login', f"User '{user['username']}' logged in.")
        return serialize_session(user), None
    return None, dbc.Alert("Invalid credentials.", color="danger")


@app.callback(Output("user-session", "data", allow_duplicate=True), Input("logout-button", "n_clicks"),
              prevent_initial_call=True)
def handle_logout(n_clicks):
    if n_clicks: return None
    return dash.no_update


@app.callback(
    Output("password-modal", "is_open", allow_duplicate=True),
    Output({'type': 'log-activity-trigger', 'coop_name': 'dummy', 'action': 'dummy'}, 'children', allow_duplicate=True),
    Input("open-password-modal", "n_clicks"),
    Input("password-close-button", "n_clicks"),
    State("password-modal", "is_open"),
    prevent_initial_call=True
)
def toggle_password_modal(open_clicks, close_clicks, is_open):
    if open_clicks or close_clicks:
        return not is_open, dash.no_update
    return is_open, dash.no_update


@app.callback(
    Output("password-change-alert", "children"),
    Output("coop-alert", "children", allow_duplicate=True),
    Output("coop-alert", "is_open", allow_duplicate=True),
    Output("coop-alert", "color", allow_duplicate=True),
    Output({'type': 'log-activity-trigger', 'coop_name': 'dummy', 'action': 'dummy'}, 'children', allow_duplicate=True),
    Input("password-save-button", "n_clicks"),
    State("new-password", "value"),
    State("confirm-password", "value"),
    State("new-passphrase", "value"),
    State("new-pin", "value"),
    State("user-session", "data"),
    prevent_initial_call=True
)
def handle_password_change(n_clicks, new_pass, confirm_pass, new_passphrase, new_pin, session_data_obfuscated):
    session_data = deserialize_session(session_data_obfuscated)

    # Define a tuple for "no update" to avoid repetition
    no_coop_alert_update = (dash.no_update, dash.no_update, dash.no_update)

    if not session_data or session_data.get('role') not in ['coop_approver', 'admin']:
        return dbc.Alert("Access Denied.", color="danger"), *no_coop_alert_update, dash.no_update

    # --- Enhanced Validation ---
    if not all([new_pass, confirm_pass, new_passphrase, new_pin]):
        return dbc.Alert("All fields are required.", color="danger"), *no_coop_alert_update, dash.no_update
    if new_pass != confirm_pass:
        return dbc.Alert("Passwords do not match.", color="danger"), *no_coop_alert_update, dash.no_update
    if len(new_pass) < 6:
        return dbc.Alert("Password must be at least 6 characters.",
                         color="danger"), *no_coop_alert_update, dash.no_update
    if len(new_passphrase) < 8:
        return dbc.Alert("Passphrase must be at least 8 characters.",
                         color="danger"), *no_coop_alert_update, dash.no_update
    if len(new_pin) != 6 or not new_pin.isdigit():
        return dbc.Alert("PIN must be exactly 6 digits.", color="danger"), *no_coop_alert_update, dash.no_update
    # --- End Validation ---

    try:
        # Use the new function to update all credentials
        update_approver_credentials(session_data['id'], new_pass, new_passphrase, new_pin)
        log_activity(session_data['id'], 'Password Change',
                     f"User '{session_data['username']}' changed password, passphrase, and PIN.")

        if session_data.get('role') == 'admin':
            # Admin is logged in. Do NOT update coop-alert.
            return None, *no_coop_alert_update, random.randint(1, 1000)
        else:
            # Coop approver is logged in. Update coop-alert.
            coop_alert_msg = f"Success: Credentials for {session_data['username']} changed successfully."
            return None, coop_alert_msg, True, "success", random.randint(1, 1000)

    except Exception as e:
        return dbc.Alert(f"Error saving credentials: {e}",
                         color="danger"), *no_coop_alert_update, dash.no_update


@app.callback(
    Output("submission-table-placeholder", "children"),
    Output("uploader-verified-data", "data"),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename'),
    State("file-label-input", "value"),
    prevent_initial_call=True
)
def handle_uploader_upload(contents, filename, file_label):
    if contents is None: return html.Div(), None
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)

    try:
        df = pd.read_csv(io.StringIO(decoded.decode('utf-8'))) if 'csv' in filename else pd.read_excel(
            io.BytesIO(decoded))
        required_cols = {'farmer_name', 'bank_name', 'account_number', 'amount'}

        if not required_cols.issubset(df.columns):
            return dbc.Alert(f"File is missing columns: {required_cols - set(df.columns)}", color="danger"), None

        df = simulate_bank_verification(df.copy())

        label_prefix = f"{file_label} - " if file_label else ""
        display_filename = f"{label_prefix}{filename}"

        output_children = create_verification_layout(df, display_filename, reverify=False)
        return output_children, {'df': df.to_dict('records'), 'filename': filename,
                                 'display_filename': display_filename}

    except Exception as e:
        return dbc.Alert(f"Error processing file: {e}", color="danger"), None


@app.callback(
    Output("submission-table-placeholder", "children", allow_duplicate=True),
    Output("uploader-verified-data", "data", allow_duplicate=True),
    Input({'type': 'reverify-btn', 'index': ALL}, 'n_clicks'),
    State("editable-datatable", "data"),
    State("uploader-verified-data", "data"),
    State("coop-note-textarea", "value"),
    State("file-label-input", "value"),
    prevent_initial_call=True
)
def handle_reverification(n_clicks, table_data, submission_data_store, coop_note, file_label):
    if not any(n_clicks) or not table_data:
        return dash.no_update, dash.no_update

    df_corrected = pd.DataFrame(table_data)
    filename = submission_data_store.get('filename', 'uploaded_file')

    label_prefix = f"{file_label} - " if file_label else ""
    display_filename = f"{label_prefix}{filename}"

    df_reverified = simulate_bank_verification(df_corrected.copy())
    output_children = create_verification_layout(df_reverified, display_filename, coop_note, reverify=True)
    return output_children, {'df': df_reverified.to_dict('records'), 'filename': filename,
                             'display_filename': display_filename}


@app.callback(
    Output("coop-alert", "children"), Output("coop-alert", "is_open"), Output("coop-alert", "color"),
    Output("submission-table-placeholder", "children", allow_duplicate=True),
    Output("submission-trigger-store", "data", allow_duplicate=True),
    Input("submit-to-approver-button", "n_clicks"),
    State("editable-datatable", "data"), State("uploader-verified-data", "data"), State("user-session", "data"),
    State("coop-note-textarea", "value"),
    prevent_initial_call=True
)
def submit_to_approver(n_clicks, table_data, submission_data_store, session_data_obfuscated, coop_note):
    if not n_clicks or not table_data: return "", False, "", dash.no_update, dash.no_update
    session_data = deserialize_session(session_data_obfuscated)
    if session_data['role'] != 'coop_uploader':
        return "Access Denied.", True, "danger", dash.no_update, dash.no_update

    df = pd.DataFrame(table_data)
    # Get the CONCATENATED name from the store
    display_filename = submission_data_store.get('display_filename', 'uploaded_file')

    if (df['verification_status'] == 'failed').any():
        return "Submission Rejected: Please correct all verification failures before submitting.", True, "danger", dash.no_update, dash.no_update

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            record_count = len(df)
            total_amount = df['amount'].sum()
            submission_timestamp = datetime.now()

            cursor.execute(
                "INSERT INTO submission_batches (cooperative_id, filename, record_count, total_amount, submission_timestamp, status, cooperative_notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_data['id'], display_filename, record_count, total_amount, submission_timestamp,
                 'coop_submitted',
                 coop_note))
            batch_id = cursor.lastrowid

            df_to_db = df[
                ['farmer_name', 'bank_name', 'account_number', 'amount', 'verification_status', 'verification_reason']]
            df_to_db['batch_id'] = batch_id
            df_to_db.to_sql('farmer_payments', conn, if_exists='append', index=False)

            invoice_usd, invoice_ref = create_invoice(conn, batch_id, session_data['cooperative_name'], record_count,
                                                      submission_timestamp)
            conn.commit()
            log_activity(session_data['id'], 'Data Submission (Verified)',
                         f"Submitted '{display_filename}'. Batch ID: {batch_id}. Invoice {invoice_ref}: ${invoice_usd:,.2f}.")
            msg = f"Successfully submitted {record_count} records. Invoice {invoice_ref} created for ${invoice_usd:,.2f}. Awaiting internal approver."
        return msg, True, "success", dash.no_update, datetime.now().isoformat()

    except Exception as e:
        msg, color = f"Database error: {e}", "danger"
    return msg, True, color, dash.no_update, dash.no_update


@app.callback(
    Output("coop-approval-placeholder", "children"),
    Input("coop-tabs", "active_tab"),
    Input("user-session", "data"),
    Input("submission-trigger-store", "data"),
    prevent_initial_call=False
)
def render_coop_approval_queue(active_tab, session_data_obfuscated, submission_trigger):
    session_data = deserialize_session(session_data_obfuscated)
    if not session_data or session_data.get('role') != 'coop_approver':
        return None

    coop_name = session_data['cooperative_name']
    with get_db_connection() as conn:
        query = """
            SELECT b.id, u.username AS submitted_by_user, b.filename, b.record_count, b.total_amount, b.submission_timestamp
            FROM submission_batches b
            JOIN users u ON b.cooperative_id = u.id
            WHERE b.status = 'coop_submitted' AND u.cooperative_name = ?
            ORDER BY b.submission_timestamp DESC
        """
        batches_df = pd.read_sql_query(query, conn, params=(coop_name,))

    if batches_df.empty:
        return dbc.Alert(f"No batches currently awaiting internal approval for {coop_name}.", color="info")

    cards = []
    for _, row in batches_df.iterrows():
        cards.append(dbc.Card([
            dbc.CardHeader(f"Awaiting Approval | Submitted by: {row['submitted_by_user']}",
                           className="bg-warning text-dark"),
            dbc.CardBody([
                html.H5(row['filename'], className="card-title"),
                html.P(f"Records: {row['record_count']:,}, Total: TSH {row['total_amount']:,.2f}"),
                html.P(
                    f"Submitted: {datetime.strptime(row['submission_timestamp'].split('.')[0], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %I:%M %p')}",
                    className="text-muted small")
            ]),
            dbc.CardFooter(html.Div([
                dbc.Button("View Uploaded Data", id={'type': 'view-details-btn', 'index': row['id']}, color="secondary",
                           outline=True, className="me-2"),
            ], className="d-flex justify-content-end"))
        ], className="mb-3 shadow-sm"))
    return cards


@app.callback(
    Output("approver-details-modal", "is_open"),
    Output("approver-details-modal", "children"),
    Input({'type': 'view-details-btn', 'index': ALL}, 'n_clicks'),
    State("user-session", "data"),
    prevent_initial_call=True
)
def toggle_approver_details_modal(n_clicks, session_data_obfuscated):
    if not any(n_clicks): return False, None
    session_data = deserialize_session(session_data_obfuscated)

    # --- Allow admin to use this callback as well ---
    if not session_data or session_data.get('role') not in ('coop_approver', 'admin'):
        return False, None

    batch_id = int(eval(callback_context.triggered[0]['prop_id'].split('.')[0])['index'])

    # --- Check context to avoid opening two modals at once ---
    # If the user is an admin, they have their own modal ('details-modal').
    # This modal ('approver-details-modal') is ONLY for the coop_approver.
    if session_data.get('role') == 'admin':
        return False, None  # Admins use a different modal

    with get_db_connection() as conn:
        df = pd.read_sql_query(
            "SELECT farmer_name, bank_name, account_number, amount, verification_status, verification_reason FROM farmer_payments WHERE batch_id = ?",
            conn,
            params=(batch_id,))
        notes_df = pd.read_sql_query("SELECT filename, cooperative_notes FROM submission_batches WHERE id = ?", conn,
                                     params=(batch_id,))

    filename = notes_df['filename'].iloc[0]
    coop_note = notes_df['cooperative_notes'].iloc[0] or ""
    style_data_conditional = [
        {'if': {'filter_query': '{verification_status} = "verified"'}, 'backgroundColor': '#e8f5e9'},
        {'if': {'filter_query': '{verification_status} = "failed"'}, 'backgroundColor': '#ffebee', 'fontWeight': 'bold'}
    ]

    return True, [
        dbc.ModalHeader(f"Uploaded Data & Verification Status (Batch ID: {batch_id}) - {filename}"),
        dbc.ModalBody([
            dbc.Alert(f"Note from Uploader: {coop_note}", color="info") if coop_note else html.P("No note provided.",
                                                                                                 className="text-muted fst-italic"),
            html.H5("Uploaded Data Preview"),
            html.P(f"Total Rows: {len(df):,}. All rows passed Uploader's internal verification check."),
            dash_table.DataTable(data=df.to_dict('records'),
                                 columns=[{'name': i.replace('_', ' ').title(), 'id': i} for i in df.columns],
                                 style_table={'maxHeight': '50vh', 'overflowY': 'auto'},
                                 style_data_conditional=style_data_conditional,
                                 style_header={'backgroundColor': 'lightgray', 'fontWeight': 'bold'},
                                 sort_action="native",
                                 export_format="csv",  # --- ADDED ---
                                 ),
            html.Hr(),
            html.Div(id=f'coop-approval-action-area-{batch_id}', children=[
                dbc.Button("Authorize Payment",
                           id={'type': 'payment-button', 'index': batch_id}, color="success")
            ], className="d-flex justify-content-end")
        ]),
    ]


@app.callback(
    Output("kpi-cards-placeholder", "children"),
    Input("user-session", "data"),
    Input("ipn-data-store", "data"),
    Input("submission-trigger-store", "data")
)
def update_kpi_cards(session_data_obfuscated, ipn_data, submission_trigger):
    session_data = deserialize_session(session_data_obfuscated)
    if not session_data or session_data.get("role") != "admin": return None

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(amount) FROM farmer_payments WHERE status = 'paid'")
        total_paid = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(id) FROM farmer_payments WHERE status = 'paid'")
        farmers_paid_count = cursor.fetchone()[0] or 0
        cursor.execute(
            "SELECT COUNT(id) FROM submission_batches WHERE status IN ('pending_admin_approval', 'verified', 'coop_submitted')")  # Added coop_submitted
        pending_submissions = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(id) FROM users WHERE role IN ('coop_uploader', 'coop_approver')")
        coop_count = cursor.fetchone()[0] or 0

    kpi_cards = dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H4(f"TSH {total_paid:,.2f}", className="card-title"),
            html.P("Total Amount Paid", className="card-text text-muted"),
        ])), width=6, lg=3, className="mb-3"),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H4(f"{farmers_paid_count:,}", className="card-title"),
            html.P("Total Farmers Paid", className="card-text text-muted"),
        ])), width=6, lg=3, className="mb-3"),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H4(pending_submissions, className="card-title text-warning"),
            html.P("Batches in All Queues", className="card-text text-muted"),
        ])), width=6, lg=3, className="mb-3"),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H4(coop_count, className="card-title"),
            html.P("Active Cooperative Users", className="card-text text-muted"),
        ])), width=6, lg=3, className="mb-3"),
    ])
    return html.Div([kpi_cards])


@app.callback(
    Output("admin-invoices-placeholder", "children"),
    Input("admin-tabs", "active_tab"),
    Input("submission-trigger-store", "data")
)
def render_admin_invoices(active_tab, trigger):
    if active_tab != "tab-invoices": return None

    with get_db_connection() as conn:
        query = """
            SELECT id, batch_id, cooperative_name, submission_timestamp, row_count, amount_usd, status, payment_date, 
                   invoice_reference, payment_commission_usd, payment_commission_reference 
            FROM invoices 
            ORDER BY submission_timestamp DESC
        """
        df = pd.read_sql_query(query, conn)

    if df.empty: return dbc.Alert("No verification invoices generated yet.", color="info")

    df['submission_timestamp'] = pd.to_datetime(df['submission_timestamp']).dt.strftime('%Y-%m-%d %I:%M %p')
    df['payment_date'] = df['payment_date'].apply(
        lambda x: pd.to_datetime(x).strftime('%Y-%m-%d %I:%M %p') if pd.notna(x) and x is not None else 'N/A')

    unpaid_df = df[df['status'] == 'unpaid']
    unpaid_total = unpaid_df['amount_usd'].sum()
    total_commission = df['payment_commission_usd'].sum()

    df['amount_usd_raw'] = df['amount_usd']
    df['amount_usd_display'] = df['amount_usd'].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A")
    df['payment_commission_usd_display'] = df['payment_commission_usd'].apply(
        lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A")

    # The 'action' column has been removed

    df = df.rename(
        columns={'invoice_reference': 'Service Ref #', 'payment_commission_reference': 'Payment Ref #',
                 'amount_usd_display': 'Service Fee (USD)', 'payment_commission_usd_display': 'Commission (USD)',
                 'cooperative_name': 'Cooperative', 'submission_timestamp': 'Date Issued',
                 'row_count': 'Rows', 'status': 'Status', 'payment_date': 'Date Paid'})

    style_data_conditional = [
        {'if': {'filter_query': '{Status} = "paid"'}, 'backgroundColor': '#d4edda', 'color': '#155724'},
        {'if': {'filter_query': '{Status} = "unpaid"'}, 'backgroundColor': '#fff3cd', 'color': '#856404',
         'fontWeight': 'bold'},
        {'if': {'column_id': 'Commission (USD)'}, 'backgroundColor': '#e8f5e9'},
        # Action column style removed
    ]

    # 'Action' column removed from display
    display_cols = ['Service Ref #', 'Payment Ref #', 'Cooperative', 'Date Issued', 'Rows', 'Service Fee (USD)',
                    'Commission (USD)', 'Status', 'Date Paid']

    return html.Div([
        html.H4("Master Invoice Ledger"),
        dbc.Row([
            dbc.Col(dbc.Alert(html.H5(f"Total Unpaid Service Fees: ${unpaid_total:,.2f}"), color="warning"), width=6),
            dbc.Col(dbc.Alert(html.H5(f"Total Payment Commission Earned: ${total_commission:,.2f}"), color="success"),
                    width=6),
        ], className="mt-3"),
        dash_table.DataTable(
            id='admin-invoice-table',
            data=df.to_dict('records'),
            columns=[{'name': i, 'id': i} for i in display_cols],
            page_size=15,
            style_table={'overflowX': 'auto'},
            style_data_conditional=style_data_conditional,
            filter_action="native",
            sort_action="native",
            export_format="csv",
            active_cell=None
        )
    ])


@app.callback(
    Output("admin-dashboard-content", "children"),
    Input("user-session", "data"), Input("ipn-data-store", "data"), Input("submission-trigger-store", "data"),
    Input("payment-interval", "disabled")
)
def render_admin_dashboard(session_data_obfuscated, ipn_data, submission_trigger, payment_interval_disabled):
    session_data = deserialize_session(session_data_obfuscated)
    if not session_data or session_data.get("role") != "admin": return None
    with get_db_connection() as conn:
        query = "SELECT b.id, u.cooperative_name, b.filename, b.record_count, b.total_amount, b.status FROM submission_batches b JOIN users u ON b.cooperative_id = u.id WHERE b.status IN ('coop_submitted', 'pending_admin_approval', 'verified') ORDER BY b.submission_timestamp DESC"
        batches_df = pd.read_sql_query(query, conn)

    if batches_df.empty: return dbc.Alert("No Batches currently awaiting Admin Action (Verification/Payment).",
                                          color="info", className="m-4")
    cards = []
    for _, row in batches_df.iterrows():
        status = row['status']
        header_color = header_text = ""
        is_processing = not payment_interval_disabled

        if status == 'coop_submitted':
            header_color = "bg-danger text-white"
            header_text = f"Status: Awaiting Coop Approval"
        elif status == 'pending_admin_approval':
            header_color = "bg-warning text-dark"
            header_text = f"Status: Pending Payment"
        elif status == 'verified':
            header_color = "bg-success text-white"
            with get_db_connection() as conn_stats:
                verified_count = pd.read_sql_query(
                    "SELECT COUNT(id) FROM farmer_payments WHERE batch_id = ? AND verification_status = 'verified'",
                    conn_stats, params=(row['id'],)).iloc[0, 0]
                failed_count = pd.read_sql_query(
                    "SELECT COUNT(id) FROM farmer_payments WHERE batch_id = ? AND verification_status = 'failed'",
                    conn_stats, params=(row['id'],)).iloc[0, 0]
            header_text = f"Status: Verified | OK: {verified_count:,} | Bounced: {failed_count:,}"

        card = dbc.Card([
            dbc.CardHeader(html.Div(header_text), className=header_color),
            dbc.CardBody([
                html.H5(row['filename'], className="card-title"),
                html.P(f"{row['cooperative_name']}"),
                html.P(f"{row['record_count']:,} farmers, Total: TSH {row['total_amount']:,.2f}")
            ]),
            dbc.CardFooter(html.Div([
                dbc.Button("View Details", id={'type': 'view-details-btn', 'index': row['id']}, color="secondary",
                           outline=True),
            ], className="d-flex justify-content-end"))
        ], className="mb-4 shadow-sm")
        cards.append(card)
    return [html.H3("Payments Awaiting Action", className="mb-4")] + cards


# Payment Authorization Flow Callbacks

@app.callback(
    Output('payment-auth-modal', 'is_open'),
    Output('payment-authorization-store', 'data'),
    Output('payment-auth-step-store', 'data', allow_duplicate=True),
    Output('passphrase-step', 'style'),
    Output('pin-step', 'style'),
    Output('auth-next-button', 'style'),
    Output('auth-authorize-button', 'style'),
    Output('auth-passphrase-input', 'value'),
    Output('auth-pin-input', 'value'),
    Output('auth-passphrase-alert', 'children'),
    Output('auth-pin-alert', 'children'),
    Input({'type': 'payment-button', 'index': ALL}, 'n_clicks'),
    Input('auth-cancel-button', 'n_clicks'),
    prevent_initial_call=True
)
def trigger_auth_modal(pay_clicks, cancel_click):
    """
    This callback intercepts a payment button click, opens the modal,
    and stores which payment is being attempted.
    """
    ctx = callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate

    triggered_id = ctx.triggered[0]["prop_id"]

    if 'auth-cancel-button' in triggered_id:
        # User clicked "Cancel", just close and reset
        return False, None, 'passphrase', {'display': 'block'}, {'display': 'none'}, {'display': 'block'}, {
            'display': 'none'}, '', '', None, None

    if 'payment-button' in triggered_id:
        # A payment button was clicked
        id_dict = json.loads(triggered_id.split('.')[0])
        payment_data = {
            'batch_id': id_dict['index'],
            'type': 'batch_payment'
        }
        # Open modal and reset to step 1
        return True, payment_data, 'passphrase', {'display': 'block'}, {'display': 'none'}, {'display': 'block'}, {
            'display': 'none'}, '', '', None, None

    return False, None, 'passphrase', {'display': 'block'}, {'display': 'none'}, {'display': 'block'}, {
        'display': 'none'}, '', '', None, None


@app.callback(
    Output('payment-auth-step-store', 'data'),
    Output('passphrase-step', 'style', allow_duplicate=True),
    Output('pin-step', 'style', allow_duplicate=True),
    Output('auth-next-button', 'style', allow_duplicate=True),
    Output('auth-authorize-button', 'style', allow_duplicate=True),
    Output('auth-passphrase-alert', 'children', allow_duplicate=True),
    Input('auth-next-button', 'n_clicks'),
    State('auth-passphrase-input', 'value'),
    State("user-session", "data"),
    prevent_initial_call=True
)
def handle_passphrase_step(n_clicks, passphrase, session_data_obfuscated):
    """
    Verifies the passphrase against the DB and moves to the PIN step.
    """
    if not n_clicks:
        raise dash.exceptions.PreventUpdate

    session_data = deserialize_session(session_data_obfuscated)
    user_id = session_data['id']

    if check_user_passphrase(user_id, passphrase):
        # Success: move to PIN step
        return 'pin', {'display': 'none'}, {'display': 'block'}, {'display': 'none'}, {'display': 'block'}, None
    else:
        # Fail: show alert
        alert = dbc.Alert("Invalid Passphrase. Please try again.", color="danger", dismissable=True)
        return 'passphrase', {'display': 'block'}, {'display': 'none'}, {'display': 'block'}, {'display': 'none'}, alert


@app.callback(
    Output('pin-input-store', 'data', allow_duplicate=True),
    Output('auth-pin-input', 'value', allow_duplicate=True),
    Input({'type': 'pin-pad-button', 'index': ALL}, 'n_clicks'),
    State('pin-input-store', 'data'),
    prevent_initial_call=True
)
def update_pin_from_dialpad(n_clicks, current_pin):
    if not any(n_clicks):
        raise dash.exceptions.PreventUpdate

    if current_pin is None:
        current_pin = ""

    triggered_id = callback_context.triggered[0]["prop_id"]
    if not triggered_id:
        raise dash.exceptions.PreventUpdate

    button_value = json.loads(triggered_id.split('.')[0])['index']

    new_pin = current_pin

    if button_value == 'C':
        new_pin = ""
    elif button_value == '<':
        new_pin = current_pin[:-1]
    elif len(current_pin) < 6:
        new_pin = current_pin + button_value

    return new_pin, new_pin


@app.callback(
    Output('payment-auth-modal', 'is_open', allow_duplicate=True),
    Output('auth-pin-alert', 'children', allow_duplicate=True),
    # Outputs to trigger the *existing* payment animation flow
    Output('batch-to-process', 'data'),
    Output('payment-modal', 'is_open'),
    Output('payment-interval', 'disabled'),
    Output('payment-animation-placeholder', 'children'),
    # Outputs to clear the pin
    Output('pin-input-store', 'data', allow_duplicate=True),
    Output('auth-pin-input', 'value', allow_duplicate=True),
    Input('auth-authorize-button', 'n_clicks'),
    State('pin-input-store', 'data'),
    State('payment-authorization-store', 'data'),
    State('user-session', 'data'),
    prevent_initial_call=True
)
def handle_pin_step(n_clicks, pin, payment_data, session_data_obfuscated):
    """
    Verifies the PIN against the DB and, on success, closes the auth modal and
    triggers the main payment animation modal.
    """
    if not n_clicks or not payment_data:
        raise dash.exceptions.PreventUpdate

    session_data = deserialize_session(session_data_obfuscated)
    user_id = session_data['id']

    if check_user_pin(user_id, pin):
        # PIN is correct!
        batch_id = payment_data.get('batch_id')

        # 1. Log the authorization
        log_activity(session_data['id'], 'Payment Authorized', f"Two-step auth passed for Batch ID: {batch_id}")

        # 2. Get batch status to pass to the animation modal
        with get_db_connection() as conn_check:
            cursor = conn_check.cursor()
            cursor.execute(
                "UPDATE submission_batches SET status = 'pending_admin_approval' WHERE id = ? AND status = 'coop_submitted'",
                (batch_id,))
            conn_check.commit()

            batch_status = pd.read_sql_query("SELECT status FROM submission_batches WHERE id = ?", conn_check,
                                             params=(batch_id,)).iloc[0, 0]

        # 3. Prepare the animation modal's first step
        animation_step = html.Div([
            html.Div("⚙️", style={'fontSize': 50}),
            dbc.Progress(value=20, striped=True, animated=True, style={"height": "20px"}),
            html.P(PAYMENT_STEPS[0], className="mt-2")
        ], className="text-center")

        new_batch_data = {'id': batch_id, 'status': batch_status}

        # 4. Close auth modal, clear PIN alert, and trigger the animation modal
        return False, None, new_batch_data, True, False, animation_step, '', ''

    else:
        # PIN is incorrect
        alert = dbc.Alert("Invalid PIN. Please try again.", color="danger", dismissable=True)
        # Don't close or change anything, just show the alert and clear pin
        return dash.no_update, alert, dash.no_update, dash.no_update, dash.no_update, dash.no_update, '', ''


@app.callback(
    Output('passphrase-step', 'style', allow_duplicate=True),
    Output('pin-step', 'style', allow_duplicate=True),
    Output('auth-next-button', 'style', allow_duplicate=True),
    Output('auth-authorize-button', 'style', allow_duplicate=True),
    Output('auth-passphrase-input', 'value', allow_duplicate=True),
    Output('auth-pin-input', 'value', allow_duplicate=True),
    Output('auth-passphrase-alert', 'children', allow_duplicate=True),
    Output('auth-pin-alert', 'children', allow_duplicate=True),
    Output('payment-authorization-store', 'data', allow_duplicate=True),
    Output('pin-input-store', 'data', allow_duplicate=True),  # <-- ADDED
    Input('payment-auth-modal', 'is_open'),
    prevent_initial_call=True
)
def reset_auth_modal_on_close(is_open):
    """
    Catches when the modal is closed (by any means) and resets it.
    """
    if is_open:
        raise dash.exceptions.PreventUpdate

    # Reset all components to their initial state
    return {'display': 'block'}, {'display': 'none'}, {'display': 'block'}, {
        'display': 'none'}, '', '', None, None, None, ''  # <-- ADDED ''


# Main Payment Processing Callback

@app.callback(
    Output("payment-modal", "is_open", allow_duplicate=True),
    Output("payment-interval", "disabled", allow_duplicate=True),
    Output("payment-animation-placeholder", "children", allow_duplicate=True),
    Output("payment-close-button", "disabled"),
    Output("batch-to-process", "data", allow_duplicate=True),
    Output("ipn-data-store", "data"),
    Input("payment-interval", "n_intervals"),
    Input("payment-close-button", "n_clicks"),
    Input("payment-modal", "is_open"),
    State("batch-to-process", "data"),
    State("user-session", "data"),
    prevent_initial_call=True
)
def handle_payment_processing(n_intervals, close_clicks, modal_is_open, batch_data, session_data_obfuscated):
    ctx = callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate

    session_data = deserialize_session(session_data_obfuscated)
    triggered_id_str = ctx.triggered[0]['prop_id']

    # This is the new "start" trigger, fired when the PIN callback opens this modal
    if triggered_id_str == 'payment-modal.is_open' and modal_is_open:
        return dash.no_update, False, dash.no_update, True, dash.no_update, dash.no_update

    elif 'payment-interval' in triggered_id_str and batch_data is not None:
        batch_id_num = batch_data['id']
        batch_status = batch_data['status']

        if n_intervals < 4:
            step_index = n_intervals
            progress = (step_index + 1) * 20
            animation_step = html.Div([
                html.Div("⚙️", style={'fontSize': 50}),
                dbc.Progress(value=progress, striped=True, animated=True, style={"height": "20px"}),
                html.P(VERIFICATION_STEPS[step_index] if batch_status == 'pending_admin_approval' else PAYMENT_STEPS[
                    step_index], className="mt-2")
            ], className="text-center")
            return True, False, animation_step, True, batch_data, dash.no_update
        else:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                if batch_status == 'pending_admin_approval':
                    verification_updates = []
                    reasons = ["Account Closed", "Name Mismatch", "Invalid Bank Code"]
                    cursor.execute(
                        "SELECT id, verification_status, verification_reason FROM farmer_payments WHERE batch_id = ?",
                        (batch_id_num,))
                    total_count = 0
                    failed_count = 0
                    for (pid, current_v_status, current_v_reason) in cursor.fetchall():
                        total_count += 1
                        if current_v_status == 'verified' and random.random() < 0.20:
                            failed_count += 1
                            verification_updates.append(('failed', random.choice(reasons), pid))
                        elif current_v_status == 'failed':
                            failed_count += 1
                            reason_text = current_v_reason if current_v_reason else "Pre-verified Failed (Uncorrected)"
                            verification_updates.append(('failed', reason_text, pid))
                        else:
                            verification_updates.append(('verified', None, pid))
                    cursor.executemany(
                        "UPDATE farmer_payments SET verification_status = ?, verification_reason = ? WHERE id = ?",
                        verification_updates)
                    cursor.execute("UPDATE submission_batches SET status = 'verified' WHERE id = ?", (batch_id_num,))
                    conn.commit()
                    log_activity(session_data['id'], 'Account Verification',
                                 f"Batch {batch_id_num} auto-verified. Failures: {failed_count}/{total_count}.")

                cursor.execute(
                    "SELECT u.cooperative_name, b.filename, b.record_count, b.total_amount FROM submission_batches b JOIN users u ON b.cooperative_id = u.id WHERE b.id = ?",
                    (batch_id_num,))
                batch_info = cursor.fetchone()
                cursor.execute("UPDATE submission_batches SET status = 'processed' WHERE id = ?", (batch_id_num,))

                payments, success, failed = [], 0, 0
                reasons = ["Bank Communication Timeout", "Daily Limit Reached", "System Error"]
                cursor.execute(
                    "SELECT id, verification_status, verification_reason FROM farmer_payments WHERE batch_id = ?",
                    (batch_id_num,))
                for pid, v_status, v_reason in cursor.fetchall():
                    if v_status == 'failed':
                        failed += 1
                        payments.append(('failed', f"Verification Failed: {v_reason}", pid))
                    elif random.random() < 0.95:
                        success += 1
                        payments.append(('paid', None, pid))
                    else:
                        failed += 1
                        payments.append(('failed', random.choice(reasons), pid))
                cursor.executemany("UPDATE farmer_payments SET status = ?, failure_reason = ? WHERE id = ?", payments)

                if batch_info:
                    coop_name, filename, record_count, total_amount = batch_info
                    cursor.execute(
                        "INSERT INTO payment_history (batch_id, cooperative_name, filename, record_count, total_amount, processing_timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                        (batch_id_num, coop_name, filename, record_count, total_amount, datetime.now()))
                    create_payment_commission(conn, batch_id_num, coop_name, total_amount)

                conn.commit()

            log_activity(session_data['id'], 'Payment Processed',
                         f"Processed '{batch_info[1]}' for {batch_info[0]}. Success: {success}, Failed: {failed}.")
            ipn = {'coop': batch_info[0], 'success': success, 'failed': failed, 'total': batch_info[2]}
            result = html.Div([
                html.Div("✅", style={'fontSize': 60, 'color': 'green'}),
                dbc.Progress(value=100, color="success", style={"height": "20px"}),
                html.H5(PAYMENT_STEPS[4], className="mt-2")
            ], className="text-center")
            return True, True, result, False, None, ipn

    elif 'payment-close-button' in triggered_id_str:
        return False, True, "", True, None, dash.no_update
    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update


@app.callback(
    Output("ipn-toast", "is_open"), Output("ipn-toast", "header"), Output("ipn-toast", "children"),
    Output("ipn-toast", "icon"),
    Input("ipn-data-store", "data"), prevent_initial_call=True
)
def show_ipn_toast(data):
    if not data: return False, "", "", ""
    header, icon = "IPN: Transaction Complete", "warning" if data['failed'] > 0 else "success"
    body = f"{data['coop']}: Paid {data['success']}/{data['total']} farmers. ({data['failed']} failed)"
    return True, header, body, icon


@app.callback(
    Output("coop-user-management-placeholder", "children"),
    Input("coop-tabs", "active_tab"),
    Input("user-management-trigger", "data"),
    Input("user-session", "data")
)
def update_coop_user_management_tab(active_tab, trigger, session_data_obfuscated):
    if active_tab == "tab-coop-user-management":
        session_data = deserialize_session(session_data_obfuscated)
        return create_admin_user_management_layout(session_data, is_admin=False)
    return dash.no_update


@app.callback(
    Output("admin-user-management-placeholder", "children"),
    Input("admin-tabs", "active_tab"),
    Input("user-management-trigger", "data"),
    Input("user-session", "data")
)
def render_admin_user_management_tab(active_tab, trigger, session_data_obfuscated):
    if active_tab == "tab-user-management":
        session_data = deserialize_session(session_data_obfuscated)
        return create_admin_user_management_layout(session_data, is_admin=True)
    return dash.no_update


@app.callback(
    Output("admin-create-user-alert", "children"),
    Output("admin-create-user-alert", "is_open"),
    Output("admin-create-user-alert", "color"),
    Output("new-user-username", "value"),
    Output("new-user-password", "value", allow_duplicate=True),
    Output("new-user-coop-name", "value"),
    Output("new-user-role", "value"),
    Output("new-user-product", "value"),
    Output("user-management-trigger", "data"),
    Input("admin-create-user-button", "n_clicks"),
    State("new-user-username", "value"),
    State("new-user-coop-name", "value"),
    State("new-user-role", "value"),
    State("new-user-product", "value"),
    State("user-session", "data"),  # This state provides the obfuscated data
    prevent_initial_call=True
)
def create_coop_user(n_clicks, username, coop_name, role, product, session_data_obfuscated):  # Renamed argument
    no_update_9 = (
        dash.no_update, False, "", dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
        dash.no_update)
    if not n_clicks:
        return no_update_9

    # --- THIS IS THE FIX ---
    # Deserialize the session data first
    session_data = deserialize_session(session_data_obfuscated)

    # Now this check will work
    if not session_data or session_data.get('role') not in ('admin', 'coop_approver'):
        return dbc.Alert("Access Denied.",
                         color="danger"), True, "danger", dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    # --- END OF FIX ---

    if not all([username, coop_name, role]):
        return dbc.Alert("Username, Cooperative, and Role are required.",
                         color="warning"), True, "warning", dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username,))
        if cursor.fetchone()[0] > 0:
            return dbc.Alert(f"Username '{username}' is already taken.",
                             color="danger"), True, "danger", dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        try:
            coop_short_name = coop_name.split()[0].upper()
            random_seed = random.randint(10000, 20000)
            temp_password = f"{coop_short_name}{random_seed}"
            hashed_password = hashlib.sha256(temp_password.encode()).hexdigest()
            user_product = product if product else "Not Specified"

            new_passphrase_hash = None
            new_pin_hash = None
            if role == 'coop_approver':
                new_passphrase_hash = hashlib.sha256("cooppass".encode()).hexdigest()
                new_pin_hash = hashlib.sha256("123456".encode()).hexdigest()

            new_user = (
                username, hashed_password, role, coop_name, user_product, temp_password, new_passphrase_hash,
                new_pin_hash)
            cursor.execute(
                "INSERT INTO users (username, password, role, cooperative_name, industry, temp_password, passphrase, pin) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                new_user)
            conn.commit()
            log_activity(session_data['id'], 'User Created',
                         f"Created new '{role}' user: {username} for {coop_name}. Initial Password: {temp_password}")

            msg = html.Div([html.P(f"Successfully created user **{username}** ({role}) for {coop_name}."),
                            html.P([f"Initial Password: ", html.Code(temp_password)])])

            return msg, True, "success", "", "", None, None, None, datetime.now().isoformat()

        except Exception as e:
            conn.rollback()
            return dbc.Alert(f"Database error during user creation: {e}",
                             color="danger"), True, "danger", dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update


def render_admin_data_table(query, active_tab, tab_id, columns_to_drop=None, styling=None, editable=False, params=()):
    """Generic helper to render styled admin tables."""
    if active_tab != tab_id: return None
    with get_db_connection() as conn:
        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            return dbc.Alert(f"Error querying data: {e}", color="danger")

    if df.empty: return dbc.Alert(f"No data found for {tab_id.replace('-', ' ').title()}.", color="secondary")

    if columns_to_drop: df = df.drop(columns=columns_to_drop, errors='ignore')

    for col in df.columns:
        if 'timestamp' in col or 'date' in col:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d %I:%M %p').fillna('N/A')

    if 'amount_usd' in df.columns:
        df['amount_usd'] = df['amount_usd'].apply(
            lambda x: f"${x:,.2f}" if pd.notna(x) and isinstance(x, (int, float)) else x)
    if 'total_amount' in df.columns:
        df['total_amount'] = df['total_amount'].apply(
            lambda x: f"TSH {x:,.2f}" if pd.notna(x) and isinstance(x, (int, float)) else x)

    return dash_table.DataTable(data=df.to_dict('records'),
                                columns=[{'name': col.replace('_', ' ').title(), 'id': col} for col in df.columns],
                                page_size=15,
                                style_table={'overflowX': 'auto'},
                                style_header={'backgroundColor': '#2c3e50', 'color': 'white', 'fontWeight': 'bold'},
                                style_cell={'textAlign': 'left', 'whiteSpace': 'normal', 'height': 'auto'},
                                style_data_conditional=styling,
                                filter_action="native",
                                sort_action="native",
                                editable=editable,
                                export_format="csv",  # --- ADDED ---
                                )


@app.callback(Output("master-data-placeholder", "children"), Input("admin-tabs", "active_tab"),
              Input("ipn-data-store", "data"), Input("submission-trigger-store", "data"))
def render_master_data_table(active_tab, ipn_data, trigger):
    if active_tab != "tab-master-data": return dash.no_update

    query = """
        SELECT u.cooperative_name, b.submission_timestamp, b.filename, p.* FROM farmer_payments AS p
        JOIN submission_batches AS b ON p.batch_id = b.id JOIN users AS u ON b.cooperative_id = u.id
        ORDER BY b.submission_timestamp DESC;"""
    styling = [{'if': {'column_id': 'status', 'filter_query': '{status} = "paid"'}, 'backgroundColor': '#d4edda'},
               {'if': {'column_id': 'status', 'filter_query': '{status} = "failed"'}, 'backgroundColor': '#f8d7da'},
               {'if': {'column_id': 'verification_status', 'filter_query': '{verification_status} = "verified"'},
                'backgroundColor': '#e8f5e9'},
               {'if': {'column_id': 'verification_status', 'filter_query': '{verification_status} = "failed"'},
                'backgroundColor': '#ffebee'}]

    return render_admin_data_table(
        query,
        active_tab,
        "tab-master-data",
        columns_to_drop=['id', 'batch_id'],
        styling=styling,
        editable=True
    )


@app.callback(Output("payment-history-placeholder", "children"), Input("admin-tabs", "active_tab"),
              Input("ipn-data-store", "data"), Input("submission-trigger-store", "data"))
def render_payment_history(active_tab, ipn_data, trigger):
    if active_tab != "tab-history": return dash.no_update
    with get_db_connection() as conn:
        # --- UPDATED SQL QUERY ---
        # Fetches data for both service and commission invoices
        query = """
            SELECT 
                p.processing_timestamp, p.cooperative_name, p.filename, p.record_count, p.total_amount, 
                i.payment_commission_usd, i.payment_commission_reference,
                i.invoice_reference, i.submission_timestamp, i.row_count, i.amount_usd, i.status
            FROM payment_history p 
            LEFT JOIN invoices i ON p.batch_id = i.batch_id 
            ORDER BY p.processing_timestamp DESC
        """
        df = pd.read_sql_query(query, conn)

    if df.empty: return dbc.Alert("No processed payments found in history.", color="secondary")

    # --- Store all raw data needed for modals ---
    df['processing_timestamp_display'] = pd.to_datetime(df['processing_timestamp']).dt.strftime('%Y-%m-%d %I:%M %p')
    df['submission_timestamp_display'] = pd.to_datetime(df['submission_timestamp']).dt.strftime('%Y-%m-%d %I:%M %p')
    df['total_amount_raw'] = df['total_amount']
    df['payment_commission_usd_raw'] = df['payment_commission_usd']
    df['amount_usd_raw'] = df['amount_usd']

    # --- Add the new action columns ---
    df['action_service'] = "View Invoice"
    df['action_commission'] = "View Receipt"

    df = df.rename(columns={
        'processing_timestamp_display': 'Date Processed',
        'cooperative_name': 'Cooperative',
        'filename': 'Filename',
        'record_count': 'Records',
        'action_service': 'Service Invoice',
        'action_commission': 'Commission Receipt'
    })

    # --- Updated display columns ---
    display_cols = ['Date Processed', 'Cooperative', 'Filename', 'Records', 'Service Invoice', 'Commission Receipt']

    return dash_table.DataTable(
        id='payment-history-table',
        data=df.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in display_cols],
        page_size=15,
        style_table={'overflowX': 'auto'},
        style_header={'backgroundColor': '#2c3e50', 'color': 'white', 'fontWeight': 'bold'},
        style_cell={'textAlign': 'left', 'whiteSpace': 'normal', 'height': 'auto'},
        # --- Updated styles to make new columns clickable ---
        style_data_conditional=[
            {'if': {'column_id': 'Service Invoice'}, 'color': 'blue', 'textDecoration': 'underline',
             'cursor': 'pointer'},
            {'if': {'column_id': 'Commission Receipt'}, 'color': 'green', 'textDecoration': 'underline',
             'cursor': 'pointer'}
        ],
        filter_action="native",
        sort_action="native",
        export_format="csv",
        active_cell=None
    )


@app.callback(
    Output("admin-download-modal", "is_open"),
    Output("admin-download-modal-content", "children"),
    Output("current-download-data", "data"),
    Input("payment-history-table", "active_cell"),
    Input({'type': 'admin-download-modal-close', 'index': ALL}, "n_clicks"),
    State("payment-history-table", "data"),
    State("admin-download-modal", "is_open"),
    prevent_initial_call=True
)
def toggle_admin_download_modal(active_cell, close_clicks, history_data, is_open):
    ctx = callback_context
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if "admin-download-modal-close" in triggered_id:
        return False, None, dash.no_update

    if triggered_id == "payment-history-table" and active_cell:
        col_id = active_cell['column_id']
        row_data = history_data[active_cell['row']]

        # --- Logic for Commission Receipt ---
        if col_id == 'Commission Receipt':
            # We assume a receipt is "unpaid" until paid, or you can fetch its actual status
            commission_status = row_data.get('payment_commission_status',
                                             'unpaid').lower()  # Assuming a new column for status
            modal_content = create_receipt_modal_layout(
                ref=row_data.get('payment_commission_reference', 'N/A'),
                date=row_data['Date Processed'],
                coop_name=row_data['Cooperative'],
                total_tsh=row_data.get('total_amount_raw', 0),
                commission_usd=row_data.get('payment_commission_usd_raw', 0)
            )
            download_data = {
                'type': 'payment_receipt',
                'ref': row_data.get('payment_commission_reference', 'N/A'),
                'date': row_data['Date Processed'],
                'coop_name': row_data['Cooperative'],
                'total_tsh': row_data.get('total_amount_raw', 0),
                'commission_usd': row_data.get('payment_commission_usd_raw', 0),
                'status': commission_status  # Pass the status
            }
            return True, modal_content, download_data

        # --- Logic for Service Invoice ---
        if col_id == 'Service Invoice':
            modal_content = create_invoice_modal_layout(
                ref=row_data.get('invoice_reference', 'N/A'),
                date=row_data.get('submission_timestamp_display', 'N/A'),
                coop_name=row_data['Cooperative'],
                rows=row_data.get('row_count', 0),
                amount=row_data.get('amount_usd_raw', 0),
                status=row_data.get('status', 'unpaid').lower()
            )
            download_data = {
                'type': 'service_invoice',
                'ref': row_data.get('invoice_reference', 'N/A'),
                'date': row_data.get('submission_timestamp_display', 'N/A'),
                'coop_name': row_data['Cooperative'],
                'rows': row_data.get('row_count', 0),
                'amount': row_data.get('amount_usd_raw', 0),
                'status': row_data.get('status', 'unpaid').lower()
            }
            return True, modal_content, download_data

    return is_open, dash.no_update, dash.no_update


@app.callback(
    Output("download-pdf", "data"),
    Input("download-pdf-button", "n_clicks"),
    State("current-download-data", "data"),
    prevent_initial_call=True
)
def download_pdf(n_clicks, download_data):
    if not n_clicks or not download_data:
        raise dash.exceptions.PreventUpdate

    doc_type = download_data.get('type')
    doc_ref = download_data.get('ref', 'download')

    if doc_type == 'service_invoice':
        pdf_bytes = generate_service_invoice_pdf(
            ref=download_data.get('ref'),
            date=download_data.get('date'),
            coop_name=download_data.get('coop_name'),
            rows=download_data.get('rows'),
            amount=download_data.get('amount'),
            status=download_data.get('status')
            # REMOVED: logos=ASSET_URLS
        )
    elif doc_type == 'payment_receipt':
        pdf_bytes = generate_payment_receipt_pdf(
            ref=download_data.get('ref'),
            date=download_data.get('date'),
            coop_name=download_data.get('coop_name'),
            total_tsh=download_data.get('total_tsh'),
            commission_usd=download_data.get('commission_usd')
            # REMOVED: logos=ASSET_URLS
        )
    else:
        raise dash.exceptions.PreventUpdate

    return dcc.send_bytes(pdf_bytes, f"{doc_ref}.pdf")


@app.callback(Output("activity-logs-placeholder", "children"), Input("admin-tabs", "active_tab"),
              Input("ipn-data-store", "data"),
              Input({'type': 'log-activity-trigger', 'coop_name': 'dummy', 'action': 'dummy'}, 'children'))
def render_admin_activity_logs(active_tab, ipn_data, log_trigger):
    query = "SELECT L.timestamp, U.username, U.cooperative_name, L.action, L.details FROM activity_logs L JOIN users U ON L.user_id = U.id ORDER BY L.timestamp DESC"
    styling = [
        {'if': {'filter_query': '{Action} = "Password Change"'}, 'backgroundColor': '#fff3cd', 'color': '#856404',
         'fontWeight': 'bold'},
        {'if': {'filter_query': '{Action} = "User Created"'}, 'backgroundColor': '#d4edda', 'color': '#155724'}]
    return render_admin_data_table(query, active_tab, "tab-logs", styling=styling)


@app.callback(Output("analytics-tab-content", "children"), Input("admin-tabs", "active_tab"),
              Input("ipn-data-store", "data"))
def render_analytics_tab(active_tab, ipn_data):
    if active_tab != "tab-analytics": return dash.no_update
    with get_db_connection() as conn:
        query = "SELECT b.submission_timestamp, u.cooperative_name, p.farmer_name, p.bank_name, p.amount, p.status FROM farmer_payments p JOIN submission_batches b ON p.batch_id = b.id JOIN users u ON b.cooperative_id = u.id"
        df = pd.read_sql_query(query, conn)

    if df.empty: return dbc.Alert("No data available to generate analytics.", color="info")
    df['date'] = pd.to_datetime(df['submission_timestamp']).dt.date
    df_paid = df[df['status'] == 'paid']
    bank_activity = df_paid.groupby('bank_name').agg(total_amount=('amount', 'sum'), account_holders=(
        'farmer_name', 'nunique')).reset_index().sort_values('total_amount', ascending=False)
    coop_activity = df_paid.groupby('cooperative_name').agg(total_amount=('amount', 'sum'),
                                                            members=('farmer_name', 'nunique')).reset_index()
    daily_trends = df_paid.groupby('date').agg(total_amount=('amount', 'sum')).reset_index()
    status_distribution = df.groupby(['date', 'status']).size().reset_index(name='value')
    fig_bank_amount = px.bar(bank_activity.head(10), x='bank_name', y='total_amount',
                             title='Top 10 Banks by Transaction Value')
    fig_coop_value = px.pie(coop_activity, names='cooperative_name', values='total_amount',
                            title='Transaction Value by Cooperative')
    fig_daily_trend = px.line(daily_trends, x='date', y='total_amount', title='Daily Transaction Volume (Amount)',
                              markers=True)
    fig_status_dist = px.bar(status_distribution, x='date', y='value', color='status',
                             title='Paid vs. Failed Transactions Over Time', barmode='stack',
                             color_discrete_map={'paid': 'green', 'failed': 'red', 'pending': 'orange'})
    return html.Div([dbc.Row([dbc.Col(dcc.Graph(figure=fig_daily_trend), width=12)]), html.Hr(),
                     dbc.Row([dbc.Col(dcc.Graph(figure=fig_status_dist), width=12)]), html.Hr(),
                     dbc.Row([dbc.Col(dcc.Graph(figure=fig_bank_amount), md=6),
                              dbc.Col(dcc.Graph(figure=fig_coop_value), md=6)])])


@app.callback(Output("coop-analytics-content", "children"), Input("coop-tabs", "active_tab"),
              Input("user-session", "data"), Input("coop-alert", "is_open"))
def render_cooperative_analytics(active_tab, session_data_obfuscated, alert_is_open):
    if active_tab != "tab-coop-analytics": return dash.no_update
    session_data = deserialize_session(session_data_obfuscated)
    if not session_data or session_data.get("role") not in ["coop_uploader", "coop_approver"]: return None
    coop_name = session_data.get('cooperative_name')
    with get_db_connection() as conn:
        query = """SELECT b.submission_timestamp, p.farmer_name, p.bank_name, p.amount, p.status, p.verification_status FROM farmer_payments AS p JOIN submission_batches AS b ON p.batch_id = b.id JOIN users AS u ON b.cooperative_id = u.id WHERE u.cooperative_name = ?"""
        df = pd.read_sql_query(query, conn, params=(coop_name,))

    if df.empty: return dbc.Alert("No data available to generate analytics.", color="info")
    df['date'] = pd.to_datetime(df['submission_timestamp']).dt.date
    total_submitted_count = len(df)
    failed_verification_count = len(df[df['verification_status'] == 'failed'])
    df_paid = df[df['status'] == 'paid'].copy()
    total_submitted_amount = df['amount'].sum()
    total_paid_amount = df_paid['amount'].sum()
    total_farmers_paid = df_paid['farmer_name'].count()
    success_rate = (total_farmers_paid / total_submitted_count) * 100 if total_submitted_count > 0 else 0
    kpi_cards = dbc.Row([dbc.Col(dbc.Card(dbc.CardBody(
        [html.H4(f"TSH {total_submitted_amount:,.2f}"), html.P("Total Submitted Value", className="text-muted")])),
        md=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H4(f"TSH {total_paid_amount:,.2f}"),
                                       html.P("Total Amount Paid", className="text-muted")])), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H4(f"{failed_verification_count:,}"),
                                       html.P("Verification Failures", className="text-danger")])),
                md=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H4(f"{success_rate:.2f}%"),
                                       html.P("Payment Success Rate", className="text-muted")])),
                md=3)])
    status_counts = df['status'].value_counts().reset_index()
    status_counts.columns = ['status', 'count']
    fig_status = px.pie(status_counts, names='status', values='count', title='Payment Status Distribution',
                        color='status', color_discrete_map={'paid': 'green', 'failed': 'red', 'pending': 'orange'})
    return html.Div([kpi_cards, html.Hr(), dbc.Row([dbc.Col(dcc.Graph(figure=fig_status), md=6)])])


@app.callback(Output("coop-activity-logs-placeholder", "children"), Input("coop-tabs", "active_tab"),
              Input("user-session", "data"), Input("submission-trigger-store", "data"))
def render_coop_activity_logs(active_tab, session_data_obfuscated, submission_trigger):
    if active_tab != "tab-coop-logs": return dash.no_update
    session_data = deserialize_session(session_data_obfuscated)
    if not session_data or session_data.get("role") != "coop_approver": return None
    coop_name = session_data['cooperative_name']

    query = "SELECT timestamp, username, action, details FROM activity_logs JOIN users ON activity_logs.user_id = users.id WHERE users.cooperative_name = ? ORDER BY timestamp DESC"
    return render_admin_data_table(
        query,
        active_tab,
        "tab-coop-logs",
        params=(coop_name,)
    )


@app.callback(
    Output("coop-history-placeholder", "children"),
    Input("coop-tabs", "active_tab"), Input("user-session", "data"), Input("coop-alert", "is_open"),
    Input("submission-trigger-store", "data")
)
def render_coop_history(active_tab, session_data_obfuscated, alert_is_open, submission_trigger):
    if active_tab != "tab-coop-history": return None
    session_data = deserialize_session(session_data_obfuscated)
    if not session_data or session_data.get("role") not in ["coop_uploader", "coop_approver"]: return None
    coop_name = session_data['cooperative_name']
    with get_db_connection() as conn:
        query = """
            SELECT b.id, b.filename, b.status, b.admin_notes, b.submission_timestamp, u.username 
            FROM submission_batches b
            JOIN users u ON b.cooperative_id = u.id
            WHERE u.cooperative_name = ?
            ORDER BY b.submission_timestamp DESC
        """
        df = pd.read_sql_query(query, conn, params=(coop_name,))

    if df.empty: return dbc.Alert("No submissions yet.", color="info")

    def get_badge(status):
        if status == 'processed': return dbc.Badge("Processed (Paid)", className="ms-2", color="success")
        if status == 'verified': return dbc.Badge("Verified (Ready to Pay)", className="ms-2", color="primary")
        if status == 'coop_submitted': return dbc.Badge("Awaiting Your Payment Authorization", className="ms-2",
                                                        color="danger")
        if status == 'pending_admin_approval': return dbc.Badge("Awaiting Admin Verification", className="ms-2",
                                                                color="warning")
        return dbc.Badge(status.replace('_', ' ').title(), className="ms-2", color="info")

    return dbc.Accordion([
        dbc.AccordionItem([
            html.P(
                f"Submitted by: {row['username']} on: {datetime.strptime(row['submission_timestamp'].split('.')[0], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %I:%M %p')}"),
            dbc.Alert(f"Admin Response: {row['admin_notes']}", color="info") if row['admin_notes'] else "",
            dbc.Button("View Results", id={'type': 'view-results-btn', 'index': row['id']}) if row[
                                                                                                   'status'] == 'processed' else ""
        ], title=html.Div([row['filename'], get_badge(row['status'])]))
        for _, row in df.iterrows()
    ], start_collapsed=True)


@app.callback(
    Output('coop-results-modal', 'is_open'), Output('coop-results-modal', 'children'),
    Input({'type': 'view-results-btn', 'index': ALL}, 'n_clicks'), prevent_initial_call=True
)
def show_coop_results_modal(n_clicks):
    if not any(n_clicks): return False, None
    batch_id = int(eval(callback_context.triggered[0]['prop_id'].split('.')[0])['index'])
    with get_db_connection() as conn:
        df = pd.read_sql_query(
            "SELECT farmer_name, bank_name, account_number, amount, verification_status, verification_reason, status, failure_reason FROM farmer_payments WHERE batch_id = ?",
            conn, params=(batch_id,))

    style_data_conditional = [
        {'if': {'filter_query': '{verification_status} = "verified"'}, 'backgroundColor': '#e8f5e9'},
        {'if': {'filter_query': '{verification_status} = "failed"'}, 'backgroundColor': '#ffebee',
         'fontWeight': 'bold'},
        {'if': {'filter_query': '{status} = "paid"'}, 'backgroundColor': '#d4edda', 'fontWeight': 'bold'},
        {'if': {'filter_query': '{status} = "failed"'}, 'backgroundColor': '#f8d7da', 'fontWeight': 'bold'}
    ]

    return True, [
        dbc.ModalHeader(f"Payment Results (Batch ID: {batch_id})"),
        dbc.ModalBody(dash_table.DataTable(
            data=df.to_dict('records'), columns=[{'name': i.replace('_', ' ').title(), 'id': i} for i in df.columns],
            style_table={'overflowX': 'auto'}, editable=False,
            style_data_conditional=style_data_conditional,
            export_format="csv",  # --- ADDED ---
        ))
    ]


@app.callback(
    Output("details-modal", "is_open"), Output("details-modal", "children"),
    Input({'type': 'view-details-btn', 'index': ALL}, 'n_clicks'),
    State("user-session", "data"),
    prevent_initial_call=True
)
def toggle_details_modal(n_clicks, session_data_obfuscated):
    ctx = callback_context
    if not any(n_clicks) or not ctx.triggered:
        return False, None

    session_data = deserialize_session(session_data_obfuscated)

    # --- This modal is for ADMINS ONLY ---
    if not session_data or session_data.get("role") != "admin":
        return False, None

    try:
        prop_id_dict = json.loads(ctx.triggered[0]['prop_id'].split('.')[0])
        if prop_id_dict.get('type') != 'view-details-btn':
            return False, None  # Not the right button type
    except:
        return False, None  # Error parsing ID

    batch_id = int(eval(callback_context.triggered[0]['prop_id'].split('.')[0])['index'])
    with get_db_connection() as conn:
        df = pd.read_sql_query(
            "SELECT farmer_name, bank_name, account_number, amount, verification_status, verification_reason, status, failure_reason FROM farmer_payments WHERE batch_id = ?",
            conn, params=(batch_id,))
        notes_df = pd.read_sql_query(
            "SELECT filename, admin_notes, cooperative_notes FROM submission_batches WHERE id = ?", conn,
            params=(batch_id,))

    filename = notes_df['filename'].iloc[0]
    admin_note, coop_note = notes_df['admin_notes'].iloc[0] or "", notes_df['cooperative_notes'].iloc[0]
    style_data_conditional = [
        {'if': {'filter_query': '{verification_status} = "verified"'}, 'backgroundColor': '#e8f5e9'},
        {'if': {'filter_query': '{verification_status} = "failed"'}, 'backgroundColor': '#ffebee'},
        {'if': {'filter_query': '{status} = "paid"'}, 'backgroundColor': '#c8e6c9', 'fontWeight': 'bold'},
        {'if': {'filter_query': '{status} = "failed"'}, 'backgroundColor': '#ffcdd2', 'fontWeight': 'bold'}
    ]

    return True, [
        dbc.ModalHeader(f"Submission Details (Batch ID: {batch_id}) - {filename}"),
        dbc.ModalBody([
            html.H5("Account & Payment Status Overview"),
            dash_table.DataTable(
                data=df.to_dict('records'),
                columns=[{'name': i.replace('_', ' ').title(), 'id': i} for i in df.columns],
                style_table={'maxHeight': '40vh', 'overflowY': 'auto'},
                style_data_conditional=style_data_conditional,
                style_header={'backgroundColor': 'lightgray', 'fontWeight': 'bold'},
                editable=True,
                export_format="csv",  # --- ADDED ---
            ),
            html.Hr(),
            html.H5("Communication"),
            dbc.Label("Note from Cooperative:"),
            dbc.Alert(coop_note, color="info") if coop_note else html.P("No note provided.",
                                                                        className="text-muted fst-italic"),
            dbc.Label("Your Response to Cooperative:", className="mt-2"),
            dbc.Alert(id="note-save-alert", is_open=False, duration=3000),
            dcc.Textarea(id={'type': 'admin-note-textarea', 'index': batch_id}, value=admin_note,
                         style={'width': '100%', 'height': 100}),
            dbc.Button("Save Response", id={'type': 'save-note-btn', 'index': batch_id}, color="primary",
                       className="mt-2")
        ])
    ]


@app.callback(
    Output("note-save-alert", "is_open"), Output("note-save-alert", "children"), Output("note-save-alert", "color"),
    Input({'type': 'save-note-btn', 'index': ALL}, 'n_clicks'),
    State({'type': 'admin-note-textarea', 'index': ALL}, 'value'),
    prevent_initial_call=True
)
def save_admin_note(n_clicks, notes):
    if not any(n_clicks): return False, "", ""
    ctx = callback_context.triggered[0]
    batch_id = int(eval(ctx['prop_id'].split('.')[0])['index'])
    note_value = notes[0] if notes and notes[0] is not None else ""

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE submission_batches SET admin_notes = ? WHERE id = ?", (note_value, batch_id))
            conn.commit()
        return True, "Response saved successfully!", "success"
    except Exception as e:
        return True, f"Error saving response: {e}", "danger"


@app.callback(
    Output("password-change-toast", "is_open"),
    Output("password-change-toast", "header"),
    Output("password-change-toast", "children"),
    Output("password-change-toast", "icon"),
    Input("user-session", "data"),
    Input(
        {
            "type": "log-activity-trigger",
            "coop_name": ALL,
            "action": ALL
        },
        "children"
    ),
    prevent_initial_call=True
)
def show_password_change_toast(session_data_obfuscated, trigger_data):
    session_data = deserialize_session(session_data_obfuscated)
    if not session_data or session_data.get("role") != "admin": return False, "", "", ""

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT L.timestamp, U.username, U.cooperative_name
            FROM activity_logs L
            JOIN users U ON L.user_id = U.id
            WHERE L.action = 'Password Change'
            ORDER BY L.timestamp DESC
            LIMIT 1
        """)
        latest_change = cursor.fetchone()

    if latest_change:
        timestamp, username, coop_name = latest_change
        timestamp_dt = datetime.strptime(timestamp.split('.')[0], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p')
        header = "🔒 IMPORTANT: Credentials Change Alert"
        body = html.Div([
            html.P(f"User **{username}** ({coop_name}) changed their credentials at {timestamp_dt}."),
            html.P(f"Action logged in Activity Logs.")
        ])
        return True, header, body, "warning"
    return False, "", "", ""


if __name__ == "__main__":
    init_db()
    print("--- Farmers Payment Module Initialized ---")
    print(f"Admin: admin / admin123 | Approver: corecu_finance / coop123")
    print("---")
    print("Default Approver (corecu_finance) Auth Credentials:")
    print("Passphrase: cooppass")
    print("PIN: 123456")
    app.run(debug=True, port=8659)
