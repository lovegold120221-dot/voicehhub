"""Voice bridge: a local HTTP + WebSocket server that exposes Beatrice over the
web so a phone (the remote channel) can bind to the user's local EburonHub
machine. The Gemini Live session runs server-side (the API key never reaches the
phone); the bridge relays browser PCM into the session and streams the model's
audio + transcriptions back.

VoiceBridge also implements the VoiceSession protocol so the Orchestrator can
use it as its voice: mobile transcripts feed the orchestrator bus, and the
orchestrator's say() is injected into the active Live session (TTS'd to the
phone).
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from .config import Settings
from .transcript import TranscriptBus, Utterance
from .preview_server import PreviewServer
from .voice_session import BEATRICE_SYSTEM
from . import model_registry
from . import control_api
from .llm import get_model

log = logging.getLogger("eburon.bridge")


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        try:
            s.close()
        except Exception:
            pass
    return ip


class LiveConnection:
    """Async wrapper over a google-genai Live session with a mock fallback."""

    async def send(self, input: Any, **kwargs) -> None: ...  # noqa: D401
    def receive(self) -> AsyncIterator[Any]: ...


class RealLiveConnection(LiveConnection):
    def __init__(self, session, cm) -> None:
        self._session = session
        self._cm = cm

    async def send(self, input: Any, **kwargs) -> None:
        await self._session.send(input=input, **kwargs)

    def receive(self):
        return self._session.receive()

    async def close(self) -> None:
        await self._cm.__aexit__(None, None, None)


class MockLiveConnection(LiveConnection):
    """Echoes a canned assistant turn so the bridge is testable without a key."""

    def __init__(self) -> None:
        self._in: asyncio.Queue = asyncio.Queue()
        self._closed = asyncio.Event()

    async def send(self, input: Any, **kwargs) -> None:
        await self._in.put(input)

    def receive(self):
        return self._iter()

    async def _iter(self):
        # Continuously turn incoming sends into mock Live events so the bridge
        # behaves like a real session across multiple turns.
        while not self._closed.is_set():
            try:
                item = await asyncio.wait_for(self._in.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if isinstance(item, dict) and item.get("mime_type") == "audio/pcm":
                yield _MockResp(server_content=_MockContent(input_transcription=_MockText("hello beatrice")))
                yield _MockResp(server_content=_MockContent(
                    output_transcription=_MockText(
                        "Hi! I'm Beatrice, connected to your machine. What should we build?"),
                    turn_complete=True))
                yield _MockResp(data=b"\x00\x00" * 480)
            elif isinstance(item, dict) and item.get("mime_type", "").startswith("image/"):
                yield _MockResp(server_content=_MockContent(
                    output_transcription=_MockText("I can see your camera feed. Tell me what you'd like to do."),
                    turn_complete=True))
            elif isinstance(item, str):
                yield _MockResp(server_content=_MockContent(
                    output_transcription=_MockText(f"You said: {item}. Got it."), turn_complete=True))

    async def close(self) -> None:
        self._closed.set()


class _MockResp:
    def __init__(self, data=None, server_content=None, text=None) -> None:
        self.data = data
        self.server_content = server_content
        self.text = text


class _MockContent:
    def __init__(self, input_transcription=None, output_transcription=None, turn_complete=False, model_turn=None) -> None:
        self.input_transcription = input_transcription
        self.output_transcription = output_transcription
        self.turn_complete = turn_complete
        self.model_turn = model_turn


class _MockText:
    def __init__(self, text: str) -> None:
        self.text = text


async def open_live(settings: Settings, *, mock: bool) -> LiveConnection:
    if mock:
        return MockLiveConnection()
    from google import genai
    from google.genai import types
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY required for the live bridge.")
    client = genai.Client(http_options={"api_version": "v1beta"}, api_key=settings.gemini_api_key)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=BEATRICE_SYSTEM,
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        media_resolution="MEDIA_RESOLUTION_MEDIUM",
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=settings.voice_name)
            )
        ),
        context_window_compression=types.ContextWindowCompressionConfig(
            trigger_tokens=104857, sliding_window=types.SlidingWindow(target_tokens=52428)
        ),
    )
    cm = client.aio.live.connect(model=settings.voice_model, config=config)
    session = await cm.__aenter__()
    return RealLiveConnection(session, cm)


class VoiceBridge:
    """HTTP + WS server and a VoiceSession for the Orchestrator."""

    def __init__(self, settings: Settings, bus: TranscriptBus, *, mock_live: bool = False,
                 host: str = "0.0.0.0", port: int = 0, web_dir: Optional[Path] = None,
                 dry_run: bool = False) -> None:
        self.settings = settings
        self.bus = bus
        self.mock_live = mock_live
        self.host = host
        self.port = port
        self.web_dir = (web_dir or Path(__file__).resolve().parent.parent / "web").resolve()
        self.dry_run = dry_run
        self.controller = control_api.Controller(
            settings=settings, model=get_model(settings, mock=mock_live),
            preview=PreviewServer(settings), dry_run=dry_run,
        )
        self._runner = None
        self._site = None
        self.url: str | None = None
        self.lan_url: str | None = None
        self._conn: LiveConnection | None = None
        self._ws: Optional[Any] = None
        self._user_buf = ""
        self._asst_buf = ""
        self._say_queue: asyncio.Queue = asyncio.Queue()

    # ---- VoiceSession protocol -----------------------------------------
    async def start(self) -> None:
        from aiohttp import web
        app = web.Application()
        app.router.add_get("/", self._index)
        app.router.add_get("/voice.html", self._voice)
        app.router.add_get("/ws", self._ws_handler)
        app.router.add_get("/settings", self._get_settings)
        app.router.add_post("/settings", self._post_settings)
        for r in control_api.routes(self.controller):
            app.router.add_route(r.method, r.path, r.handler)
        # static: vendor, icons, manifest, sw.js
        for sub in ("vendor",):
            app.router.add_static(f"/{sub}/", path=str(self.web_dir / sub))
        app.router.add_static("/", path=str(self.web_dir), show_index=False)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        ip = _lan_ip()
        self.url = f"http://127.0.0.1:{self.port}"
        self.lan_url = f"http://{ip}:{self.port}"
        log.info("Voice bridge serving %s  (LAN: %s)  web=%s", self.url, self.lan_url, self.web_dir)
        asyncio.create_task(self._say_pump(), name="say_pump")

    async def stop(self) -> None:
        if self._conn:
            await self._conn.close()
        if self._runner:
            await self._runner.cleanup()

    async def say(self, text: str) -> None:
        # Queue so it works even before a client connects; relayed into the Live
        # session which TTS's it to the phone. Also log as an assistant turn.
        await self._say_queue.put(text)
        await self.bus.publish(Utterance("assistant", text))

    async def _say_pump(self) -> None:
        while True:
            text = await self._say_queue.get()
            if self._conn is not None:
                try:
                    await self._conn.send(f"RELAY: {text}")
                except Exception:
                    log.exception("say relay failed")

    # ---- HTTP handlers --------------------------------------------------
    async def _index(self, request):
        from aiohttp import web
        return web.FileResponse(self.web_dir / "index.html")

    async def _voice(self, request):
        from aiohttp import web
        return web.FileResponse(self.web_dir / "voice.html")

    async def _get_settings(self, request):
        from aiohttp import web
        import json
        catalog = {}
        cat_path = self.web_dir / "models.json"
        if cat_path.is_file():
            try: catalog = json.loads(cat_path.read_text())
            except json.JSONDecodeError: catalog = {}
        return web.json_response({
            "settings": {
                "voice_model": self.settings.voice_model,
                "reason_model": self.settings.reason_model,
                "backend": self.settings.default_backend,
                "dispatch_model": self.settings.dispatch_model,
                "ollama_base_url": self.settings.ollama_base_url,
                "workspace_dir": str(self.settings.workspace_dir),
            },
            "catalog": catalog,
        })

    async def _post_settings(self, request):
        from aiohttp import web
        import json
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)
        persisted = model_registry.load_settings()
        for k in ("voice_model", "reason_model", "backend", "dispatch_model", "ollama_base_url", "workspace_dir"):
            if k in body:
                persisted[k] = body[k]
        model_registry.save_settings(persisted)
        # apply to the live runtime for new sessions
        if "voice_model" in body: self.settings.voice_model = body["voice_model"]
        if "reason_model" in body: self.settings.reason_model = body["reason_model"]
        if "backend" in body: self.settings.default_backend = body["backend"]
        if "dispatch_model" in body: self.settings.dispatch_model = body["dispatch_model"] or None
        if "ollama_base_url" in body: self.settings.ollama_base_url = body["ollama_base_url"]
        if "workspace_dir" in body and body["workspace_dir"]:
            from pathlib import Path
            self.settings.workspace_dir = Path(body["workspace_dir"])
            self.settings.workspace_dir.mkdir(parents=True, exist_ok=True)
        log.info("Settings updated: %s", persisted)
        return web.json_response({"ok": True, "settings": persisted})

    # ---- WebSocket relay ------------------------------------------------
    # ---- WebSocket relay ------------------------------------------------
    async def _ws_handler(self, request):
        from aiohttp import web
        ws = web.WebSocketResponse(max_msg_size=0)
        await ws.prepare(request)
        self._ws = ws
        log.info("Mobile client connected (%s)", request.remote)
        try:
            self._conn = await open_live(self.settings, mock=self.mock_live)
        except Exception as e:
            await ws.send_json({"type": "error", "message": f"bridge: {e}"})
            await ws.close()
            return ws

        recv_task = asyncio.create_task(self._relay_in(ws), name="relay_in")
        out_task = asyncio.create_task(self._relay_out(ws), name="relay_out")
        try:
            # Run until the client disconnects (recv ends) or the relay dies.
            await asyncio.wait({recv_task, out_task}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            recv_task.cancel(); out_task.cancel()
            await self._conn.close()
            self._conn = None
            self._ws = None
            log.info("Mobile client disconnected")
        return ws

    async def _relay_in(self, ws) -> None:
        async for msg in ws:
            from aiohttp import WSMsgType
            if msg.type == WSMsgType.BINARY:
                if self._conn:
                    await self._conn.send({"data": bytes(msg.data), "mime_type": "audio/pcm"})
            elif msg.type == WSMsgType.TEXT:
                try:
                    obj = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                if not self._conn:
                    continue
                if obj.get("type") == "text":
                    await self._conn.send(input=str(obj.get("text", "")), end_of_turn=True)
                elif obj.get("type") == "image":
                    await self._conn.send(input={"data": obj.get("data"), "mime_type": obj.get("mime_type", "image/jpeg")})
                elif obj.get("type") == "stop":
                    await self._conn.send(input=".", end_of_turn=True)

    async def _relay_out(self, ws) -> None:
        assert self._conn is not None
        async for response in self._conn.receive():
            await self._handle_out(ws, response)

    async def _handle_out(self, ws, response) -> None:
        if getattr(response, "data", None):
            try:
                await ws.send_bytes(response.data)
            except Exception:
                return
        sc = getattr(response, "server_content", None)
        if sc:
            it = getattr(sc, "input_transcription", None)
            ot = getattr(sc, "output_transcription", None)
            if it and getattr(it, "text", None):
                self._user_buf += it.text
                await ws.send_json({"type": "user_text", "text": it.text})
            if ot and getattr(ot, "text", None):
                self._asst_buf += ot.text
                await ws.send_json({"type": "assistant_text", "text": ot.text})
                await ws.send_json({"type": "state", "state": "speaking"})
            if getattr(sc, "turn_complete", False) or getattr(sc, "model_turn", None):
                await self._flush(ws)
        if getattr(response, "text", None):
            await ws.send_json({"type": "assistant_text", "text": response.text})

    async def _flush(self, ws) -> None:
        if self._user_buf.strip():
            await self.bus.publish(Utterance("user", self._user_buf.strip()))
            self._user_buf = ""
        if self._asst_buf.strip():
            self._asst_buf = ""
        await ws.send_json({"type": "state", "state": "listening" if self._user_buf else "idle"})
