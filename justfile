# orchestra — recetas de desarrollo. Requiere `just` (https://github.com/casey/just).
# Si no tienes just, los comandos equivalentes están comentados bajo cada receta.

# Python del venv local (Windows/Git Bash). En Linux/mac: .venv/bin/python
py := ".venv/Scripts/python.exe"

# Lista las recetas disponibles
default:
    @just --list

# Corre los tests (día 1: solo stdlib + pytest, sin proxy ni keys)
test:
    {{py}} -m pytest

# Levanta el proxy litellm local (día 2+). Lee litellm.yaml.
# equivalente: .venv/Scripts/python.exe -m litellm --config litellm.yaml --port 4000
proxy:
    {{py}} -m litellm --config litellm.yaml --port 4000

# Ejecuta un rol concreto sobre una tarea (día 3+)
# uso: just run planner auth-jwt   |   just run builder auth-jwt
run role slug:
    {{py}} -m orchestra.cli run {{role}} --slug {{slug}}

# Ejecuta el ciclo completo planner -> builder -> tester (día 4+)
# uso: just cycle auth-jwt
cycle slug:
    {{py}} -m orchestra.cli cycle --slug {{slug}}

# Estado actual (fase/tarea activa)
status:
    {{py}} -m orchestra.cli status
