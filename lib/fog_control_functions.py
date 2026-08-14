# fog_control_functions.py

import os
import sys
import time
import datetime
import subprocess
import mysql.connector
import psutil

# Añadir los directorios lib y etc al path de Python

sys.path.append(os.path.join(os.path.dirname(__file__), 'etc'))

# Importar todas las configuraciones
from fog_cloning_config import (
    CPU_LIMIT,
    CPU_THRESHOLD,
    CPU_OVERLOADED,
    NETWORK_LIMIT,
    HISTORY_DURATION,
    DEVICE_NAME,

    HISTORY_FILE,
    HISTORY_10_MINUTES_FILE,
    LOG_FILE,

    # Parámetros del controlador PID
    Kp,
    Ki,
    Kd,
    integral_cpu,
    integral_network,
    last_cpu_error,
    last_network_error,

    # Configuración de MySQL
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
    MYSQL_HOST,

    # Parámetros de tareas
    MIN_TASKS,
    MAX_TASKS,
    MONITORED_PROCESSES
)

# Importar la clase DatabaseManager
from DatabaseManager import DatabaseManager

# Crear una instancia de DatabaseManager
db_manager = DatabaseManager(MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE)

def initialize_files(HISTORY_FILE, HISTORY_10_MINUTES_FILE, LOG_FILE):
    files = {
        HISTORY_FILE: "timestamp;cpu_usage;network_usage;active_tasks;unicast_download_active;unicast_upload_active;queued_tasks;unicast_download_queued;unicast_upload_queued;active_multicast;queued_multicast;task_limit;busy_percent;read_kib;write_kib;mb_read_per_sec;mb_write_per_sec;mariadb_cpu;php-fpm_cpu;nfsd_cpu;udp-sender_cpu;total_resources_cpu;unicast_files_download;multicast_files_download",
        HISTORY_10_MINUTES_FILE: "timestamp;cpu_usage;network_usage;active_tasks;unicast_download_active;unicast_upload_active;queued_tasks;unicast_download_queued;unicast_upload_queued;active_multicast;queued_multicast;task_limit;busy_percent;read_kib;write_kib;mb_read_per_sec;mb_write_per_sec;mariadb_cpu;php-fpm_cpu;nfsd_cpu;udp-sender_cpu;total_resources_cpu;unicast_files_download;multicast_files_download",
        LOG_FILE: "Fichero de log para FOG Cloning Control"
    }
    
    for file, header in files.items():
        if not os.path.exists(file):
            with open(file, 'w') as f:
                f.write(f"{header}\n")

def bytes_to_kib(bytes_value):
    return bytes_value / 1024

def kib_to_mb(kib_value):
    return kib_value / 1024

def get_io_stats(device, LOG_FILE):
    try:
        with open('/proc/diskstats', 'r') as f:
            for line in f:
                if device in line:
                    stats = line.split()
                    return [int(stats[5]), int(stats[9]), int(stats[6]), int(stats[10]), int(stats[12])]
    except Exception as e:
        with open(LOG_FILE, 'a') as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},Error: No se pudo leer las estadísticas de E/S para {device}: {str(e)}\n")
    return None

def get_dm_device(device_name, LOG_FILE):
    try:
        result = subprocess.run(['ls', '-l', '/dev/mapper'], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if device_name in line:
                return line.split()[-1].replace('../', '')
    except subprocess.CalledProcessError as e:
        with open(LOG_FILE, 'a') as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},Error: Fallo al buscar el dispositivo dm: {str(e)}\n")
    return None

