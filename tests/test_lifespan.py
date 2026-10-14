"""Use inherited HTTP routes and real engine scheduling with model inference stubbed."""
import asyncio
import importlib
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pytest
import httpx
from wyoming.event import async_read_event, async_write_event
from wyoming.tts import Synthesize

# Local source inspection tests need no multi-GB torch installation.
# In the built image, tests import the actual torch package.
if importlib.util.find_spec('torch') is None:
    sys.modules['torch'] = types.SimpleNamespace(Tensor=type('Tensor', (), {}))

import dual.main as main
from app.tts import TTSEngine

async def test_single_engine_http_wyoming_concurrency_cancellation(monkeypatch):
    monkeypatch.setenv('WYOMING_PORT','0')
    main.settings.pocket_tts_api_key = 'test-key'
    main.settings.pocket_tts_voice = 'alba'
    active, peak, loads = 0, 0, 0
    def load(self):
        nonlocal loads
        loads += 1
        self._model = object()
        self._sample_rate = 24000
    def generate(self,text,voice):
        nonlocal active, peak
        active += 1
        peak = max(peak,active)
        time.sleep(.04)
        active -= 1
        return np.zeros(100,dtype=np.float32),24000
    monkeypatch.setattr(TTSEngine,'load',load)
    monkeypatch.setattr(TTSEngine,'_synthesize_sync',generate)
    async with main.lifespan(main.app):
        assert main.app.state.engine is main.app.state.wyoming.engine
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
            assert (await client.get('/health')).json()['model_loaded']
            assert (await client.post('/v1/audio/speech',json={'input':'Hello'})).status_code == 401
            headers={'Authorization':'Bearer test-key'}
            async def http():
                r=await client.post('/v1/audio/speech',headers=headers,json={'input':'Hello','voice':'alba','response_format':'wav'})
                assert r.status_code == 200 and r.content.startswith(b'RIFF')
            async def wyoming():
                port=main.app.state.wyoming.server.sockets[0].getsockname()[1]
                reader,writer=await asyncio.open_connection('127.0.0.1',port)
                await async_write_event(Synthesize('Hello').event(),writer)
                while (await asyncio.wait_for(async_read_event(reader),3)).type != 'audio-stop': pass
                writer.close()
                await writer.wait_closed()
            abandoned=asyncio.create_task(main.app.state.engine.synthesize('abandoned','alba'))
            await asyncio.sleep(.01)
            abandoned.cancel()
            with pytest.raises(asyncio.CancelledError): await abandoned
            await asyncio.gather(http(),wyoming())
            assert (await client.post('/v1/audio/speech',headers=headers,json={'input':'Hello','voice':'not-a-voice'})).status_code==400
    assert loads == 1 and peak == 1 and active == 0
    main.settings.pocket_tts_api_key = ''

async def test_bind_failure_shuts_down_engine(monkeypatch):
    monkeypatch.setenv('WYOMING_PORT','invalid')
    closed=[]
    class Engine:
        def __init__(self,settings): self._executor=ThreadPoolExecutor(1)
        def load(self): pass
        def validate_voice(self,voice): pass
        async def synthesize(self,text,voice): pass
        def shutdown(self): closed.append(True)
    monkeypatch.setattr(main,'TTSEngine',Engine)
    with pytest.raises(ValueError):
        async with main.lifespan(main.app): pass
    assert closed == [True]
