from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from functools import wraps
import oracledb
import io
import csv
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_mail import Mail, Message

app = Flask(__name__)
app.secret_key = 'secret123'

# ---------------- EMAIL CONFIG ---------------- #
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'anikatalavadekar@gmail.com'   
app.config['MAIL_PASSWORD'] = 'jasj kxxj ycjm mqye'      

mail = Mail(app)

def send_email(to, subject, body):
    try:
        msg = Message(subject,
                      sender=app.config['MAIL_USERNAME'],
                      recipients=[to])
        msg.body = body
        mail.send(msg)
    except Exception as e:
        print("EMAIL ERROR:", e)

# ---------------- DATABASE ---------------- #
def get_db_connection():
    dsn = oracledb.makedsn("localhost", 1521, service_name="XEPDB1")
    return oracledb.connect(user="LIBDB", password="0307", dsn=dsn)

# ---------------- AUTH ---------------- #
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Login required', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user_role = session.get('role', '').strip().lower()
            allowed_roles = [r.strip().lower() for r in roles]
            if user_role not in allowed_roles:
                flash('Access Denied', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return wrapper
    return decorator

ADMIN_EMAIL = 'admin@library.com'

# ---------------- REGISTER ---------------- #
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        department = request.form.get('department')

        if not all([name, email, password, department]):
            flash('All fields required!', 'danger')
            return redirect(url_for('register'))

        if email.lower() == ADMIN_EMAIL:
            flash('Admin email not allowed', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO LIB_USER (USER_ID, Name, Email, Role, Department, Password)
                VALUES (user_seq.NEXTVAL, :name, :email, 'Student', :department, :password)
            """, {
                "name": name,
                "email": email,
                "department": department,
                "password": hashed_password
            })

            conn.commit()
            flash('Registered successfully!', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            print(e)
            flash('Registration failed!', 'danger')

        finally:
            cursor.close()
            conn.close()

    return render_template('register.html')

# ---------------- LOGIN ---------------- #
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT User_ID, Name, Role, Password 
            FROM LIB_USER 
            WHERE Email=:email
        """, {"email": email})

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row and check_password_hash(row[3], password):
            session['user_id'] = row[0]
            session['name'] = row[1]
            session['role'] = row[2].strip().lower()
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))

        flash('Invalid email or password', 'danger')

    return render_template('login.html')

# ---------------- LOGOUT ---------------- #
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('login'))

# ---------------- DASHBOARD ---------------- #
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*),
        SUM(CASE WHEN Availability_Status='Available' THEN 1 ELSE 0 END),
        SUM(CASE WHEN Availability_Status='Borrowed' THEN 1 ELSE 0 END)
        FROM BOOK
    """)

    total, available, issued = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template('dashboard.html',
                           total_books=total or 0,
                           available=available or 0,
                           issued=issued or 0)

# ---------------- BOOKS ---------------- #
@app.route('/books')
@login_required
def books():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT b.Book_ID, b.Title, b.ISBN, b.Availability_Status,
               br.User_ID,
               u.Name, u.Email,
               br.Borrow_Date, br.Due_Date
        FROM BOOK b
        LEFT JOIN BORROW br 
            ON b.Book_ID = br.Book_ID AND br.Status = 'Borrowed'
        LEFT JOIN LIB_USER u 
            ON br.User_ID = u.User_ID
    """)

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    books = []
    for r in rows:
        books.append({
            "id": r[0],
            "title": r[1],
            "isbn": r[2],
            "status": r[3],
            "borrowed_by": r[4],
            "user_name": r[5],
            "user_email": r[6],
            "borrow_date": r[7],
            "due_date": r[8]
        })

    return render_template('books.html', books=books, now=datetime.now())
