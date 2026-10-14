# Pocket TTS: HTTP + Wyoming

An extension of `epidoux/pocket-tts:0.1.1`, with `pocket-tts==3.3.0` and `wyoming==1.7.2`. One FastAPI process loads exactly one upstream `TTSEngine`; HTTP and Wyoming use that same engine, voice cache and inference queue.

- HTTP: port **8000**, inherited `/v1/audio/speech` and `/health` routes, authentication, response formats and voice allowlist.
- Wyoming: port **10200**, `describe` → `info` discovery and `synthesize` → `audio-start`, PCM `audio-chunk`, `audio-stop`.
- Audio: native model sample rate, mono, signed 16-bit little-endian PCM. Audio generation completes before chunks are sent; incremental text synthesis is not advertised.
- One worker and concurrency **1** are required. Do not override the entrypoint to start multiple workers. Disconnected HTTP clients cannot release the model queue early. Shutdown stops accepting Wyoming connections and drains inference before closing the executor.

## Publication status

Source prepared and five local tests passed against application files extracted from the base image. Publication and real-model image validation must be confirmed by a successful GitHub Actions run before treating the following image as available. No custom checkpoint is included in the repository or image.

## Build and release

The `Test, build and publish` workflow builds for `linux/amd64` (the base image architecture), runs tests against the actual inherited application, starts the real default model, validates both protocols, and only then pushes that exact candidate to GHCR. A failed test prevents publication.

Push to `main` publishes `latest` and `sha-<full-commit>`; a `v1.0.0` tag publishes `1.0.0` and a commit tag. PRs test without publishing. Workflow permissions include `packages: write`; no separate registry secret is needed. Configure repository Actions permissions to permit these actions and GHCR writes. In the package settings, set package visibility to **Public** for anonymous pulls (GitHub may initially create a private package).

Once that run succeeds and visibility is public:

```sh
docker pull ghcr.io/websterwh/pocket-tts-dual:latest
```

For a reproducible deployment, replace `latest` in Compose with the successful build's `sha-...` tag or image digest. Check anonymous pull access from the deployment host. A private package instead requires `docker login ghcr.io` using a credential with package read permission.

## Deploy on MOS / existing Webby host

Use [compose.yaml](compose.yaml). It preserves `/mnt/cache/appdata/pocket-tts:/models` and your supplied environment. MOS supports Compose stacks; use its Compose editor with this YAML, or run the commands below on the server. Confirm the actual host path exists if migrating from another OS. The existing container and the new stack cannot both own ports 8000/10200 or the name `pocket-tts`.

1. Save the current container settings and image name. Back up the model/configuration files before changing the deployment. Keep the old container for rollback.
2. Stop and rename it; this releases its name and ports without deleting it:

   ```sh
   docker stop pocket-tts
   docker rename pocket-tts pocket-tts-backup
   ```

3. In a directory containing the supplied `compose.yaml`, deploy:

   ```sh
   docker compose pull
   docker compose up -d
   docker compose logs -f pocket-tts
   ```

4. Check both protocols and try your own reference voice:

   ```sh
   curl --fail http://Webby:8000/health
   curl --fail http://Webby:8000/v1/audio/speech \
     -H 'Content-Type: application/json' \
     -d '{"input":"Hello from Pocket TTS.","response_format":"wav"}' -o test.wav
   docker exec -i pocket-tts python - <<'PY'
   import asyncio
   from wyoming.event import async_read_event, async_write_event
   from wyoming.info import Describe
   async def main():
       reader, writer = await asyncio.open_connection('127.0.0.1', 10200)
       await async_write_event(Describe().event(), writer)
       print(await asyncio.wait_for(async_read_event(reader), 10))
       writer.close()
       await writer.wait_closed()
   asyncio.run(main())
   PY
   ```

In the MOS container editor the equivalent is image `ghcr.io/websterwh/pocket-tts-dual:latest`, bridge networking, TCP mappings `8000:8000` and `10200:10200`, the `/models` mapping above, and all environment entries in Compose. The image runs as UID/GID **1000:1000**; that identity needs read access to model/config/voice files and write access to `/models/hf-cache`. Allow several minutes for initial model loading/downloads. Health is available after lifespan startup completes.

Rollback:

```sh
docker compose down
docker rename pocket-tts-backup pocket-tts
docker start pocket-tts
```

This does not remove `/models`. Do not use volume deletion options.

## Home Assistant

Add the **Wyoming Protocol** integration, entering the Webby server's LAN IP and port **10200**. Select Pocket TTS in your voice assistant's text-to-speech configuration. `describe` advertises `default` and the existing voice catalog. This image does not advertise mDNS/zeroconf, so add the host and port manually. Expose TCP 10200 between Home Assistant and Webby.

