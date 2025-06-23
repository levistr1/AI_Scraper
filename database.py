import mysql.connector

class Database:
    def __init__(self):
        self.connection = None

    def connect(self):
        self.connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Summer2025!",
            database="real_estate_ai")

    def get_all_sites(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name, url FROM site")
        return cursor.fetchall()
    
    def get_all_listings(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM listings")
        return cursor.fetchall()