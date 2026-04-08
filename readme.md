# PRA HLArg

Calculadora de PRA basada solo en incompatibilidades HLA, usando base de donantes argentina.

Alias interno: CalcuPRAdora HLArgentina.

Esta aplicación es una herramienta hermana de `cPRArgentina` para comparación metodológica. A diferencia de la app principal, aquí no se usa ABO en ningún punto del flujo.

## Alcance actual

- FastAPI + frontend HTML integrado
- Cálculo HLA-only (sin ajuste ni filtrado ABO)
- Modos disponibles: `freq` y `filter` (sin lógica ABO)
- Validación de antígenos contra `data/hla_validation.csv`
- Base SQLite real o demo
- Endpoints de salud, metadata y referencia

## Diferencias clave con cPRArgentina

- No hay campo ABO en el input
- No hay salida asociada a ajuste ABO
- Resultado único: porcentaje PRA por incompatibilidad HLA

## Endpoints

- `GET /` sirve la interfaz
- `POST /calc_cpra` calcula PRA HLA-only
- `GET /dataset_info` devuelve metadata de la base
- `GET /reference_data` devuelve antígenos observados/soportados
- `GET /health` devuelve estado del servicio
- `POST /reload_db` recarga la base en memoria

## Ejecución local

1. Instalar dependencias:

```bash
pip install -r requirements.txt
```

2. Levantar la app:

```bash
uvicorn main:app --reload
```

3. Abrir:

```text
http://127.0.0.1:8000
```

## Selección de base

Por defecto, la app usa `cpra_demo.db`.

Para usar la base real:

En Windows `cmd`:

```cmd
set CPRA_DB=cpra.db
uvicorn main:app --reload
```

En Windows PowerShell:

```powershell
$env:CPRA_DB="cpra.db"
uvicorn main:app --reload
```

## Variables de entorno

- `CPRA_DB`: nombre/ruta del archivo SQLite
- `CPRA_CORS_ORIGINS`: orígenes permitidos separados por coma (default `*`)

## Dataset demo

Puede recrearse con:

```bash
python init_demo_db.py
```

Si `cpra_demo.db` no existe al iniciar, se recrea automáticamente.

## Carga de donantes

Usar `load_donors.py` para cargar CSV a `cpra.db`.

El importador acepta CSV sin columnas `abo` y `rh` (se completan en blanco).

Incremental:

```bash
python load_donors.py --csv "C:\path\to\donors.csv" --mode append
```

Reconstrucción completa:

```bash
python load_donors.py --csv "C:\path\to\donors.csv" --mode rebuild
```

## Fuente de validación

Catálogo oficial HLA en:

- `data/hla_validation.csv`

La validación es independiente de la presencia en la base de donantes.

## Nota de uso

Research Use Only.

Herramienta orientada a comparación metodológica, investigación y validación. No reemplaza decisión clínica independiente.
