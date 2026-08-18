# FOG Cloning Control — Fase 1: correcciones críticas

**Fecha**: 17/08/2026
**Autores**: Fernando Gietz + Claude Sonnet 5
**Alcance**: los 10 puntos de la tabla "Fase 1" de `fog_cloning_control_propuesta.md`. No incluye cambios de comportamiento del control (Fase 3), ni el nuevo esquema de histórico (Fase 2), ni limpieza de código muerto (Fase 4) — se mantienen deliberadamente fuera de esta entrega.

---

## Ficheros modificados

| Fichero | Cambios |
|---|---|
| `lib/DatabaseManager.py` | Bug #2 (RuntimeError ante fallo de conexión MySQL) |
| `etc/fog_cloning_config.py` | Bug #8 (credenciales en texto plano) |
| `etc/fog_cloning_secrets.ini.example` | Nuevo — plantilla del fichero de secretos |
| `lib/fog_control_functions.py` | Bugs #1, #3, #5, #7, #9 |
| `fog_cloning_control.py` | Bugs #4, #10 |
| `lib/FOGModelInterpreter.py` | Sin cambios (copiado tal cual, pendiente de eliminación en Fase 4) |

---

## Detalle por bug

### #1 — `UnboundLocalError` en la franja de CPU 70–90% (`fog_control_functions.py`)

Faltaba `CPU_OVERLOADED` en la declaración `global` de `adjust_cloning_tasks`. Se añade junto al resto de estado del controlador. Efecto: en el rango `CPU_THRESHOLD < CPU_USAGE < CPU_LIMIT` (donde ninguna de las dos ramas reasigna la variable), ahora se conserva el último estado conocido de un ciclo a otro, en vez de quedar sin definir — es decir, histéresis, no un bug.

Validado con una prueba de humo forzando la secuencia de CPU `95 → 80 → 80 → 80 → 60 → 80 → 80`: el estado se mantiene "sobrecargado" durante los `80` que siguen al `95`, y pasa a "no sobrecargado" tras el `60`, manteniéndose así en los `80` posteriores — sin excepción en ningún ciclo.

### #2 — `RuntimeError` ante fallo de conexión MySQL (`DatabaseManager.py`)

`get_connection()` ahora relanza (`raise`) la excepción `Error` tras loguearla, en vez de dejar que el generador termine sin `yield`. `execute_query()`/`execute_update()` envuelven también la apertura de la conexión en su propio `try/except`, devolviendo `None`/`False` de forma controlada ante cualquier fallo de conexión — igual que ya hacían ante un fallo de la propia consulta.

### #3 — Fallos de lectura de BD tratados como `0` (`fog_control_functions.py`)

`get_task_status()` distingue ahora un fallo real (`result is None`, o lista vacía) de una respuesta válida, devolviendo `None` explícito en ese caso. `adjust_cloning_tasks()` comprueba al principio si algún valor del estado de tareas es `None` y, si es así, **aborta el ciclo completo**: no escribe fila en el histórico ni llama a `manage_tasks()`, evitando que un fallo transitorio de lectura pueda sobrescribir `nfsGroupMembers.ngmMaxClients` con un valor erróneo. Se deja constancia clara en `LOG_FILE`.

Un `COUNT(...) = 0` real (consulta que sí responde, con resultado cero) se sigue tratando como `0`, no se confunde con el fallo — validado con prueba de humo.

### #4 — Sin manejo de excepciones en el bucle principal (`fog_cloning_control.py`)

El `while True` envuelve ahora la llamada a `adjust_cloning_tasks()` en `try/except Exception`, registrando el error y la traza completa en `LOG_FILE` (o en `stdout`/journal si ni siquiera se puede escribir el log) y continuando con el siguiente ciclo. **Recomendación operativa** (fuera de este código): confirmar que la unit de systemd tiene `Restart=always` como red de seguridad adicional.

### #5 — `get_cpu_usage` frágil (`fog_control_functions.py`)

Se sustituye el comando de shell (`awk` + sustitución de procesos `<(...)`, dependiente de que `/bin/sh` sea compatible) por `psutil.cpu_percent(interval=1)`, nativo y sin dependencia de shell externo. Mismo comportamiento de muestreo (bloquea 1s), sin el riesgo de `ValueError` no controlado ante un `stdout` vacío.

