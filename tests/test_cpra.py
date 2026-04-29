import os
import sys

import pandas as pd
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import (
    InputData,
    app,
    calc_cpra,
    dataset_info,
    get_hla_columns,
    is_supported_antigen,
    load_data_from_db,
    load_supported_antigens,
    normalize_hla_columns,
    normalize_hla_value,
    reference_data,
)


load_data_from_db(app)


def test_pra_valido():
    response = calc_cpra(InputData(antigenos=["A2"]))

    assert "pra" in response
    assert response["mode_used"] == "FREQ"
    assert isinstance(response["pra"], float)


def test_pra_invalido():
    try:
        calc_cpra(InputData(antigenos=["BANANA"]))
        assert False, "Se esperaba HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400


def test_pra_entre_0_y_100():
    data = calc_cpra(InputData(antigenos=["A2"]))

    assert 0 <= data["pra"] <= 100


def test_agregar_antigeno_no_disminuye_pra():
    r1 = calc_cpra(InputData(antigenos=["A2"], mode="freq"))
    r2 = calc_cpra(InputData(antigenos=["A2", "B44"], mode="filter"))

    assert r2["pra"] >= r1["pra"]


def test_calc_cpra_rechaza_payload_vacio():
    with TestClient(app) as client:
        response = client.post("/calc_cpra", json={"antigenos": []})

    assert response.status_code == 400


def test_mode_invalido_rechazado():
    with TestClient(app) as client:
        response = client.post(
            "/calc_cpra",
            json={
                "antigenos": ["A2"],
                "mode": "banana",
            },
        )

    assert response.status_code == 422


def test_normalize_hla_value_maneja_numericos_y_normalizados():
    assert normalize_hla_value("02", "A") == ("A2", True)
    assert normalize_hla_value("A02", "A") == ("A2", True)
    assert normalize_hla_value("A2", "A") == ("A2", False)
    assert normalize_hla_value("044", "B") == ("B44", True)
    assert normalize_hla_value("DR1404", "DR") == ("DR1404", False)
    assert normalize_hla_value("-", "DQ") == ("-", False)
    assert normalize_hla_value("", "DQ") == ("", False)


def test_normalize_hla_columns_aplica_prefijos_por_columna():
    df = pd.DataFrame(
        {
            "A1": ["02", "A2", "-"],
            "A2": ["24", "", "A03"],
            "B1": ["044", "B44", "7"],
            "B2": ["8", "-", ""],
            "DRB1_1": ["4", "DR1404", "07"],
            "DRB1_2": ["15", "", "-"],
            "DQB1_1": ["7", "DQ2", ""],
            "DQB1_2": ["04", "-", "DQ7"],
        }
    )

    changed = normalize_hla_columns(df, ["A1", "A2", "B1", "B2", "DRB1_1", "DRB1_2", "DQB1_1", "DQB1_2"])

    assert changed > 0
    assert df.loc[0, "A1"] == "A2"
    assert df.loc[0, "B1"] == "B44"
    assert df.loc[2, "B1"] == "B7"
    assert df.loc[0, "DRB1_1"] == "DR4"
    assert df.loc[2, "DRB1_1"] == "DR7"
    assert df.loc[0, "DQB1_2"] == "DQ4"
    assert df.loc[2, "A1"] == "-"


def test_freq_y_filter_difieren_en_dataset_controlado():
    df_control = pd.DataFrame(
        {
            "A1": ["A2", "A2", "A1", "A1"],
            "A2": ["", "", "", ""],
            "B1": ["B44", "", "B44", ""],
            "B2": ["", "", "", ""],
            "DRB1_1": ["", "", "", ""],
            "DRB1_2": ["", "", "", ""],
            "DQB1_1": ["", "", "", ""],
            "DQB1_2": ["", "", "", ""],
        }
    )

    app.state.df = df_control
    app.state.hla_columns = ["A1", "A2", "B1", "B2", "DRB1_1", "DRB1_2", "DQB1_1", "DQB1_2"]
    app.state.supported_antigens = {"A1", "A2", "B44"}
    app.state.last_update = "2026-04-08 00:00:00"

    r_freq = calc_cpra(InputData(antigenos=["A2", "B44"], mode="freq"))
    r_filter = calc_cpra(InputData(antigenos=["A2", "B44"], mode="filter"))

    assert r_freq["pra"] != r_filter["pra"]
    assert r_freq["mode_used"] == "FREQ"
    assert r_filter["mode_used"] == "FILTER"

    load_data_from_db(app)


def test_health_endpoint_responde_ok():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["app"] == "PRA HLArg"
    assert "data_quality" in response.json()


def test_dataset_info_expone_metadata_hla():
    info = dataset_info()

    assert info["total_donors"] > 0
    assert "A1" in info["hla_columns"]
    assert info["observed_antigen_count"] > 0
    assert info["supported_antigen_count"] > 0
    assert info["calculation_scope"] == "HLA_ONLY"
    assert "data_quality" in info
    assert "normalized_hla_value_count" in info["data_quality"]
    assert "unsupported_observed_antigen_count" in info["data_quality"]


def test_reference_data_es_hla_only():
    data = reference_data()

    assert "A2" in data["observed_antigens"]
    assert "M" not in data["observed_antigens"]
    assert "-" not in data["observed_antigens"]
    assert "B76" in data["supported_antigens"]
    assert data["hla_columns"] == ["A1", "A2", "B1", "B2", "DRB1_1", "DRB1_2", "DQB1_1", "DQB1_2"]
    assert "hla_validation.csv" in data["validation_rule"]
    assert data["calculation_scope"] == "HLA_ONLY"
    assert "abo_groups" not in data
    assert sorted(data["modes"]) == ["filter", "freq"]
    assert "data_quality" in data
    assert "unsupported_observed_antigens" in data["data_quality"]


def test_get_hla_columns_devuelve_columnas_esperadas():
    columns = [
        "donor_id",
        "sexo",
        "edad",
        "fecha_operativo",
        "A1",
        "A2",
        "B1",
        "DQB1_1",
        "abo",
        "rh",
    ]

    assert get_hla_columns(columns) == ["A1", "A2", "B1", "DQB1_1"]


def test_antigeno_valido_aunque_no_aparezca_en_la_base():
    supported_antigens = load_supported_antigens()
    assert is_supported_antigen("B76", supported_antigens)
    response = calc_cpra(InputData(antigenos=["B76"]))
    assert "pra" in response


def test_antigeno_con_formato_invalido_se_rechaza():
    try:
        calc_cpra(InputData(antigenos=["BANANA"]))
        assert False, "Se esperaba HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
