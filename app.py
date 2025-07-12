from flask import Flask, render_template, request, redirect, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import redis

app = Flask(__name__)
app.secret_key = 'secret-key'

# MongoDB setup
client = MongoClient('mongodb://localhost:27017')
db = client['restaurant_db']
users_col = db['users']
reservations_col = db['reservations']
tables_col = db['tables']

# Redis setup
try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    redis_client.ping()
except redis.exceptions.ConnectionError:
    redis_client = None
    print("❌ Redis tidak bisa terhubung.")

@app.route('/')
def index():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = users_col.find_one({'email': email, 'password': password})
        if user:
            session['user_id'] = str(user['_id'])
            session['name'] = user['name']
            session['role'] = user.get('role', 'user')  

            
            if redis_client:
                redis_client.hset(f"session:{user['_id']}", "name", user['name'])
                redis_client.hset(f"session:{user['_id']}", "email", user['email'])

           
            if session['role'] == 'admin':
                return redirect('/admin')
            else:
                return redirect('/home')
        else:
            flash('Login gagal! Email atau password salah.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        existing = users_col.find_one({'email': email})
        if existing:
            flash('Email sudah terdaftar!', 'error')
        else:
            users_col.insert_one({
                'name': name,
                'email': email,
                'password': password,
                'role': 'user',  # Tambahkan role default
                'registered_at': datetime.now()
            })
            flash('Registrasi berhasil, silakan login!', 'success')
            return redirect('/login')
    return render_template('register.html')



@app.route("/home")
def home():
    return render_template("home.html")


@app.route('/reservasi', methods=['GET', 'POST'])
def reservasi():
    if 'user_id' not in session:
        return redirect('/login')

    user = users_col.find_one({'_id': ObjectId(session['user_id'])})
    if not user:
        flash('User tidak ditemukan.', 'error')
        return redirect('/login')

    name = user['name']
    guests = request.form.get('guests')
    tables = []
    show_full_form = False

    if request.method == 'POST':
        
        if 'table_id' in request.form:
            # Form kedua (lengkap)
            table_id = request.form['table_id']
            date = request.form['date']
            time = request.form['time']
            guests = int(request.form['guests'])
            notes = request.form['notes']

            selected_table = tables_col.find_one({'table_id': table_id})
            if not selected_table or selected_table['status'] == 'booked':
                flash('Meja tidak tersedia.', 'error')
                return redirect('/reservasi')

            if guests > selected_table.get('capacity', 0):
                flash('Jumlah tamu melebihi kapasitas meja.', 'warning')
                return redirect('/reservasi')

            existing = reservations_col.find_one({
                'table_id': table_id,
                'date': date,
                'time': time
            })
            if existing:
                flash('Meja sudah dipesan di waktu tersebut.', 'warning')
                return redirect('/reservasi')

            reservations_col.insert_one({
                'user_id': ObjectId(session['user_id']),
                'user_name': name,
                'table_id': table_id,
                'date': date,
                'time': time,
                'guests': guests,
                'notes': notes,
                'status': 'Pending',
                'created_at': datetime.now()
            })

            tables_col.update_one({'table_id': table_id}, {'$set': {'status': 'Pending'}})
            flash('Reservasi berhasil!', 'success')
            return redirect('/home')

        else:
            # Form pertama (isi jumlah tamu saja)
            try:
                guests = int(guests)
                show_full_form = True
                tables = list(tables_col.find({
                    'status': {'$ne': 'booked'},
                    'capacity': {'$gte': guests}
                }))
            except (TypeError, ValueError):
                flash('Jumlah tamu tidak valid.', 'error')
                return redirect('/reservasi')

    return render_template('reservation.html', name=name, tables=tables, guests=guests, show_form=show_full_form)

@app.route('/meja')
def daftar_meja():
    tables = list(db.tables.find())
    return render_template('tables.html', tables=tables)

@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Akses ditolak! Hanya admin yang bisa mengakses halaman ini.", "error")
        return redirect('/login')

    q = request.args.get('q', '').strip()

    if q:
        reservations = list(reservations_col.find({
            'user_name': {'$regex': q, '$options': 'i'}  
        }).sort('created_at', -1))
    else:
        reservations = list(reservations_col.find().sort('created_at', -1))

    return render_template('dashboard.html', reservations=reservations)

@app.route('/admin/users')
def admin_users():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Akses ditolak! Hanya admin yang bisa mengakses halaman ini.", "error")
        return redirect('/home')

    users = list(users_col.find())
    return render_template('users.html', users=users)


@app.route('/admin/reservasi/<reservation_id>/approve', methods=['POST'])
def approve_reservation(reservation_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Akses ditolak!", "error")
        return redirect('/login')

    reservation = reservations_col.find_one({'_id': ObjectId(reservation_id)})
    if reservation and reservation.get('status', '').lower() == 'pending':
        reservations_col.update_one(
            {'_id': ObjectId(reservation_id)},
            {'$set': {'status': 'Approved'}}
        )
        tables_col.update_one(
            {'table_id': reservation['table_id']},
            {'$set': {'status': 'booked'}}
        )
        flash("Reservasi disetujui.", "success")
    else:
        flash("Reservasi tidak ditemukan atau sudah diproses.", "error")
    return redirect('/admin')


@app.route('/admin/reservasi/<reservation_id>/reject', methods=['POST'])
def reject_reservation(reservation_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Akses ditolak!", "error")
        return redirect('/login')

    reservation = reservations_col.find_one({'_id': ObjectId(reservation_id)})
    if reservation and reservation.get('status', '').lower() == 'pending':
        reservations_col.update_one(
            {'_id': ObjectId(reservation_id)},
            {'$set': {'status': 'rejected'}}
        )
        tables_col.update_one(
            {'table_id': reservation['table_id']},
            {'$set': {'status': 'available'}}
        )
        flash("Reservasi ditolak.", "warning")
    else:
        flash("Reservasi tidak ditemukan atau sudah diproses.", "error")
    return redirect('/admin')

@app.route('/reservasi/delete/<reservation_id>', methods=['POST'])
def delete_reservation(reservation_id):
    if 'user_id' not in session:
        return redirect('/login')

    reservation = reservations_col.find_one({'_id': ObjectId(reservation_id)})

    if reservation:
        table_id = reservation['table_id']
        reservations_col.delete_one({'_id': ObjectId(reservation_id)})
        tables_col.update_one({'table_id': table_id}, {'$set': {'status': 'available'}})
        flash('Reservasi berhasil dihapus.', 'success')
    else:
        flash('Reservasi tidak ditemukan.', 'error')

    return redirect('/admin')

@app.route('/admin/tables', methods=['GET', 'POST'])
def admin_tables():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Akses ditolak!", "error")
        return redirect('/login')

    tables = list(tables_col.find())

    popular_tables = reservations_col.aggregate([
        {"$group": {"_id": "$table_id", "jumlah_reservasi": {"$sum": 1}}},
        {"$sort": {"jumlah_reservasi": -1}},
        {"$limit": 5}
    ])

    popular_tables = list(popular_tables)

    return render_template('admin_tables.html', tables=tables, popular_tables=popular_tables)

@app.route('/admin/table/<table_id>/set_available', methods=['POST'])
def set_table_available(table_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Akses ditolak!", "error")
        return redirect('/login')

    
    tables_col.update_one({'table_id': table_id}, {'$set': {'status': 'available'}})

    updated_res = reservations_col.find_one_and_update(
        {'table_id': table_id, 'status': {'$regex': '^approved$', '$options': 'i'}},
        {'$set': {'status': 'confirmed'}}
    )

    if updated_res:
        flash(f"Meja {table_id} telah di-set ke 'available'. Reservasi terkait dikonfirmasi.", "success")
    else:
        flash(f"Meja {table_id} telah di-set ke 'available'. Tidak ada reservasi yang dikonfirmasi.", "info")

    return redirect('/admin/tables')


@app.route('/logout')
def logout():
    session.clear()
    flash("Anda telah logout.", 'info')
    return redirect('/login')

if __name__ == '__main__':
    app.run(debug=True)
