"""Request contract of the 22 AI endpoints, transcribed from AI_INTEGRATION.md and the Phase-0 client.

The service's openapi.json is not in this repository (decision D73), so this table stands in for it:
for every endpoint, the HTTP method, the request fields the service accepts (it forbids extra fields)
and the fields it requires. Replace this table with a check against openapi.json once it is available.
"""

INCIDENT_FIELDS = {
    "workshop_id",
    "machine_id",
    "profile",
    "lang",
    "voice_file_path",
    "audio_file_path",
    "panel_photo_path",
    "tool_photo_path",
    "tool_reference_photo_path",
    "text",
    "context",
    "baseline_ref",
    "answers",
    "incident_context",
    "catalog_machines",
}

# path -> (method, allowed body fields, required body fields); GET endpoints have no body
CONTRACT: dict[str, tuple[str, set[str], set[str]]] = {
    "/healthz": ("GET", set(), set()),
    "/readyz": ("GET", set(), set()),
    "/v1/meta/models": ("GET", set(), set()),
    "/v1/risk/predict": ("POST", {"machine_id", "workshop_id", "features", "context"}, set()),
    "/v1/risk/rank": ("POST", {"machines"}, {"machines"}),
    "/v1/risk/what-if": ("POST", {"machine_id", "current", "overrides"}, {"machine_id", "current", "overrides"}),
    "/v1/anomaly/readings": ("POST", {"machine_id", "history", "latest"}, {"machine_id", "history", "latest"}),
    "/v1/audio/route": ("POST", {"file_path", "mode"}, set()),
    "/v1/audio/baseline": ("POST", {"machine_id", "file_paths", "embedder_id"}, {"machine_id", "file_paths"}),
    "/v1/audio/analyze": (
        "POST",
        {"machine_id", "file_path", "baseline_ref"},
        {"machine_id", "file_path", "baseline_ref"},
    ),
    "/v1/speech/transcribe": ("POST", {"file_path", "language_hint", "profile", "catalog_machines"}, {"file_path"}),
    "/v1/speech/parse": ("POST", {"text", "profile", "catalog_machines"}, {"text"}),
    "/v1/vision/quality": ("POST", {"file_path", "image_b64"}, set()),
    "/v1/vision/panel": ("POST", {"file_path", "machine_id", "workshop_id", "lang"}, {"file_path"}),
    "/v1/vision/tool-compare": (
        "POST",
        {"file_path_reference", "file_path_current"},
        {"file_path_reference", "file_path_current"},
    ),
    "/v1/vision/part-defect": ("POST", {"file_path", "category"}, {"file_path"}),
    "/v1/manuals/index": (
        "POST",
        {"manual_id", "machine_id", "file_path", "language"},
        {"manual_id", "machine_id", "file_path"},
    ),
    "/v1/manuals/{id}/status": ("GET", set(), set()),
    "/v1/manuals/query": ("POST", {"machine_id", "query", "top_k"}, {"machine_id", "query"}),
    "/v1/incident/analyze": ("POST", INCIDENT_FIELDS, {"workshop_id"}),
    "/v1/assistant/operator": (
        "POST",
        {"machine_id", "question", "lang", "incident_context"},
        {"machine_id", "question"},
    ),
    "/v1/assistant/dashboard": ("POST", {"workshop_id", "query", "lang"}, {"workshop_id", "query"}),
}
