import asyncio
import numpy as np
import pytest
from wyoming.event import Event, async_read_event as read_event, async_write_event

async def async_read_event(reader):
    return await asyncio.wait_for(read_event(reader), 3)
from wyoming.info import Describe, Info
from wyoming.tts import Synthesize, SynthesizeVoice
from wyoming.audio import AudioChunk
from dual.server import WyomingService, pcm16

class Engine:
    def __init__(self):
        self.calls = []
        self.done = False
    def validate_voice(self, voice):
        if voice == 'bad':
            raise ValueError('unknown voice')
    async def synthesize(self, text, voice):
        self.calls.append((text, voice))
        await asyncio.sleep(.02)
        self.done = True
        return np.array([-1, 0, 1], dtype=np.float32), 24000

async def connect(service):
    return await asyncio.open_connection('127.0.0.1', service.server.sockets[0].getsockname()[1])

async def test_discovery_audio_selection_errors_shutdown():
    engine = Engine()
    server = WyomingService(engine, {'default':'/models/voice.wav', 'alba':'alba'}, max_chars=10)
    await server.start('127.0.0.1', 0)
    reader, writer = await connect(server)
    try:
        await async_write_event(Describe().event(), writer)
        info = Info.from_event(await async_read_event(reader))
        assert [v.name for v in info.tts[0].voices] == ['default','alba']
        # Home Assistant uses description when present, falling back to name.
        labels = [v.description or v.name for v in info.tts[0].voices]
        assert labels == ['Default (configured voice)', 'alba']
        assert len(set(labels)) == len(labels)
        assert not info.tts[0].supports_synthesize_streaming
        for voice, expected in [(None,'/models/voice.wav'), (SynthesizeVoice(name='alba'),'alba')]:
            await async_write_event(Synthesize('hello', voice).event(), writer)
            start = await async_read_event(reader)
            assert start.type == 'audio-start'
            assert all(start.data[k] == v for k,v in {'rate':24000,'width':2,'channels':1}.items())
            chunk = AudioChunk.from_event(await async_read_event(reader))
            assert np.frombuffer(chunk.audio, '<i2').tolist() == [-32768,0,32767]
            assert (await async_read_event(reader)).type == 'audio-stop'
            assert engine.calls[-1] == ('hello',expected)
        for event in [Synthesize('x'*11).event(), Synthesize('').event(), Synthesize('ok',SynthesizeVoice(name='bad')).event(),Event(type='invalid')]:
            await async_write_event(event,writer)
            assert (await async_read_event(reader)).type == 'error'
        assert len(engine.calls)==2
    finally:
        await server.stop()
        writer.close()
        await writer.wait_closed()
    assert not server.clients

async def test_shutdown_drains_generation():
    engine = Engine()
    server = WyomingService(engine, {'default':'alba'})
    await server.start('127.0.0.1',0)
    reader,writer = await connect(server)
    await async_write_event(Synthesize('hello').event(),writer)
    while not engine.calls:
        await asyncio.sleep(.001)
    await server.stop()
    assert engine.done
    writer.close()
    await writer.wait_closed()

def test_pcm_clipping_nonfinite_and_shapes():
    assert np.frombuffer(pcm16([float('nan'),float('inf'),float('-inf'),2,-2]),'<i2').tolist() == [0,32767,-32768,32767,-32768]
    assert len(pcm16(np.zeros((1,5)))) == 10
    with pytest.raises(ValueError): pcm16(np.zeros((2,5)))