def monitor_lvm_io(DEVICE_NAME, LOG_FILE):
    lvm_device = get_dm_device(DEVICE_NAME,LOG_FILE)
    if not lvm_device:
        with open(LOG_FILE, 'a') as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},Error: No se pudo encontrar el dispositivo dm para el LVM {DEVICE_NAME}\n")
        return 0, 0, 0, 0, 0  # Retornar valores por defecto

    initial_stats = get_io_stats(lvm_device, LOG_FILE)
    if not initial_stats:
        return 0, 0, 0, 0, 0  # Retornar valores por defecto

    initial_time = time.time_ns()
    time.sleep(5)
    final_stats = get_io_stats(lvm_device, LOG_FILE)
    if not final_stats:
        return 0, 0, 0, 0, 0  # Retornar valores por defecto
    final_time = time.time_ns()

    # Calcular diferencias y métricas
    read_sectors = final_stats[0] - initial_stats[0]
    write_sectors = final_stats[1] - initial_stats[1]
    read_time = final_stats[2] - initial_stats[2]
    write_time = final_stats[3] - initial_stats[3]
    io_time = final_stats[4] - initial_stats[4]

    elapsed_time = (final_time - initial_time) / 1e9
    if elapsed_time == 0:
        with open(LOG_FILE, 'a') as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},Error: El tiempo transcurrido es cero. No se puede calcular la tasa\n")
        return 0, 0, 0, 0, 0  # Retornar valores por defecto

    busy_percent = round(100 * io_time / (elapsed_time * 1000), 2)
    read_kib = round(bytes_to_kib(read_sectors * 512), 2)
    write_kib = round(bytes_to_kib(write_sectors * 512), 2)
    kib_per_read = round(read_kib / (read_sectors / 2), 2) if read_sectors > 0 else 0
    kib_per_write = round(write_kib / (write_sectors / 2), 2) if write_sectors > 0 else 0
    mb_read_per_sec = round(kib_to_mb(read_kib / elapsed_time), 2)
    mb_write_per_sec = round(kib_to_mb(write_kib / elapsed_time), 2)
    avio_ms = round((read_time + write_time) / (read_sectors + write_sectors), 2) if (read_sectors + write_sectors) > 0 else 0

    log_message = f"LVM | {DEVICE_NAME} | busy {busy_percent:.2f}% | read {read_sectors} | write {write_sectors} | discrd 0 | KiB/r {kib_per_read:.2f} | KiB/w {kib_per_write:.2f} | KiB/d 0 | MBr/s {mb_read_per_sec:.2f} | MBw/s {mb_write_per_sec:.2f} | avio {avio_ms:.2f} ms"
    
    with open(LOG_FILE, 'a') as log:
        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}: {log_message}\n")

    return busy_percent, read_kib, write_kib, mb_read_per_sec, mb_write_per_sec


def monitor_specific_processes(MONITORED_PROCESSES):
    total_cpu = 0
    process_cpu_usage = []

    for process_name, process_identifier in MONITORED_PROCESSES:
        cpu_usage = 0
        for proc in psutil.process_iter(['name', 'cpu_percent']):
            if proc.info['name'] == process_identifier:
                cpu_usage += proc.info['cpu_percent']
        
        total_cpu += cpu_usage
        process_cpu_usage.append(f"{cpu_usage:.2f}")

    return ';'.join(process_cpu_usage), round(total_cpu, 2)

def calculate_network_usage():
    net_io = psutil.net_io_counters()
    start_bytes = net_io.bytes_sent + net_io.bytes_recv
    time.sleep(1)
    net_io = psutil.net_io_counters()
    end_bytes = net_io.bytes_sent + net_io.bytes_recv
    return (end_bytes - start_bytes) * 8

def get_task_status():
    queries = {
        "current_unicast_download_active": "SELECT COUNT(taskID) FROM tasks WHERE taskTypeID IN (1,15,17) AND taskStateID=3",
        "current_unicast_upload_active": "SELECT COUNT(taskID) FROM tasks WHERE taskTypeID IN (2,16) AND taskStateID=3",
        "current_unicast_download_queued": "SELECT COUNT(taskID) FROM tasks WHERE taskTypeID IN (1,15,17) AND taskStateID=1",
        "current_unicast_upload_queued": "SELECT COUNT(taskID) FROM tasks WHERE taskTypeID IN (2,16) AND taskStateID=1",
        "current_multicast_active": "SELECT COUNT(msID) FROM multicastSessions WHERE msState=3",
        "current_multicast_queued": "SELECT COUNT(msID) FROM multicastSessions WHERE msState=1",
        "current_task_limit": "SELECT ngmMaxClients FROM nfsGroupMembers WHERE ngmID=1",
        "unicast_files_download": "select count(distinct taskImageID) from tasks where taskStateID in (2,3) and taskTypeID in (1, 15)",
        "multicast_files_download": "select count(distinct msImage) from multicastSessions where msState = 3"
    }

    results = {}
    for key, query in queries.items():
        result = db_manager.execute_query(query)
        if result:
            results[key] = result[0][0]
        else:
            results[key] = 0

    current_unicast_active = results["current_unicast_download_active"] + results["current_unicast_upload_active"]
    current_unicast_queued = results["current_unicast_download_queued"] + results["current_unicast_upload_queued"]

    return (
        current_unicast_active,
        results["current_unicast_download_active"],
        results["current_unicast_upload_active"],
        current_unicast_queued,
        results["current_unicast_download_queued"],
        results["current_unicast_upload_queued"],
        results["current_multicast_active"],
        results["current_multicast_queued"],
        results["current_task_limit"],
        results["unicast_files_download"],
        results["multicast_files_download"]
    )

