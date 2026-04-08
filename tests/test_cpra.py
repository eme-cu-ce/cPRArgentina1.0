import os
import sys

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


def test_health_endpoint_responde_ok():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["app"] == "PRA HLArg"


def test_dataset_info_expone_metadata_hla():
    info = dataset_info()

    assert info["total_donors"] > 0
    assert "A1" in info["hla_columns"]
    assert info["observed_antigen_count"] > 0
    assert info["supported_antigen_count"] > 0
    assert info["calculation_scope"] == "HLA_ONLY"


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
