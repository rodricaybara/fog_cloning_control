# DatabaseManager.py

import mysql.connector
from mysql.connector import Error
from contextlib import contextmanager

class DatabaseManager:
    def __init__(self, host, user, password, database):
        self.host = host
        self.user = user
        self.password = password
        self.database = database

    @contextmanager
    def get_connection(self):
        connection = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
            yield connection
        except Error as e:
            print(f"Error connecting to MySQL database: {e}")
        finally:
            if connection and connection.is_connected():
                connection.close()

    def execute_query(self, query, params=None):
        with self.get_connection() as connection:
            cursor = connection.cursor()
            try:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                result = cursor.fetchall()
                return result
            except Error as e:
                print(f"Error executing query: {e}")
                return None
            finally:
                cursor.close()

    def execute_update(self, query, params=None):
        with self.get_connection() as connection:
            cursor = connection.cursor()
            try:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                connection.commit()
                return True
            except Error as e:
                print(f"Error executing update: {e}")
                connection.rollback()
                return False
            finally:
                cursor.close()