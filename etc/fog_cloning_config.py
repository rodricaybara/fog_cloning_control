# fog_cloning_config.py
#
# Fase 1 (bugs críticos) - FOG Cloning Control
# Autores: Fernando Gietz + Claude Sonnet 5
#
# Cambios de esta fase respecto al original:
#   - MYSQL_USER / MYSQL_PASSWORD ya no están hardcodeados en texto plano en
#     este fichero (versionable). Se cargan en tiempo de arranque desde un
#     fichero de secretos externo (SECRETS_FILE, ver más abajo), que debe
#     crearse manualmente con permisos 600 y quedar fuera del control de
#     versiones. Ver fog_cloning_secrets.ini.example en este mismo
#     directorio para el formato exacto y las instrucciones de despliegue.
#   - Si el fichero de secretos no existe o está mal formado, el servicio
#     falla de forma clara e inmediata al arrancar (fail-loud), en vez de
#     arrancar con credenciales incorrectas o vacías.
#
# El resto de bugs de Fase 1 (CPU_OVERLOADED, conexión MySQL, lecturas
# fallidas tratadas como 0, etc.) se corrigen en fog_control_functions.py y
# DatabaseManager.py, no en este fichero.

import os
import configparser

# Configuración
CPU_LIMIT = 90
CPU_THRESHOLD = 70
CPU_OVERLOADED = 0
NETWORK_LIMIT = 1000000000
SAMPLE_INTERVAL = 20
HISTORY_DURATION = 600
DEVICE_NAME = "VG_IMAGES_ISILONY"
HISTORY_FILE = "/opt/fog_cloning_control/log/fog_cloning_history.csv"
HISTORY_10_MINUTES_FILE = "/opt/fog_cloning_control/log/fog_cloning_history_10min.csv"
LOG_FILE = "/opt/fog_cloning_control/log/fog_cloning_control.log"
MODEL_PATHS = {
    "unicast_download_cpu": "/opt/fog_cloning_control/models/unicast_download_cpu_usage_rf.joblib",
    "unicast_upload_cpu": "/opt/fog_cloning_control/models/unicast_upload_cpu_usage_rf.joblib",
    "multicast_download_cpu": "/opt/fog_cloning_control/models/multicast_cpu_usage_rf.joblib"
}

# Parámetros del controlador PID
Kp = 0.1
Ki = 0.01
Kd = 0.01
integral_cpu = 0
integral_network = 0
last_cpu_error = 0
last_network_error = 0

# Configuración de MySQL
MYSQL_DATABASE = "fog"
MYSQL_HOST = "localhost"

# Fichero de secretos con las credenciales de MySQL (permisos 600, fuera de
# control de versiones). Se busca junto a este propio fichero de config.
SECRETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fog_cloning_secrets.ini")


def _load_mysql_credentials(secrets_file):
    if not os.path.exists(secrets_file):
        raise FileNotFoundError(
            f"No se encuentra el fichero de credenciales de MySQL: {secrets_file}\n"
            f"Debe crearse manualmente con permisos 600 (chmod 600), fuera del "
            f"control de versiones. Ver fog_cloning_secrets.ini.example en este "
            f"mismo directorio para el formato esperado."
        )
    parser = configparser.ConfigParser()
    parser.read(secrets_file)
    try:
        user = parser.get("mysql", "user")
        password = parser.get("mysql", "password")
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        raise ValueError(
            f"El fichero de credenciales de MySQL ({secrets_file}) no tiene el "
            f"formato esperado (sección [mysql] con claves 'user' y "
            f"'password'): {e}"
        )
    return user, password


MYSQL_USER, MYSQL_PASSWORD = _load_mysql_credentials(SECRETS_FILE)

# Parámetros de tareas
MIN_TASKS = 10
MAX_TASKS = 30

# Procesos a monitorizar
# Formato: "nombre_proceso,especificador"
MONITORED_PROCESSES = [
    ("mariadb", "mariadbd"),
    ("php-fpm", "php-fpm"),
    ("nfsd", "nfsd"),
    ("udp-sender", "udp-sender")
]
