
from config import get_db_connection

connection = get_db_connection()

if connection.is_connected():
    print("Database Connected Successfully!")

connection.close()
