from config import get_db_connection
from werkzeug.security import generate_password_hash

username = input("Enter Admin Username: ")
password = input("Enter Admin Password: ")

hashed_password = generate_password_hash(password)

connection = get_db_connection()
cursor = connection.cursor()

query = """
INSERT INTO admin (username, password)
VALUES (%s, %s)
"""

cursor.execute(query, (username, hashed_password))

connection.commit()

print("Admin Account Created Successfully!")

cursor.close()
connection.close()