`default` resolves to `WYOMING_VOICE` when set, otherwise `POCKET_TTS_VOICE`. For a friendly custom voice entry, add an environment value:

```yaml
WYOMING_VOICES: '{"my-reference":"/models/voice_reference.wav","my-embedding":"/models/voice.safetensors"}'
```

Select that alias in Home Assistant or send a Wyoming `voice.name`. The existing voice validation still applies. `POCKET_TTS_ALLOW_ARBITRARY_VOICE=true` is required for reference paths or HF URLs. Reference WAVs and compatible saved voice embeddings are passed unchanged to Pocket TTS's `get_state_for_audio_prompt`; compatibility depends on the loaded model. Catalog entries describe the inherited allowlist, not a guarantee every voice is cached or compatible with a custom checkpoint. `HF_HUB_OFFLINE=0` permits missing assets to download.

Wyoming has no bearer authentication or TLS here. Keep it on a trusted LAN. `POCKET_TTS_API_KEY` continues to protect HTTP only. Arbitrary voice access permits callers to supply paths/URLs, so restrict access to both ports when enabled.

## Models and voices

All upstream model-loading and audio-generation settings are inherited:

| Setting | Your Compose value / behavior |
|---|---|
| `POCKET_TTS_CONFIG` | `/models/config.yaml` |
| `POCKET_TTS_CHECKPOINT` | Empty by default; set to an explicit checkpoint if the YAML does not already identify it |
| `POCKET_TTS_LANGUAGE` | Empty; upstream passes `None` for your custom config |
| `POCKET_TTS_DEVICE` | `cpu` |
| `POCKET_TTS_VOICE` | `/models/voice_reference.wav` |
| `POCKET_TTS_TEMPERATURE` | `0.2` |
| `POCKET_TTS_MAX_TOKENS` | `150` |
| `POCKET_TTS_NUM_THREADS` | `8` |
| `POCKET_TTS_MAX_CONCURRENCY` | Must be `1` |
| `POCKET_TTS_ALLOW_ARBITRARY_VOICE` | `true` |
| `HF_HUB_OFFLINE` / `HF_HOME` | `0` / `/models/hf-cache` |
| `WYOMING_VOICE` | `/models/voice_reference.wav` |
| `WYOMING_LANGUAGE` | `en`, discovery metadata only; does not change the loaded model |
| `WYOMING_HOST` / `WYOMING_PORT` | Defaults `0.0.0.0` / `10200` |
| `WYOMING_VOICES` | Optional JSON alias-to-voice mapping |

The upstream `POCKET_TTS_MAX_INPUT_CHARS` applies to both protocols. Unknown voices and inference errors return Wyoming `error` events; details go to container logs. Standard HTTP formats and validation remain upstream behavior.

Choose compatible voices per HTTP request with `voice`, or per Wyoming request with `voice.name`. Change `POCKET_TTS_CONFIG`, `POCKET_TTS_CHECKPOINT`, language or sampling settings and recreate the container to switch models/settings. In Compose use `docker compose up -d --force-recreate`; a plain restart does not apply edited Compose environment. Changing voices does not load another model. The fine-tuned checkpoint remains private in your mounted storage.

For the original built-in English model, clear CONFIG and CHECKPOINT and set LANGUAGE to `english`, with VOICE/WYOMING_VOICE set to `alba`, then recreate. Other compatible model configurations work the same way.

## Development and validation

```sh
docker build -t pocket-tts-dual:test .
docker run --rm --user root --entrypoint sh \
  -v "$PWD/tests:/tests:ro" -v "$PWD/pytest.ini:/app/pytest.ini:ro" \
  pocket-tts-dual:test -c 'python -m pip install pytest pytest-asyncio httpx && python -m pytest /tests -q'
```

Tests cover real TCP discovery/framing, PCM clipping/endianness, voice selection, invalid requests, draining shutdown, startup cleanup, HTTP bearer authentication, inherited HTTP WAV rendering, single-engine loading, and shared scheduling including cancellation. Model inference is stubbed in unit tests. The workflow separately runs `tests/smoke.py` against real default-model inference. Your private model must be checked on Webby because its assets are not available to CI.

Upstream references: [base image](https://hub.docker.com/r/epidoux/pocket-tts), [Pocket TTS](https://github.com/kyutai-labs/pocket-tts), [Wyoming](https://github.com/rhasspy/wyoming), [MOS walkthrough](https://docs.mos-official.net/docs/Installation/First-Walkthrough/).
