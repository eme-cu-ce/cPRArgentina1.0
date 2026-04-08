import json
from http import HTTPStatus
import os
from typing import Any

from fastapi import HTTPException

from main import InputData, app, calc_cpra, dataset_info, health, load_data_from_db, reference_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_PATH = os.path.join(BASE_DIR, "frontend", "index.html")


def _json_response(start_response, status_code: int, payload: dict[str, Any]):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    status_text = f"{status_code} {HTTPStatus(status_code).phrase}"
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ]
    start_response(status_text, headers)
    return [body]


def _text_response(start_response, status_code: int, body_text: str, content_type: str = "text/plain; charset=utf-8"):
    body = body_text.encode("utf-8")
    status_text = f"{status_code} {HTTPStatus(status_code).phrase}"
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
    ]
    start_response(status_text, headers)
    return [body]


def _read_json_body(environ) -> dict[str, Any]:
    try:
        length = int(environ.get("CONTENT_LENGTH", "0") or "0")
    except ValueError:
        length = 0

    if length <= 0:
        return {}

    raw = environ["wsgi.input"].read(length)
    if not raw:
        return {}

    return json.loads(raw.decode("utf-8"))


def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/")

    try:
        if path == "/":
            with open(FRONTEND_PATH, "r", encoding="utf-8") as f:
                return _text_response(start_response, 200, f.read(), "text/html; charset=utf-8")

        if method == "GET" and path == "/health":
            return _json_response(start_response, 200, health())

        if method == "GET" and path == "/dataset_info":
            return _json_response(start_response, 200, dataset_info())

        if method == "GET" and path == "/reference_data":
            return _json_response(start_response, 200, reference_data())

        if method == "POST" and path == "/reload_db":
            load_data_from_db(app)
            return _json_response(start_response, 200, {"status": "Base recargada correctamente"})

        if method == "POST" and path == "/calc_cpra":
            payload = _read_json_body(environ)
            data = InputData(**payload)
            return _json_response(start_response, 200, calc_cpra(data))

        return _json_response(start_response, 404, {"detail": "Not Found"})
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Error de solicitud"
        return _json_response(start_response, int(exc.status_code), {"detail": detail})
    except Exception as exc:  # noqa: BLE001
        return _json_response(start_response, 500, {"detail": f"Internal Server Error: {type(exc).__name__}"})
