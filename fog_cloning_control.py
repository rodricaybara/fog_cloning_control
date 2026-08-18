# fog_cloning_control.py
#
# Fase 1 (bugs críticos) - FOG Cloning Control
# Autores: Fernando Gietz + Claude Sonnet 5
#
# Cambios de esta fase respecto al original:
#   - [4.3] No había ningún try/except alrededor de adjust_cloning_tasks()
#     en el bucle principal. Combinado con los bugs de CPU_OVERLOADED y de
#     conexión a MySQL, cualquier excepción no prevista tumbaba el proceso
#     por completo. Ahora se captura cualquier excepción del ciclo, se
#     registra con su traza completa, y se continúa con el siguiente ciclo
#     en vez de morir. Como red de seguridad adicional (fuera de este
#     código), la unit de systemd debería tener Restart=always.
#   - [4.4] cleanup() no gestionaba errores al escribir el log de cierre
#     (p.ej. disco lleno), lo que podía impedir una salida limpia ante
#     SIGTERM/SIGINT. Ahora se envuelve en try/except.
#
# NOTA: MODEL_PATHS y el bloque importlib.reload son código muerto
# confirmado (el enfoque de modelo ML se descartó a favor del controlador
# PID). Se mantienen sin tocar en esta fase a propósito, para no mezclar la
# corrección de bugs con limpieza de código; su eliminación está prevista
# para la Fase 4.
#
# CORRECCIÓN URGENTE (17/08/2026, tras fallo en fog8): el import
# `from FOGModelInterpreter import FOGModelInterpreter` SÍ se retira ya,
# fuera del orden de fases previsto. Al arrancar en fog8 el proceso moría
# con "ModuleNotFoundError: No module named 'FOGModelInterpreter'"
# (crash-loop de systemd), porque este import de código muerto quedaba en
# el camino crítico de arranque dependiendo de un módulo (y, en cascada, de
# joblib/shap/scikit-learn) que no estaba disponible en el despliegue. Se
# retira solo este import puntual, sin tocar el resto del código muerto
# programado para la Fase 4, precisamente para no dejar el servicio caído
# mientras se resuelve.

import os
import sys
import signal
import time
import traceback
import importlib

# Añadir los directorios lib y etc al path de Python
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'etc'))

# Importar los módulos antes de recargarlos
import fog_cloning_config
import fog_control_functions
# Importar clases
import DatabaseManager

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
    # [4.4] Si LOG_FILE no fuera escribible en el momento de recibir la
    # señal (p.ej. disco lleno), esto lanzaba una excepción dentro del
    # propio manejador de señal, impidiendo una salida limpia. Se envuelve
    # en try/except para garantizar que el proceso siempre termina bien.
    try:
        with open(LOG_FILE, 'a') as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},Script terminado (señal {signum})\n")
    except Exception as e:
        print(f"Aviso: no se pudo escribir en LOG_FILE durante el cierre: {e}")
    finally:
        sys.exit(0)

def main():
    initialize_files(HISTORY_FILE, HISTORY_10_MINUTES_FILE, LOG_FILE)
    #interpreter = FOGModelInterpreter(MODEL_PATHS)
    interpreter = ''

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    while True:
        # [4.3] Ningún fallo puntual (BD, comando de sistema, fichero no
        # escribible, etc.) debe tumbar el daemon completo. Se captura,
        # registra y continúa con el siguiente ciclo.
        try:
            adjust_cloning_tasks(LOG_FILE, interpreter)
        except Exception as e:
            error_line = f"{time.strftime('%Y-%m-%d %H:%M:%S')},ERROR no controlado en adjust_cloning_tasks: {e}\n"
            try:
                with open(LOG_FILE, 'a') as log:
                    log.write(error_line)
                    log.write(traceback.format_exc() + "\n")
            except Exception:
                # Si ni siquiera se puede escribir el log, que quede
                # constancia al menos en stdout/journal.
                print(error_line, end="")
                traceback.print_exc()
        time.sleep(SAMPLE_INTERVAL)

if __name__ == "__main__":
    main()
