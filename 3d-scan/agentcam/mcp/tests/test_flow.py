"""The whole loop through the real HTTP/WebSocket API, with the fake phone."""

import asyncio
import hashlib
import json

import aiohttp
import numpy as np

from agentcam import fakephone
from agentcam.geometry import pose_difference
from conftest import images_of, orbit, running_server, text_of


async def call(client, name, **args):
    return await client.call_tool(name, args)


async def test_request_capture_wait(tmp_path):
    async with running_server(tmp_path) as (client, base):
        r = await call(client, "request_photos", requests=[orbit(-90, 55, 380), orbit(0, 40, 320, hold="portrait")])
        text = text_of(r)
        assert "Queued 2 request(s)" in text and "No phone has connected yet" in text
        phone = asyncio.create_task(fakephone.run(base, count=2, skip=set(), seed=3, once=False))
        r = await call(client, "wait_for_photos", timeout_s=30)
        assert await phone == 2
        text = text_of(r)
        assert text.startswith("2/2 done."), text
        assert len(images_of(r)) == 2
        for rid in ("r0001", "r0002"):
            folder = next((tmp_path / rid).iterdir())
            meta = json.loads((folder / "meta.json").read_text())
            analysis = json.loads((folder / "analysis.json").read_text())
            true = np.array(meta["fake_true_pose"])
            dt, dr = pose_difference(np.array(analysis["pnp"]["camera_to_page"]), true)
            assert dt < 1.0 and dr < 0.2, (rid, dt, dr)          # the still's own pose is good
            assert analysis["phone_vs_pnp"]["dt_mm"] < 5
            assert (folder / "preview.jpg").exists()
        # portrait hold: the stored image is sideways, the preview upright (taller than wide)
        assert json.loads(next((tmp_path / "r0002").iterdir()).joinpath("meta.json").read_text())[
            "image"]["upright_rotation_cw_deg"] == 90
        assert "r0001 [captured]" in text_of(await call(client, "list_requests"))


async def test_freeform_requests_need_no_pose(tmp_path):
    async with running_server(tmp_path) as (client, base):
        r = await call(client, "request_photos", requests=[{**orbit(-90, 55, 380), "kind": "freeform"}])
        assert r.is_error and "takes no pose" in text_of(r)
        r = await call(client, "request_photos", requests=[{"kind": "freeform", "note": "what's on the page?"}])
        assert "r0001 [queued] freeform (whole page in view)" in text_of(r)
        await fakephone.run(base, count=1, skip=set(), seed=5, once=False)
        text = text_of(await call(client, "wait_for_photos", ids=["r0001"], timeout_s=10))
        assert "r0001 [captured] freeform" in text and "still PnP" in text, text


async def test_skip_is_reported(tmp_path):
    async with running_server(tmp_path) as (client, base):
        await call(client, "request_photos", requests=[orbit(-90, 55, 380)])
        await fakephone.run(base, count=1, skip={"r0001"}, seed=0, once=False)
        text = text_of(await call(client, "wait_for_photos", ids=["r0001"], timeout_s=5))
        assert "r0001 [skipped]" in text and "fakephone was told to skip it" in text


async def test_snapshots_follow_the_queue(tmp_path):
    async with running_server(tmp_path) as (client, base):
        async with aiohttp.ClientSession() as s, s.ws_connect(f"{base}/v1/ws") as ws:
            await ws.send_json(fakephone.hello())
            assert (await next_of(ws, "welcome"))["board"]["dictionary"] == "DICT_4X4_100"
            assert (await next_of(ws, "requests"))["items"] == []
            await call(client, "request_photos", requests=[orbit(-90, 55, 380), orbit(90, 55, 380)])
            snap = await next_of(ws, "requests")
            assert [i["id"] for i in snap["items"]] == ["r0001", "r0002"]
            assert snap["items"][0]["target"]["camera_to_page"]
            await call(client, "cancel_requests", ids=["r0001"])
            assert [i["id"] for i in (await next_of(ws, "requests"))["items"]] == ["r0002"]
            status = json.loads(text_of(await call(client, "phone_status")))
            assert status["connected"] and status["app_state"] == "foreground"


