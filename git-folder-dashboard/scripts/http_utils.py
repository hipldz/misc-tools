from io import BytesIO

from flask import jsonify, request, send_file


def api_error(detail: str, status_code: int):
    response = jsonify({"detail": detail, "success": False})
    response.status_code = status_code
    return response


def send_bytes_download(content: bytes, filename: str, mimetype: str):
    payload = BytesIO(content)
    kwargs = {"mimetype": mimetype, "as_attachment": True}
    try:
        return send_file(payload, download_name=filename, **kwargs)
    except TypeError:
        payload.seek(0)
        return send_file(payload, attachment_filename=filename, **kwargs)


def read_json_body():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}

