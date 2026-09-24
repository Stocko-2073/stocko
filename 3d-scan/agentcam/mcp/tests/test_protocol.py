"""The shared examples are valid under the server's own models."""

import json

from agentcam.models import BoardInfo, CaptureMetadata, Hello, PhotoRequest, RequestUpdate
from conftest import PROTOCOL

EXAMPLES = PROTOCOL / "examples"


def load(name):
    return json.loads((EXAMPLES / name).read_text())


def test_examples_parse():
    Hello.model_validate(load("hello.json"))
    BoardInfo.model_validate(load("welcome.json")["board"])
    for item in load("requests.json")["items"]:
        PhotoRequest.model_validate(item)
    RequestUpdate.model_validate(load("request_update.json"))
    CaptureMetadata.model_validate(load("capture_meta.json"))


def test_full_path_detection():
    snap = load("requests.json")["items"]
    assert [PhotoRequest.model_validate(i).options.needs_full_path() for i in snap] == [False, True, False, False]
