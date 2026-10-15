"""Wyoming transport using the already-loaded HTTP engine."""
import asyncio
import logging
import numpy as np
from wyoming.audio import AudioStart, AudioChunk, AudioStop
from wyoming.event import Event, async_read_event, async_write_event
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.tts import Synthesize

_LOG = logging.getLogger(__name__)


def pcm16(audio):
    values = np.asarray(audio, dtype=np.float32).squeeze()
    if values.ndim > 1:
        raise ValueError("Expected mono audio")
    values = np.atleast_1d(values)
    values = np.nan_to_num(values, nan=0.0, posinf=1.0, neginf=-1.0)
    return np.clip(np.rint(values * 32768), -32768, 32767).astype("<i2").tobytes()


class WyomingService:
    def __init__(self, engine, aliases, max_chars=5000, language="en", default_voice_name=None):
        self.engine, self.aliases, self.max_chars = engine, aliases, max_chars
        self.clients = set()
        self.server = None
        self.stopping = False
        attribution = Attribution(name="Kyutai", url="https://github.com/kyutai-labs/pocket-tts")
        common = dict(attribution=attribution, installed=True, version="3.3.0")
        self.info = Info(tts=[TtsProgram(name="pocket-tts", voices=[
            TtsVoice(name=name, description=((default_voice_name or "Default (configured voice)") if name == "default" else name),
                     languages=[language], **common) for name in aliases
        ], description="Pocket TTS", **common)])

    async def start(self, host, port):
        self.server = await asyncio.start_server(self._accept, host, port)

    def _accept(self, reader, writer):
        task = asyncio.create_task(self._client(reader, writer))
        pair = (task, writer, reader)
        self.clients.add(pair)
        task.add_done_callback(lambda _: self.clients.discard(pair))

    async def _client(self, reader, writer):
        try:
            while not self.stopping:
                event = await async_read_event(reader)
                if event is None:
                    break
                try:
                    if Describe.is_type(event.type):
                        await async_write_event(self.info.event(), writer)
                    elif Synthesize.is_type(event.type):
                        request = Synthesize.from_event(event)
                        if not isinstance(request.text, str) or not request.text.strip():
                            raise ValueError("Text must not be empty")
                        if len(request.text) > self.max_chars:
                            raise ValueError("Text exceeds maximum input length")
                        name = request.voice.name if request.voice and request.voice.name else "default"
                        # Named aliases are advertised; direct voice paths retain upstream policy.
                        voice = self.aliases.get(name, name)
                        self.engine.validate_voice(voice)
                        audio, rate = await self.engine.synthesize(request.text, voice)
                        data = pcm16(audio)
                        await async_write_event(AudioStart(rate=rate, width=2, channels=1).event(), writer)
                        for offset in range(0, len(data), 8192):
                            await async_write_event(AudioChunk(rate=rate, width=2, channels=1,
                                                   audio=data[offset:offset+8192]).event(), writer)
                        await async_write_event(AudioStop().event(), writer)
                    else:
                        raise ValueError("Unsupported event")
                except (ConnectionError, BrokenPipeError):
                    break
                except Exception:
                    _LOG.exception("Wyoming request failed")
                    await async_write_event(Event(type="error", data={
                        "code": "synthesis-failed", "text": "Unable to synthesize; check server logs and voice settings"
                    }), writer)
        except (ConnectionError, asyncio.IncompleteReadError, ValueError):
            _LOG.debug("Wyoming client disconnected", exc_info=True)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def stop(self):
        self.stopping = True
        if self.server:
            self.server.close()
        clients = list(self.clients)
        for _, writer, reader in clients:
            writer.close()
            reader.feed_eof()
        # Do not cancel synthesis: cancellation could release the engine semaphore
        # while its executor thread still uses the model.
        await asyncio.gather(*(task for task, _, _ in clients), return_exceptions=True)
        if self.server:
            await self.server.wait_closed()
