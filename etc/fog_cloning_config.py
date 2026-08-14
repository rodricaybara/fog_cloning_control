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
MYSQL_USER = "mysql_user"
MYSQL_PASSWORD = "mysql_password"
MYSQL_DATABASE = "mysql_database"
MYSQL_HOST = "localhost"

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