### #7 — Métricas de I/O rotas: `kib_per_read`, `kib_per_write`, `avio_ms` (`fog_control_functions.py`)

`get_io_stats()` ahora también captura el número de operaciones de lectura/escritura completadas desde `/proc/diskstats` (antes no se leían). Con eso, `monitor_lvm_io()` calcula `kib_per_read`/`kib_per_write` dividiendo por el número real de operaciones (antes daba ~1.00 constante, ver análisis 1.4) y `avio_ms` dividiendo el tiempo acumulado entre operaciones completadas, no entre sectores (antes subestimaba el tiempo medio de E/S, ver análisis 1.5) — ahora es comparable al `await` de `iostat`.

Este cambio solo afecta al mensaje interno que `monitor_lvm_io()` escribe en `LOG_FILE`; no toca el esquema del CSV de histórico (eso es Fase 2).

### #8 — Credenciales en texto plano (`fog_cloning_config.py`)

`MYSQL_USER`/`MYSQL_PASSWORD` ya no están hardcodeados. Se cargan desde un fichero externo (`etc/fog_cloning_secrets.ini`, no incluido en esta entrega — ver más abajo) mediante `configparser`. Si el fichero no existe o está mal formado, el servicio falla de forma clara al arrancar (fail-loud) en vez de arrancar con credenciales incorrectas.

Se entrega `etc/fog_cloning_secrets.ini.example` como plantilla segura de versionar.

### #9 — `manage_tasks` con parámetro `task_limit` engañoso (`fog_control_functions.py`)

Se elimina el parámetro `task_limit` (siempre valía `1`, solo se usaba para un log que decía "Límite de tarea: 1" cuando el paso real era `±2`). Se introduce la constante `TASK_STEP = 2` y el log ahora muestra el paso real aplicado y el límite propuesto resultante.

### #10 — `cleanup()` sin manejo de errores (`fog_cloning_control.py`)

Se envuelve la escritura del log de cierre en `try/except`, garantizando una salida limpia (`sys.exit(0)`) aunque `LOG_FILE` no sea escribible en ese momento (p. ej. disco lleno).

---

## Validación realizada hasta ahora (entorno de desarrollo de Claude, no fog8)

Antes de entregar, se han ejecutado pruebas de humo con MySQL simulado (sin conexión real) para verificar la lógica:

1. Carga de credenciales desde el fichero de secretos (éxito y fallo por ausencia de fichero).
2. `get_task_status()` devuelve `None` explícito ante un fallo simulado de consulta, y `0` real ante un `COUNT` que sí responde con cero.
3. `adjust_cloning_tasks()` aborta el ciclo sin excepción y sin escribir histórico cuando el estado de tareas viene con `None`.
4. Secuencia de CPU que fuerza la franja 70–90% durante varios ciclos consecutivos, sin `UnboundLocalError`, con histéresis correcta.
5. `manage_tasks()` con la nueva firma, log resultante coherente.

**Esto no sustituye la validación pendiente en fog8 con sesiones de clonación reales**, que sigue siendo necesaria antes de fog9, en particular para:

- Confirmar que `psutil.cpu_percent(interval=1)` da lecturas coherentes con el `get_cpu_usage` anterior en el hardware real (RHEL 9, VMware).
- Provocar una caída puntual real de MariaDB durante un ciclo activo y comprobar en `LOG_FILE` que el servicio sobrevive y retoma el control al siguiente ciclo.
- Comprobar el mensaje `LVM | ...` en `LOG_FILE` con tráfico real de E/S, y contrastar `avio_ms`/`KiB/r`/`KiB/w` frente a `iostat -x` en el propio fog8 para validar que las nuevas fórmulas son coherentes.
- Crear el `fog_cloning_secrets.ini` real (a partir de la plantilla) con permisos 600 y confirmar que el servicio arranca correctamente con él.

---

## Pasos de despliegue en fog8

