from flask import Flask, render_template, request, redirect, session, url_for, flash, make_response
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # change this

DB = 'expenses.db'

# Initialize DB and create tables
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    # Users table with hashed password
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                 )''')
    # Expenses table linked to user
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    category TEXT,
                    description TEXT,
                    date TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                 )''')
    conn.commit()
    conn.close()

# Helper to get DB connection
def get_db_connection():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    error = None
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid username or password"

    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    error = None
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            error = "Passwords do not match"
        else:
            hashed_password = generate_password_hash(password)

            try:
                conn = get_db_connection()
                conn.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                             (username, hashed_password))
                conn.commit()
                conn.close()
                flash("Registration successful! Please login.")
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                error = "Username already exists"

    return render_template('register.html', error=error)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    username = session['username']

    if request.method == 'POST':
        amount = request.form['amount']
        category = request.form['category'].strip()
        description = request.form['description'].strip()
        date = request.form['date']

        conn = get_db_connection()
        conn.execute('INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, ?, ?, ?, ?)',
                     (user_id, amount, category, description, date))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    expenses = conn.execute('SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC', (user_id,)).fetchall()

    today = datetime.today()
    current_month = today.strftime('%Y-%m')
    current_year = today.strftime('%Y')

    # Monthly total
    monthly_total = conn.execute(
        "SELECT IFNULL(SUM(amount), 0) FROM expenses WHERE user_id = ? AND substr(date,1,7) = ?",
        (user_id, current_month)).fetchone()[0]

    # Annual total
    annual_total = conn.execute(
        "SELECT IFNULL(SUM(amount), 0) FROM expenses WHERE user_id = ? AND substr(date,1,4) = ?",
        (user_id, current_year)).fetchone()[0]

    # Monthly expenses by category
    monthly_data = conn.execute(
        "SELECT category, IFNULL(SUM(amount), 0) as total FROM expenses WHERE user_id = ? AND substr(date,1,7) = ? GROUP BY category",
        (user_id, current_month)).fetchall()

    # Annual expenses by category
    annual_data = conn.execute(
        "SELECT category, IFNULL(SUM(amount), 0) as total FROM expenses WHERE user_id = ? AND substr(date,1,4) = ? GROUP BY category",
        (user_id, current_year)).fetchall()

    conn.close()

    monthly_categories = [row['category'] for row in monthly_data]
    monthly_amounts = [row['total'] for row in monthly_data]

    annual_categories = [row['category'] for row in annual_data]
    annual_amounts = [row['total'] for row in annual_data]

    return render_template('dashboard.html',
                           user=username,
                           expenses=expenses,
                           monthly_total=monthly_total,
                           annual_total=annual_total,
                           monthly_categories=monthly_categories,
                           monthly_amounts=monthly_amounts,
                           annual_categories=annual_categories,
                           annual_amounts=annual_amounts)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/download_annual_report_pdf')
def download_annual_report_pdf():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    username = session.get('username', 'User')
    current_year = datetime.today().strftime('%Y')

    conn = get_db_connection()
    expenses = conn.execute(
        "SELECT date, category, description, amount FROM expenses WHERE user_id = ? AND substr(date,1,4) = ? ORDER BY date",
        (user_id, current_year)
    ).fetchall()
    conn.close()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Annual Expense Report - {current_year}", 0, 1, 'C')

    # Add username below the title
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"User: {username}", 0, 1, 'C')

    pdf.set_font("Arial", 'B', 12)
    pdf.cell(40, 10, "Date", 1)
    pdf.cell(50, 10, "Category", 1)
    pdf.cell(60, 10, "Description", 1)
    pdf.cell(30, 10, "Amount", 1, 1)

    pdf.set_font("Arial", '', 12)
    total_amount = 0
    for exp in expenses:
        pdf.cell(40, 10, exp['date'], 1)
        pdf.cell(50, 10, exp['category'], 1)
        description = exp['description'] if exp['description'] else '-'
        description = (description[:25] + '...') if len(description) > 28 else description
        pdf.cell(60, 10, description, 1)
        pdf.cell(30, 10, f"Rs.{exp['amount']:.2f}", 1, 1)
        total_amount += exp['amount']

    pdf.set_font("Arial", 'B', 12)
    pdf.cell(150, 10, "Total", 1)
    pdf.cell(30, 10, f"Rs.{total_amount:.2f}", 1, 1)

    response = make_response(pdf.output(dest='S').encode('latin-1'))
    response.headers.set('Content-Disposition', 'attachment', filename=f'annual_expense_report_{current_year}.pdf')
    response.headers.set('Content-Type', 'application/pdf')
    return response

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
