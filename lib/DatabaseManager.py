# DatabaseManager.py
#
# Fase 1 (bugs críticos) - FOG Cloning Control
# Autores: Fernando Gietz + Claude Sonnet 5
#
# Cambios de esta fase respecto al original:
#   - get_connection() volvía a lanzar la excepción de conexión tras
#     limitarse a un print(), lo que hacía que el generador decorado con
#     @contextmanager terminara sin pasar por el yield. Al ser así, el
#     propio `with self.get_connection() as connection:` fallaba con
#     RuntimeError: generator didn't yield en su __enter__, ANTES de entrar
#     al bloque `with` - por lo que el try/except que rodea las operaciones
#     en execute_query/execute_update nunca llegaba a ejecutarse para este
#     caso, y el RuntimeError se propagaba sin control hasta matar el
#     daemon completo ante cualquier incidencia de conectividad con MySQL.
#   - Ahora get_connection() vuelve a lanzar (`raise`) la excepción Error
#     tras loguearla, y execute_query()/execute_update() envuelven también
#     la apertura de la conexión en su propio try/except, devolviendo
#     None/False de forma controlada - igual que ya hacían ante un fallo de
#     la propia consulta.

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
            # Se relanza para que el fallo se gestione de forma controlada
            # en execute_query()/execute_update(), en vez de dejar que el
            # generador termine sin yield.
            raise
        finally:
            if connection and connection.is_connected():
                connection.close()

    def execute_query(self, query, params=None):
        try:
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
        except Error as e:
            # Fallo al obtener la conexión (host caído, credenciales
            # inválidas, timeout, demasiadas conexiones, etc.). Antes esto
            # se propagaba como RuntimeError sin control; ahora se captura
            # aquí y se devuelve None, igual que ante un fallo de consulta.
            print(f"Error obtaining MySQL connection: {e}")
            return None

    def execute_update(self, query, params=None):
        try:
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
        except Error as e:
            print(f"Error obtaining MySQL connection: {e}")
            return False