async def test_uploads_are_idempotent_and_checked(tmp_path):
    async with running_server(tmp_path) as (client, base):
        await call(client, "request_photos", requests=[orbit(-90, 55, 380)])
        url = f"{base}/v1/requests/r0001/captures/c1"
        body = b"not really a jpeg"
        sha = hashlib.sha256(body).hexdigest()
        async with aiohttp.ClientSession() as s:
            async def put(data, digest, name="image.jpg"):
                async with s.put(f"{url}/files/{name}", data=data, headers={"X-AgentCam-SHA256": digest}) as r:
                    return r.status
            assert await put(body, sha) == 201
            assert await put(body, sha) == 200                       # a retry
            assert await put(b"other", hashlib.sha256(b"other").hexdigest()) == 409
            assert await put(body, "0" * 64, name="depth.png") == 409   # corrupted in transit
            assert await put(body, sha, name="..") in (400, 404)
            meta = {"capture_id": "c1", "request_id": "r0001", "captured_at": "t", "path": "fast",
                    "files": [{"name": "image.jpg", "sha256": sha, "bytes": len(body)},
                              {"name": "depth.png", "sha256": sha, "bytes": len(body)}],
                    "image": {"file": "image.jpg", "w": 10, "h": 10},
                    "intrinsics": {"K": [[10, 0, 5], [0, 10, 5], [0, 0, 1]], "source": "test", "ref_dims": [10, 10]},
                    "pose": {"camera_to_page": None, "source": "none"}}
            async with s.post(f"{url}/commit", json=meta) as r:
                assert r.status == 409                              # depth.png never arrived
            meta["files"].pop()
            async with s.post(f"{url}/commit", json=meta) as r:
                assert r.status == 200 and (await r.json())["duplicate"] is False
            async with s.post(f"{url}/commit", json=meta) as r:
                assert r.status == 200 and (await r.json())["duplicate"] is True
        # An unreadable image still completes the request, with the analysis error recorded.
        text = text_of(await call(client, "wait_for_photos", ids=["r0001"], timeout_s=5))
        assert "r0001 [captured]" in text and "could not read" in text


async def test_state_survives_a_restart(tmp_path):
    async with running_server(tmp_path) as (client, base):
        await call(client, "request_photos", requests=[orbit(-90, 55, 380), orbit(0, 55, 380)])
        await fakephone.run(base, count=1, skip=set(), seed=1, once=False)
        await call(client, "wait_for_photos", ids=["r0001"], timeout_s=10)
    async with running_server(tmp_path) as (client, _):
        text = text_of(await call(client, "list_requests"))
        assert "r0001 [captured]" in text and "r0002 [queued]" in text
        r = await call(client, "request_photos", requests=[orbit(90, 55, 380)])
        assert "r0003" in text_of(r)


async def test_a_second_server_on_the_same_data_explains_itself(tmp_path):
    async with running_server(tmp_path), running_server(tmp_path) as (second, _):
        r = await call(second, "list_requests")
        assert r.is_error and "Only one Claude Code session" in text_of(r)


async def test_a_newer_phone_connection_replaces_the_older(tmp_path):
    async with running_server(tmp_path) as (_, base):
        async with aiohttp.ClientSession() as s:
            old = await s.ws_connect(f"{base}/v1/ws")
            await old.send_json(fakephone.hello())
            await next_of(old, "requests")
            new = await s.ws_connect(f"{base}/v1/ws")
            await new.send_json(fakephone.hello())
            await next_of(new, "requests")
            while (await old.receive()).type != aiohttp.WSMsgType.CLOSE:
                pass
            assert old.close_code == 4001
            await new.close()


async def test_wait_times_out_with_status(tmp_path):
    async with running_server(tmp_path) as (client, _):
        await call(client, "request_photos", requests=[orbit(-90, 55, 380)])
        text = text_of(await call(client, "wait_for_photos", timeout_s=0.5))
        assert "0/1 done. Timed out waiting." in text and "Ask the user to open AgentCam" in text


async def test_impossible_requests_are_rejected_whole(tmp_path):
    async with running_server(tmp_path) as (client, _):
        r = await call(client, "request_photos", requests=[orbit(-90, 55, 380), orbit(0, -10, 300)])
        assert "Nothing queued: request 1" in text_of(r)
        assert "No requests" in text_of(await call(client, "list_requests"))


async def test_preflight_warns_about_doubtful_requests(tmp_path):
    async with running_server(tmp_path) as (client, _):
        # Too low to see markers; too close to focus; a 5x view of only the page interior.
        r = await call(client, "request_photos", requests=[orbit(0, 12, 300), orbit(-90, 60, 90),
                                                           {**orbit(-90, 90, 400), "options": {"lens": "telephoto"}}])
        text = text_of(r)
        assert "looking only 12 deg down" in text
        assert "closer than the wide lens focuses" in text
        assert "only 0 markers predicted in view" in text


async def next_of(ws, t: str) -> dict:
    while True:
        msg = json.loads((await asyncio.wait_for(ws.receive(), 5)).data)
        if msg["t"] == t:
            return msg


async def test_a_port_taken_on_localhost_is_reported(tmp_path):
    """Another program on 127.0.0.1:<port> would silently take the phone's
    local traffic, since aiohttp binds with SO_REUSEADDR."""
    import socket
    from conftest import free_port
    port = free_port()
    squatter = socket.socket()
    squatter.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    squatter.bind(("127.0.0.1", port))
    squatter.listen()
    try:
        async with running_server(tmp_path, port) as (client, _):
            r = await call(client, "phone_status")
            assert r.is_error and f"already using port {port}" in text_of(r)
    finally:
        squatter.close()