# ---------------- ADD BOOK ---------------- #
@app.route('/add-book', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def add_book():
    if request.method == 'POST':
        title = request.form.get('title')
        isbn = request.form.get('isbn')

        if not title or not isbn:
            flash("Title and ISBN required!", "danger")
            return redirect(url_for('add_book'))

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO BOOK 
                (Book_ID, Title, ISBN, Type, Publication_Year, Availability_Status, Category_ID, Publisher_ID)
                VALUES 
                ((SELECT NVL(MAX(Book_ID),0)+1 FROM BOOK),
                 :title, :isbn, 'Programming', 2024, 'Available', 1, 1)
            """, {"title": title, "isbn": isbn})

            conn.commit()
            flash('Book added successfully!', 'success')

        except Exception as e:
            print(e)
            flash('Error adding book!', 'danger')

        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('books'))

    return render_template('add_book.html')


# ---------------- BORROW ---------------- #
@app.route('/checkout_book/<int:book_id>', methods=['POST'])
@login_required
def checkout_book(book_id):
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT Availability_Status FROM BOOK WHERE Book_ID=:id", {"id": book_id})
        row = cursor.fetchone()

        if not row or row[0] != 'Available':
            flash("Book not available!", "danger")
            return redirect(url_for('books'))

        cursor.execute("""
            INSERT INTO BORROW (Borrow_ID, User_ID, Book_ID, Borrow_Date, Due_Date, Status)
            VALUES (borrow_seq.NEXTVAL, :user_id, :book_id, SYSDATE, SYSDATE+7, 'Borrowed')
        """, {"user_id": user_id, "book_id": book_id})

        cursor.execute("UPDATE BOOK SET Availability_Status='Borrowed' WHERE Book_ID=:id", {"id": book_id})

        conn.commit()

        # EMAIL
        cursor.execute("SELECT Email FROM LIB_USER WHERE User_ID=:id", {"id": user_id})
        user_email = cursor.fetchone()[0]

        send_email(user_email, "Book Borrowed 📚",
                   f"You borrowed book ID {book_id}. Return within 7 days.")

        flash("Book borrowed successfully!", "success")

    except Exception as e:
        print("BORROW ERROR:", e)
        flash("Error borrowing book!", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('books'))

# ---------------- RETURN ---------------- #
@app.route('/return_book/<int:book_id>', methods=['POST'])
@login_required
def return_book(book_id):
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT Borrow_ID, Due_Date FROM BORROW
            WHERE Book_ID=:book_id AND User_ID=:user_id AND Status='Borrowed'
        """, {"book_id": book_id, "user_id": user_id})

        row = cursor.fetchone()

        if not row:
            flash("Invalid return!", "danger")
            return redirect(url_for('books'))

        borrow_id, due_date = row

        fine = 0
        if due_date:
            days_late = (datetime.now() - due_date).days
            if days_late > 0:
                fine = days_late * 5

        cursor.execute("""
            UPDATE BORROW
            SET Return_Date=SYSDATE, Fine=:fine, Status='Returned'
            WHERE Borrow_ID=:id
        """, {"fine": fine, "id": borrow_id})

        cursor.execute("UPDATE BOOK SET Availability_Status='Available' WHERE Book_ID=:id", {"id": book_id})

        conn.commit()

        # EMAIL
        cursor.execute("SELECT Email FROM LIB_USER WHERE User_ID=:id", {"id": user_id})
        user_email = cursor.fetchone()[0]

        send_email(user_email, "Book Returned ✅",
                   f"Book returned. Fine: ₹{fine}")

        flash(f"Returned! Fine: ₹{fine}", "success")

    except Exception as e:
        print("RETURN ERROR:", e)
        flash("Error returning book!", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('books'))

# ---------------- SEARCH PAGE ---------------- #
@app.route('/search')
@login_required
def search():
    return render_template('search.html')

# ---------------- HOME ---------------- #
@app.route('/')
def home():
    return render_template('index.html')

# ---------------- RUN ---------------- #
if __name__ == '__main__':
    app.run(debug=True)