def manage_tasks(action, task_limit, current_task_limit, current_tasks, MIN_TASKS, MAX_TASKS, LOG_FILE):
    with open(LOG_FILE, 'a') as log:
        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},Acción: {action}, Límite de tarea: {task_limit}\n")

    if action == "increase":
        if current_task_limit < MAX_TASKS:
            new_task_limit = min(current_task_limit + 2, MAX_TASKS)
        else:
            new_task_limit = MAX_TASKS
    elif action == "decrease":
        new_task_limit = max(current_task_limit - 2, MIN_TASKS)
    else:
        with open(LOG_FILE, 'a') as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},Acción inválida: {action}\n")
        return False

    if current_task_limit != new_task_limit:
        query = "UPDATE nfsGroupMembers SET ngmMaxClients=%s WHERE ngmID=1"
        success = db_manager.execute_update(query, (new_task_limit,))
        if success:
            with open(LOG_FILE, 'a') as log:
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},Límite de tareas actualizado a: {new_task_limit}\n")
            return True
        else:
            with open(LOG_FILE, 'a') as log:
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},Error al actualizar el límite de tareas en la base de datos MySQL\n")
            return False
    return True

def adjust_cloning_tasks(LOG_FILE, interpreter):
    # Función para obtener el uso de CPU
    def get_cpu_usage():
        cmd = "awk '{u=$2+$4; t=$2+$4+$5; if (NR==1){u1=u; t1=t;} else print ($2+$4-u1) * 100 / (t-t1); }' <(grep 'cpu ' /proc/stat) <(sleep 1; grep 'cpu ' /proc/stat)"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return int(float(result.stdout.strip().split('.')[0]))

    CPU_USAGE = get_cpu_usage()
    NETWORK_USAGE = calculate_network_usage()

    # Obtener el estado actual de las tareas
    task_status = get_task_status()
    current_tasks_active_unicast, current_unicast_download_active, current_unicast_upload_active, \
    current_tasks_queued_unicast, current_unicast_download_queued, current_unicast_upload_queued, \
    current_tasks_active_Multicast, current_tasks_queued_Multicast, current_task_limit, \
    unicast_files_download, multicast_files_download = task_status

    current_tasks = (current_tasks_active_unicast + current_tasks_active_Multicast + 
                     current_tasks_queued_unicast + current_tasks_queued_Multicast)
    current_tasks_queued = current_tasks_queued_unicast + current_tasks_queued_Multicast

    # Obtener uso de CPU de procesos específicos
    process_cpu_usage, total_monitored_cpu = monitor_specific_processes(MONITORED_PROCESSES)

    # Obtener información de I/O del disco o cualquier otra fuente
    result = monitor_lvm_io(DEVICE_NAME, LOG_FILE)
    if result is None:
        busy_percent, read_kib, write_kib, mb_read_per_sec, mb_write_per_sec = (0, 0, 0, 0, 0)  # Valores por defecto
    else:
        busy_percent, read_kib, write_kib, mb_read_per_sec, mb_write_per_sec = result



    # Guardar resultados en el archivo de todos los registros
    with open(HISTORY_FILE, 'a') as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')};{CPU_USAGE};{NETWORK_USAGE};"
                f"{current_tasks};{current_unicast_download_active};{current_unicast_upload_active};"
                f"{current_tasks_queued};{current_unicast_download_queued};{current_unicast_upload_queued};"
                f"{current_tasks_active_Multicast};{current_tasks_queued_Multicast};{current_task_limit};"
                f"{busy_percent};{read_kib};{write_kib};{mb_read_per_sec};{mb_write_per_sec};"
                f"{process_cpu_usage};{total_monitored_cpu};{unicast_files_download};{multicast_files_download}\n")

    # Guardar resultados en el archivo de los últimos 10 minutos
    with open(HISTORY_10_MINUTES_FILE, 'a') as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')};{CPU_USAGE};{NETWORK_USAGE};"
                f"{current_tasks};{current_unicast_download_active};{current_unicast_upload_active};"
                f"{current_tasks_queued};{current_unicast_download_queued};{current_unicast_upload_queued};"
                f"{current_tasks_active_Multicast};{current_tasks_queued_Multicast};{current_task_limit};"
                f"{busy_percent};{read_kib};{write_kib};{mb_read_per_sec};{mb_write_per_sec}\n")

    # Filtrar registros de los últimos 10 minutos
    ten_minutes_ago = datetime.datetime.now() - datetime.timedelta(seconds=HISTORY_DURATION)

    # Comprobar si el archivo existe y no está vacío
    if os.path.exists(HISTORY_10_MINUTES_FILE) and os.path.getsize(HISTORY_10_MINUTES_FILE) > 0:
        with open(HISTORY_10_MINUTES_FILE, 'r') as f:
            lines = f.readlines()

        with open(HISTORY_10_MINUTES_FILE, 'w') as f:
            for line in lines:
                date_str = line.split(';')[0]
                try:
                    if datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S') > ten_minutes_ago:
                        f.write(line)
                except ValueError:
                    with open(LOG_FILE, 'a') as log:
                        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},Advertencia: la línea no contiene una fecha válida: {line.strip()}\n")
    else:
        with open(LOG_FILE, 'a') as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},Advertencia: El archivo está vacío o no existe, no se realizarán filtros\n")


    # Calcular la media de los últimos 10 minutos
    with open(HISTORY_10_MINUTES_FILE, 'r') as f:
        lines = f.readlines()

    # Asegúrate de que las líneas no estén vacías para evitar división por cero
    if len(lines) > 1:  # Verificamos que hay más de una línea (cabecera + datos)
        # Ignorar la cabecera
        data_lines = lines[1:]

        avg_cpu_usage = sum(float(line.split(';')[1]) for line in data_lines) / len(data_lines)
        avg_network_usage = sum(float(line.split(';')[2]) for line in data_lines) / len(data_lines)
    else:
        avg_cpu_usage = 0
        avg_network_usage = 0

    error_cpu = avg_cpu_usage - CPU_LIMIT
    error_network = avg_network_usage - NETWORK_LIMIT

    global integral_cpu, integral_network, last_cpu_error, last_network_error

    integral_cpu += error_cpu
    integral_network += error_network

    derivative_cpu = error_cpu - last_cpu_error
    derivative_network = error_network - last_network_error

    control_cpu = Kp * error_cpu + Ki * integral_cpu + Kd * derivative_cpu
    control_network = Kp * error_network + Ki * integral_network + Kd * derivative_network

    current_state = ""
    task_type = ""
    #prediction = interpreter.get_prediction(current_state, task_type)

    # Verificar si el uso de CPU es mayor o igual a CPU_LIMIT
    if CPU_USAGE >= CPU_LIMIT:
        CPU_OVERLOADED = 1
        with open(LOG_FILE, 'a') as f:
            f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, Mantener tareas actuales. Uso de CPU por encima del {CPU_LIMIT}%\n")
    elif CPU_USAGE <= CPU_THRESHOLD:
        CPU_OVERLOADED = 0
        with open(LOG_FILE, 'a') as f:
            f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, Reducir tareas. Uso de CPU por debajo del {CPU_THRESHOLD}%\n")

    # Incrementar o decrementar según el estado
    if CPU_OVERLOADED == 0:
        task_difference = current_task_limit - current_tasks

        if control_cpu < 0:
            if task_difference < 2:
                action = "Aumentar"
                reason = f"Recursos disponibles (CPU: {CPU_USAGE}%, Red: {NETWORK_USAGE} bps)"
                manage_tasks("increase", 1, current_task_limit, current_tasks, MIN_TASKS, MAX_TASKS, LOG_FILE)
            elif task_difference > 2:
                if current_task_limit <= MIN_TASKS:
                    action = "Mantener"
                    reason = f"El límite de tareas es el mínimo permitido ({MIN_TASKS}), no se pueden reducir más tareas"
                else:
                    action = "Reducir"
                    reason = f"Diferencia de tareas mayor a 2 ({task_difference})"
                    manage_tasks("decrease", 1, current_task_limit, current_tasks, MIN_TASKS, MAX_TASKS, LOG_FILE)
            else:
                action = "Mantener"
                reason = f"Diferencia de tareas es 2 ({task_difference})"
        else:
            action = "Reducir"
            reason = f"Uso de CPU alto ({CPU_USAGE}%)"
            manage_tasks("decrease", 1, current_task_limit, current_tasks, MIN_TASKS, MAX_TASKS, LOG_FILE)
    else:
        action = "Mantener"
        reason = "El sistema está sobrecargado"

    with open(LOG_FILE, 'a') as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{action},{reason},{CPU_USAGE},{NETWORK_USAGE},"
                f"{current_tasks},{current_tasks_queued},{current_tasks_active_Multicast},"
                f"{current_tasks_queued_Multicast},{current_task_limit}\n")

    last_cpu_error = error_cpu
    last_network_error = error_network
