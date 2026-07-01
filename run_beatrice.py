#!/usr/bin/env python3
"""Run the EburonHub Beatrice voice orchestration agent.

Examples:
  # Real voice (needs GEMINI_API_KEY and a mic):
  python3 run_beatrice.py

  # Text mode (no mic/API), still uses the real Gemini text model for reasoning:
  python3 run_beatrice.py --text

  # Fully offline end-to-end smoke (text + mock reasoning + dry-run dispatch):
  python3 run_beatrice.py --text --mock-llm --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from orchestrator import config
from orchestrator.llm import get_model
from orchestrator.orchestrator import Orchestrator
from orchestrator.preview_server import PreviewServer
from orchestrator.transcript import TranscriptBus
from orchestrator.voice_session import make_session
from orchestrator.voice_bridge import VoiceBridge


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="EburonHub Beatrice voice orchestration agent")
    p.add_argument("--text", action="store_true", help="text mode (no mic/API) for the voice session")
    p.add_argument("--mock-llm", action="store_true", help="use canned reasoning (no network/API key)")
    p.add_argument("--dry-run", action="store_true", help="don't really invoke opencode; write a sample preview")
    p.add_argument("--workspace", type=Path, default=None, help="project dir opencode runs in")
    p.add_argument("--serve", action="store_true", help="host the mobile voice bridge (HTTP+WS) and run the orchestrator over it")
    p.add_argument("--mock-live", action="store_true", help="use a mock Gemini Live session (no key/network) for the bridge")
    p.add_argument("--host", default="0.0.0.0", help="bridge bind host (0.0.0.0 to reach the LAN)")
    p.add_argument("--port", type=int, default=0, help="bridge port (0 = free)")
    p.add_argument("--web-dir", type=Path, default=None, help="web assets dir to serve")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    s = config.settings()
    if args.workspace:
        s.workspace_dir = args.workspace.resolve()
    # --mock-live implies offline reasoning, so it never needs a Gemini key.
    if args.mock_live and not args.mock_llm:
        logging.getLogger("eburon").warning("--mock-live implies offline reasoning; enabling --mock-llm automatically")
        args.mock_llm = True
    if not args.mock_llm and not args.text and not args.mock_live:
        config.ensure_api_key(s)  # real voice needs a key
    if args.mock_llm:
        s.gemini_api_key = s.gemini_api_key or "mock"

    bus = TranscriptBus()
    if args.serve:
        voice = VoiceBridge(s, bus, mock_live=args.mock_live, host=args.host,
                            port=args.port, web_dir=args.web_dir, dry_run=args.dry_run)
    else:
        voice = make_session(s, bus, text_mode=args.text)
    if args.mock_live and not args.mock_llm:
        log = logging.getLogger("eburon")
        log.warning("--mock-live implies offline reasoning; enabling --mock-llm automatically")
        args.mock_llm = True
    model = get_model(s, mock=args.mock_llm)
    preview = PreviewServer(s)
    orch = Orchestrator(
        settings=s, voice=voice, bus=bus, model=model, preview=preview, dry_run=args.dry_run,
    )

    try:
        asyncio.run(orch.run())
    except KeyboardInterrupt:
        print("\nShutting down Beatrice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
