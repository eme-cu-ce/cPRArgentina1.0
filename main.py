from datetime import datetime
from typing import Literal
import os
import sqlite3

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from init_demo_db import create_demo_db

APP_NAME = "PRA HLArg"
APP_DESCRIPTION = "Calculadora de PRA basada solo en incompatibilidades HLA."

DB_NAME = os.getenv("CPRA_DB", "cpra_demo.db")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, DB_NAME)
FRONTEND_PATH = os.path.join(BASE_DIR, "frontend", "index.html")
VALIDATION_TABLE_PATH = os.path.join(BASE_DIR, "data", "hla_validation.csv")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CPRA_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]
HLA_COLS = ["A1", "A2", "B1", "B2", "DRB1_1", "DRB1_2", "DQB1_1", "DQB1_2"]
VALID_MODES = {"freq", "filter"}
HLA_PREFIX_BY_COLUMN = {
    "A1": "A",
    "A2": "A",
    "B1": "B",
    "B2": "B",
    "DRB1_1": "DR",
    "DRB1_2": "DR",
    "DQB1_1": "DQ",
    "DQB1_2": "DQ",
}

DONORS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS donors (
    donor_id TEXT PRIMARY KEY,
    sexo TEXT,
    edad TEXT,
    fecha_operativo TEXT,
    A1 TEXT,
    A2 TEXT,
    B1 TEXT,
    B2 TEXT,
    DRB1_1 TEXT,
    DRB1_2 TEXT,
    DQB1_1 TEXT,
    DQB1_2 TEXT,
    abo TEXT,
    rh TEXT
);
"""


def get_hla_columns(columns: list[str]) -> list[str]:
    return [col for col in HLA_COLS if col in columns]


def load_supported_antigens(validation_table_path: str = VALIDATION_TABLE_PATH) -> set[str]:
    df_validation = pd.read_csv(validation_table_path, dtype=str).fillna("")
    if "antigen" not in df_validation.columns:
        raise ValueError("La tabla de validación HLA debe incluir la columna 'antigen'.")

    return {
        antigen.strip().upper()
        for antigen in df_validation["antigen"].tolist()
        if antigen.strip()
    }


def is_supported_antigen(antigen: str, supported_antigens: set[str]) -> bool:
    return antigen in supported_antigens


def normalize_hla_value(raw_value: str, prefix: str) -> tuple[str, bool]:
    value = (raw_value or "").strip().upper()
    if not value or value == "-":
        return value, False

    if value.startswith(prefix):
        suffix = value[len(prefix):]
        if suffix.isdigit():
            normalized = f"{prefix}{int(suffix)}"
            return normalized, normalized != value
        return value, False

    if value.isdigit():
        normalized = f"{prefix}{int(value)}"
        return normalized, True

    return value, False


def normalize_hla_columns(df_local: pd.DataFrame, columnas_hla: list[str]) -> int:
    normalized_count = 0

    for col in columnas_hla:
        prefix = HLA_PREFIX_BY_COLUMN.get(col)
        if not prefix:
            continue

        new_values: list[str] = []
        for value in df_local[col].tolist():
            normalized_value, changed = normalize_hla_value(value, prefix)
            new_values.append(normalized_value)
            if changed:
                normalized_count += 1

        df_local[col] = new_values

    return normalized_count


def calc_hla_filter_pra(df_local: pd.DataFrame, columnas_hla: list[str], antigenos: list[str]) -> float:
    mask_hla = df_local[columnas_hla].isin(antigenos).any(axis=1)
    return mask_hla.sum() / len(df_local)


def calc_hla_freq_pra(df_local: pd.DataFrame, columnas_hla: list[str], antigenos: list[str]) -> float:
    # Aproximación probabilística HLA-only:
    # combina probabilidades marginales por antígeno asumiendo independencia.
    probs = []
    for antigen in antigenos:
        has_antigen = df_local[columnas_hla].eq(antigen).any(axis=1)
        probs.append(has_antigen.sum() / len(df_local))

    no_hit_prob = 1.0
    for prob in probs:
        no_hit_prob *= (1 - prob)

    return 1 - no_hit_prob


def load_data_from_db(app: FastAPI):
    if DB_NAME == "cpra_demo.db" and not os.path.exists(DB_PATH):
        create_demo_db(DB_PATH)

    supported_antigens = load_supported_antigens()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(DONORS_TABLE_SQL)
        df_local = pd.read_sql_query("SELECT * FROM donors", conn)

    for col in df_local.columns:
        df_local[col] = df_local[col].fillna("").astype(str).str.strip().str.upper()

    columnas_hla = get_hla_columns(df_local.columns.tolist())
    normalized_hla_value_count = normalize_hla_columns(df_local, columnas_hla)
    antigens_observados = {
        antigen
        for antigen in df_local[columnas_hla].stack().dropna().unique()
        if antigen and antigen != "-"
    }
    unsupported_observed_antigens = sorted(antigens_observados - supported_antigens)

    app.state.df = df_local
    app.state.supported_antigens = supported_antigens
    app.state.observed_antigens = antigens_observados
    app.state.unsupported_observed_antigens = unsupported_observed_antigens
    app.state.hla_columns = columnas_hla
    app.state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    app.state.total_donors = len(df_local)
    app.state.db_path = DB_PATH
    app.state.normalized_hla_value_count = normalized_hla_value_count

    print("Base recargada. Donantes:", len(df_local))


app = FastAPI(title=APP_NAME, description=APP_DESCRIPTION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InputData(BaseModel):
    antigenos: list[str]
    mode: Literal["freq", "filter"] = "freq"


def ensure_data_loaded() -> None:
    if not hasattr(app.state, "df"):
        load_data_from_db(app)


@app.post("/calc_cpra")
def calc_cpra(data: InputData):
    ensure_data_loaded()
    df_local: pd.DataFrame = getattr(app.state, "df", pd.DataFrame())
    supported_antigens = getattr(app.state, "supported_antigens", set())
    columnas_hla = getattr(app.state, "hla_columns", [])

    if df_local.empty:
        return {"pra": 0.0}

    if not columnas_hla:
        raise HTTPException(
            status_code=500,
            detail="La base no contiene columnas HLA configuradas.",
        )

    antigenos = [a.strip().upper() for a in data.antigenos if a and a.strip()]
    mode = data.mode.lower().strip()

    if not antigenos:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar al menos un antígeno.",
        )

    invalid = [a for a in antigenos if not is_supported_antigen(a, supported_antigens)]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Antígenos inválidos: {invalid}")

    if mode == "filter":
        pra = calc_hla_filter_pra(df_local, columnas_hla, antigenos)
    else:
        pra = calc_hla_freq_pra(df_local, columnas_hla, antigenos)

    return {
        "pra": round(pra * 100, 1),
        "N_donors": len(df_local),
        "mode_used": mode.upper(),
        "scope": "HLA_ONLY",
        "last_update": app.state.last_update,
    }


@app.post("/reload_db")
def reload_db():
    load_data_from_db(app)
    return {"status": "Base recargada correctamente"}


@app.get("/health")
def health():
    ensure_data_loaded()
    unsupported_observed_antigens = getattr(app.state, "unsupported_observed_antigens", [])
    return {
        "status": "ok",
        "app": APP_NAME,
        "database": os.path.basename(getattr(app.state, "db_path", DB_PATH)),
        "total_donors": getattr(app.state, "total_donors", 0),
        "data_quality": {
            "normalized_hla_value_count": getattr(app.state, "normalized_hla_value_count", 0),
            "unsupported_observed_antigen_count": len(unsupported_observed_antigens),
            "has_warnings": bool(unsupported_observed_antigens),
        },
    }


@app.get("/dataset_info")
def dataset_info():
    ensure_data_loaded()
    unsupported_observed_antigens = getattr(app.state, "unsupported_observed_antigens", [])
    return {
        "app_name": APP_NAME,
        "total_donors": getattr(app.state, "total_donors", 0),
        "last_update": getattr(app.state, "last_update", "N/A"),
        "db_path": getattr(app.state, "db_path", DB_PATH),
        "hla_columns": getattr(app.state, "hla_columns", []),
        "observed_antigen_count": len(getattr(app.state, "observed_antigens", set())),
        "supported_antigen_count": len(getattr(app.state, "supported_antigens", set())),
        "calculation_scope": "HLA_ONLY",
        "data_quality": {
            "normalized_hla_value_count": getattr(app.state, "normalized_hla_value_count", 0),
            "unsupported_observed_antigen_count": len(unsupported_observed_antigens),
            "unsupported_observed_antigens": unsupported_observed_antigens,
        },
    }


@app.get("/reference_data")
def reference_data():
    ensure_data_loaded()
    observed_antigens = getattr(app.state, "observed_antigens", set())
    supported_antigens = getattr(app.state, "supported_antigens", set())
    unsupported_observed_antigens = getattr(app.state, "unsupported_observed_antigens", [])
    return {
        "hla_columns": getattr(app.state, "hla_columns", []),
        "observed_antigens": sorted(observed_antigens),
        "observed_antigen_count": len(observed_antigens),
        "supported_antigens": sorted(supported_antigens),
        "supported_antigen_count": len(supported_antigens),
        "modes": sorted(VALID_MODES),
        "validation_rule": "Validated against data/hla_validation.csv only",
        "calculation_scope": "HLA_ONLY",
        "data_quality": {
            "normalized_hla_value_count": getattr(app.state, "normalized_hla_value_count", 0),
            "unsupported_observed_antigen_count": len(unsupported_observed_antigens),
            "unsupported_observed_antigens": unsupported_observed_antigens,
        },
    }


@app.get("/", response_class=HTMLResponse)
def root_page():
    try:
        with open(FRONTEND_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(content="<h2>Frontend no encontrado</h2>", status_code=404)
