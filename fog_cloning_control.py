import os
import sys
import signal
import time
import importlib

# Añadir los directorios lib y etc al path de Python
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'etc'))

# Importar los módulos antes de recargarlos
import fog_cloning_config
import fog_control_functions
# Importar clases
import DatabaseManager
from FOGModelInterpreter import FOGModelInterpreter

# Forzar la recarga de los módulos en caso de que se haya modificado
importlib.reload(fog_cloning_config)
importlib.reload(fog_control_functions)
importlib.reload(DatabaseManager)

from fog_control_functions import adjust_cloning_tasks
from fog_control_functions import initialize_files

# Importar todas las configuraciones
from fog_cloning_config import (
    SAMPLE_INTERVAL,
    HISTORY_FILE,
    HISTORY_10_MINUTES_FILE,
    LOG_FILE,
    MODEL_PATHS
)

def cleanup(signum, frame):
    with open(LOG_FILE, 'a') as log:
        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},Script terminado\n")
    exit(0)

def main():
    initialize_files(HISTORY_FILE, HISTORY_10_MINUTES_FILE, LOG_FILE)
    #interpreter = FOGModelInterpreter(MODEL_PATHS)
    interpreter = ''

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    while True:
        adjust_cloning_tasks(LOG_FILE, interpreter)
        #adjust_cloning_tasks(LOG_FILE)
        time.sleep(SAMPLE_INTERVAL)

if __name__ == "__main__":
    main()