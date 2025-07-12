from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017')
db = client['restaurant_db']
tables_col = db['tables']

tables = []
for i in range(1, 41):
    table_id = f"TBL{i:02d}"
    capacity = 2 if i <= 10 else 4 if i <= 25 else 6 if i <= 35 else 8
    location = "Dekat jendela" if i % 4 == 0 else "Tengah ruangan" if i % 3 == 0 else "Pojok"
    status = "available"  # default status semua meja saat awal
    tables.append({
        "table_id": table_id,
        "capacity": capacity,
        "location": location,
        "status": status
    })

tables_col.insert_many(tables)
print("✅ 40 meja berhasil ditambahkan dengan status 'available'.")