1. Copiar los ficheros de este paquete respetando la estructura de directorios (`fog_cloning_control.py` en la raíz, `etc/`, `lib/`).
2. Crear `etc/fog_cloning_secrets.ini` a partir de `etc/fog_cloning_secrets.ini.example`, con las credenciales reales, y aplicar:
   ```
   chown <usuario_servicio>:<usuario_servicio> etc/fog_cloning_secrets.ini
   chmod 600 etc/fog_cloning_secrets.ini
   ```
3. Confirmar que `etc/fog_cloning_secrets.ini` queda excluido del control de versiones.
4. Arrancar el servicio y comprobar en `LOG_FILE` que arranca sin errores.
5. Ejecutar la batería de pruebas descrita arriba con sesiones de clonación reales (unicast y multicast).

---

*(Fase 1 implementada y probada con MySQL simulado. Pendiente de validación con sesiones reales en fog8 antes de pasar a fog9 o a la Fase 2.)*

---

## Addendum — Hotfix urgente (17/08/2026, tras primer despliegue en fog8)

Al reiniciar el servicio en fog8 con esta entrega, arrancó en crash-loop:

```
ModuleNotFoundError: No module named 'FOGModelInterpreter'
```

**Causa**: `fog_cloning_control.py` seguía importando `FOGModelInterpreter` (código muerto, programado para retirarse en la Fase 4) en el camino crítico de arranque. Ese módulo depende en cascada de `joblib`/`shap`/`scikit-learn`, y ni el propio fichero ni esas dependencias estaban disponibles en el despliegue de fog8 — dejando el import fuera de esta fase resultó, en la práctica, en la misma clase de fragilidad que la Fase 1 pretendía eliminar.

**Fix aplicado** (solo en `fog_cloning_control.py`, un único cambio, fuera del orden de fases previsto por necesidad operativa):
- Se elimina la línea `from FOGModelInterpreter import FOGModelInterpreter`.
- No se toca nada más de ese fichero (ni `MODEL_PATHS`, ni el bloque `importlib.reload`, ni el resto de código muerto) — se mantienen tal cual, programados para la Fase 4.

**Validado** (esta vez con ejecución real del proceso, no con mocks):
- Arranque sin `lib/FOGModelInterpreter.py` presente → sin `ModuleNotFoundError`.
- El proceso entra en el bucle principal, crea correctamente `fog_cloning_history.csv`, `fog_cloning_history_10min.csv` y `fog_cloning_control.log`.
- Con MySQL inalcanzable (sin servidor en el entorno de prueba), el proceso registra el error de conexión en bucle y **sigue vivo** — confirma también, en ejecución real, la corrección del bug #2 (antes esto mataba el proceso con `RuntimeError`).

**Pendiente de confirmar en fog8**: si `lib/FOGModelInterpreter.py` existe o no en `/opt/fog_cloning_control/lib/` — no bloquea el arranque de todas formas ahora que no se importa, pero conviene saberlo para entender qué pasó exactamente en el despliegue.

*(Confirmado: no existía. Coherente con que `interpreter` lleva deshabilitado tiempo (`interpreter = ''`).)*

---

## Resultados de validación real en fog8

### Bloque A — Caída puntual de MySQL (bugs #2, #3, #4) — ✅ PASA (17/08/2026)

Al parar MariaDB con el servicio en marcha:
- El PID de `fog-cloning-control` no cambia (sin `RuntimeError`, sin reinicio de systemd).
- No se escriben filas nuevas en `fog_cloning_history.csv` durante la caída (sin datos falsos/incompletos contaminando el histórico).
- Al restablecerse MySQL, el servicio retoma solo en el siguiente ciclo, sin intervención manual.

Bugs #2 (`RuntimeError` no controlado), #3 (lecturas fallidas tratadas como 0) y #4 (sin manejo de excepciones en el bucle principal) validados conjuntamente con una caída real, no simulada.

**Pendiente**: Bloque B (CPU 70-90% sostenida), Bloque C (métricas de I/O vs. `iostat`), Bloque D (`get_cpu_usage` vs. `top`/`sar`), Bloque E (secretos ausentes) y Bloque F (log no escribible) — ver `fog_cloning_control_fase1_plan_pruebas.md`.
