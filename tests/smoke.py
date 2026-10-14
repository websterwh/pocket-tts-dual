"""Run inside the started candidate image (real model, no test doubles)."""
import asyncio
import io
import json
import urllib.request
import wave
from importlib.metadata import version
from wyoming.event import async_read_event, async_write_event
from wyoming.info import Describe, Info
from wyoming.tts import Synthesize
assert version('pocket-tts') == '3.3.0'
request = urllib.request.Request('http://127.0.0.1:8000/v1/audio/speech',
    data=json.dumps({'input':'Hello.', 'voice':'alba','response_format':'wav'}).encode(),
    headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request, timeout=180) as response:
    with wave.open(io.BytesIO(response.read())) as audio:
        assert audio.getnchannels() == 1 and audio.getnframes() > 0
async def main():
    reader, writer = await asyncio.open_connection('127.0.0.1',10200)
    try:
        await async_write_event(Describe().event(),writer)
        info = Info.from_event(await async_read_event(reader))
        assert 'alba' in [v.name for v in info.tts[0].voices]
        await async_write_event(Synthesize('Hello.').event(),writer)
        types, count = [], 0
        while True:
            event = await asyncio.wait_for(async_read_event(reader),180)
            assert event is not None and event.type != 'error', event
            types.append(event.type)
            count += len(event.payload or b'')
            if event.type == 'audio-start':
                assert event.data['width'] == 2 and event.data['channels'] == 1
            if event.type == 'audio-stop': break
        assert types[0] == 'audio-start' and count > 0
    finally:
        writer.close()
        await writer.wait_closed()
asyncio.run(main())
print('Real-model HTTP + Wyoming smoke passed')
