"""Retain every upstream HTTP route; replace only startup/shutdown."""
import asyncio
import os
from contextlib import asynccontextmanager
from app.main import app, settings
from app.tts import TTSEngine, KNOWN_VOICES
from dual.server import WyomingService
from dual.voices import voice_aliases
from dual.stock import enable_stock_references

@asynccontextmanager
async def lifespan(app):
    if settings.pocket_tts_max_concurrency != 1:
        raise ValueError("POCKET_TTS_MAX_CONCURRENCY must be 1: the shared model is not thread safe")
    engine = TTSEngine(settings)
    service = None
    pending = set()
    original_synthesize = engine.synthesize
    async def synthesize(text, voice):
        task = asyncio.create_task(original_synthesize(text, voice))
        pending.add(task)
        def finished(done):
            pending.discard(done)
            if not done.cancelled():
                done.exception()  # Retrieve errors even if the client left.
        task.add_done_callback(finished)
        return await asyncio.shield(task)
    engine.synthesize = synthesize
    try:
        await asyncio.to_thread(engine.load)
        stock_references = enable_stock_references(engine, settings, KNOWN_VOICES)
        app.state.engine = engine
        voice = os.environ.get("WYOMING_VOICE") or settings.pocket_tts_voice
        import json
        aliases = voice_aliases(settings, KNOWN_VOICES, voice,
                               json.loads(os.environ.get("WYOMING_VOICES", "{}")), stock_references=stock_references)
        for target in aliases.values():
            engine.validate_voice(target)
        service = WyomingService(engine, aliases, settings.pocket_tts_max_input_chars,
                                 os.environ.get("WYOMING_LANGUAGE", "en"))
        await service.start(os.environ.get("WYOMING_HOST", "0.0.0.0"),
                            int(os.environ.get("WYOMING_PORT", "10200")))
        app.state.wyoming = service
        yield
    finally:
        if service:
            await service.stop()
        await asyncio.gather(*list(pending), return_exceptions=True)
        # Wait for executor work, including HTTP requests abandoned by clients.
        await asyncio.to_thread(engine._executor.shutdown, wait=True, cancel_futures=True)
        engine.shutdown()

app.router.lifespan_context = lifespan
