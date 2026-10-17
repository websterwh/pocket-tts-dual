# Pocket TTS: HTTP + Wyoming

Docker image extending `epidoux/pocket-tts:0.1.1` with Pocket TTS **3.3.0** and Wyoming **1.7.2**. One FastAPI process loads one `TTSEngine`, shared by both interfaces.

| Interface | Port | Features |
|---|---|---|
| HTTP | 8000 | `/v1/audio/speech`, `/health`, upstream voice selection and response formats |
| Wyoming | 10200 | Service discovery, voice selection, mono 16-bit little-endian PCM at the model sample rate |

## Run

```sh
docker pull ghcr.io/websterwh/pocket-tts-dual:latest

docker run -d --name pocket-tts \
  --restart unless-stopped --stop-timeout 300 \
  -p 8000:8000/tcp -p 10200:10200/tcp \
  -v /path/to/models:/models \
  -e POCKET_TTS_LANGUAGE=english \
  -e POCKET_TTS_VOICE=alba \
  -e POCKET_TTS_MAX_CONCURRENCY=1 \
  -e HF_HOME=/models/hf-cache \
  -e HF_HUB_OFFLINE=0 \
  ghcr.io/websterwh/pocket-tts-dual:latest
```

Replace `/path/to/models` with a host directory. The image runs as UID/GID `1000:1000`; model and reference files must be readable and the cache directory writable by that identity.

```sh
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"Hello.","voice":"alba","response_format":"wav"}' \
  -o speech.wav
```

HTTP retains the upstream `wav`, `pcm`, `mp3`, `opus`, `aac` and `flac` formats. Optional `POCKET_TTS_API_KEY` enables HTTP bearer authentication. Keep the unauthenticated Wyoming port on a trusted network.

## CPU and CUDA in one image

Use the same `latest` image for either device:

- `POCKET_TTS_DEVICE=cpu`: use the bundled CPU runtime; no CUDA download.
- `POCKET_TTS_DEVICE=cuda` or `cuda:0`: on first startup, install a pinned PyTorch 2.13.0 / CUDA 12.6 runtime from the official PyTorch index. This build supports the Quadro P2000's Pascal architecture. Attach the GPU through the container runtime as well.

CUDA packages are cached at `/models/.pocket-tts-runtime`, so the existing `/models` bind mount preserves them across restarts and container replacements. Initial installation needs outbound internet access, several GB of disk space, and write permission on the cache directory. `HF_HUB_OFFLINE` controls model downloads independently; it does not disable runtime package installation. Later starts use the completed cache without downloading it again. Interrupted or failed installations are not treated as complete. Shared-cache installations use a file lock.

`POCKET_TTS_RUNTIME_CACHE` can select a different persistent writable directory. Set `POCKET_TTS_AUTO_INSTALL_CUDA=false` to require a pre-populated cache and prevent package downloads. CUDA runtime installation and import failures stop startup with an error; the launcher does not silently switch a requested CUDA deployment to CPU. The health check allows up to 15 minutes for first-time startup downloads.

Changing the device requires recreating the container. CPU dynamic quantization and CUDA are separate modes; leave `POCKET_TTS_QUANTIZE=false` for CUDA. Model weights, voice aliases, and sampling settings work the same way on both devices.

## Home Assistant

Add **Wyoming Protocol** using the Docker host's LAN IP and port `10200`. Select Pocket TTS as the text-to-speech provider in the voice assistant configuration. Voice labels use each catalog name or configured alias; `Default (configured voice)` selects the configured default reference. Set `WYOMING_VOICE_NAME=Narrator` to give this entry a custom display name without changing its `default` voice ID or existing assistant selections. Additional custom voices display the names supplied in `WYOMING_VOICES`.

After updating the image, recreate the container and reload the Wyoming integration to refresh voice information. A Home Assistant restart is normally unnecessary. This image supports Wyoming `describe`/`info` discovery and does not publish an mDNS service itself.

## Multiple custom voices

Mount reference clips and exported voice states under `/models`, then configure aliases:

```sh
-e POCKET_TTS_ALLOW_ARBITRARY_VOICE=true \
-e POCKET_TTS_VOICE=/models/voices/narrator.wav \
-e WYOMING_VOICES='{"Narrator":"/models/voices/narrator.wav","Reader":"/models/voices/reader.safetensors","Guide":"/models/voices/guide.wav"}'
```

Each alias appears separately in Home Assistant. Wyoming requests select it with `voice.name`. HTTP requests use the underlying path as `voice`; `WYOMING_VOICES` aliases apply to Wyoming only. Voice conditioning states are cached per reference in the shared engine.

A voice-state `.safetensors` file is an exported conditioning state, **not a full model checkpoint**. States must be compatible with the loaded model. WAV references also require a model that supports audio conditioning. Selecting a different reference does not load another model.

## Custom models

Set these variables in addition to the custom voice configuration:

```sh
-e POCKET_TTS_CONFIG=/models/config.yaml \
-e POCKET_TTS_LANGUAGE= \
-e POCKET_TTS_DEVICE=cpu
```

A full model `.safetensors` weights file is selected through the custom YAML. `POCKET_TTS_CHECKPOINT` is an optional training-checkpoint override (for example `/models/checkpoint.pt`), not a voice-state selector. Leave it empty when the YAML already selects the intended model weights.

Pocket TTS may reject precomputed stock voice states with a custom configuration or custom weights. For custom models with voice-cloning support, this image resolves catalog names such as `alba`, `anna` and `george` to Pocket TTS's official reference recordings and creates conditioning states using the loaded model. This works for both HTTP catalog names and Wyoming selections. Long stock recordings are truncated to 30 seconds for conditioning. Recordings download on first use and are cached under the Hugging Face cache directory; offline operation requires the recordings to be cached first.

Stock speaker references and custom aliases are advertised together. A model without voice-cloning support advertises only its configured default and explicit custom aliases in custom-model mode. Compatible exported voice states can still be supplied explicitly.

The same fine-tuned model generates every voice. Selecting a stock speaker reference does not switch to the released stock model, and the fine-tuning may affect how those speakers sound. Exact stock-model output requires using the released model configuration, or running a separate stock-model container.

To use the stock catalog, clear CONFIG and CHECKPOINT, select a supported LANGUAGE, and recreate the container. Switching full checkpoints requires a container restart with the new configuration; one container does not switch between full checkpoints per request.

## Environment

All upstream model-loading, audio-generation and HTTP variables remain supported.

| Variable | Purpose |
|---|---|
| `POCKET_TTS_LANGUAGE` | Stock model language; empty for custom configuration |
| `POCKET_TTS_CONFIG` | Custom YAML path or URL |
| `POCKET_TTS_CHECKPOINT` | Optional full model checkpoint override |
| `POCKET_TTS_DEVICE` | `cpu` or supported CUDA device |
| `POCKET_TTS_VOICE` | HTTP default voice; Wyoming fallback |
| `POCKET_TTS_ALLOW_ARBITRARY_VOICE` | Enables reference paths and URLs for trusted callers |
| `POCKET_TTS_TEMPERATURE` | Model sampling temperature |
| `POCKET_TTS_MAX_TOKENS` | Generation text chunk limit passed to Pocket TTS |
| `POCKET_TTS_NUM_THREADS` | CPU thread count |
| `POCKET_TTS_MAX_CONCURRENCY` | Must be `1` for shared inference |
| `POCKET_TTS_MAX_INPUT_CHARS` | Input limit shared by HTTP and Wyoming |
| `HF_HOME` / `HF_HUB_OFFLINE` | Model cache directory / offline mode |
| `WYOMING_VOICE` | Wyoming default; falls back to `POCKET_TTS_VOICE` |
| `WYOMING_VOICE_NAME` | Optional display name for the default voice |
| `WYOMING_VOICES` | JSON mapping of display aliases to reference paths or voice IDs |
| `WYOMING_LANGUAGE` | Discovery language metadata; defaults to `en` |
| `WYOMING_HOST` / `WYOMING_PORT` | Bind address / port; defaults to `0.0.0.0:10200` |

Use one Uvicorn worker. Both interfaces share the engine's inference queue. Shutdown drains inference before closing the executor. Wyoming audio is sent in chunks after generation completes; incremental text synthesis is not advertised.

## MOS deployment

In the MOS container editor, select `ghcr.io/websterwh/pocket-tts-dual:latest`, publish TCP ports `8000` and `10200`, mount a model directory at `/models`, and enter the desired environment variables. Use a restart policy and a shutdown timeout long enough for pending inference.

For Compose deployments, adapt [compose.yaml](compose.yaml), particularly the host volume path and model/voice settings. Apply updates with:

```sh
docker compose pull
docker compose up -d
```

Changing environment values requires container recreation. A plain restart does not apply edited Compose configuration.

## Build and test

GitHub Actions builds `linux/amd64`, runs the tests inside the candidate image, and verifies real-model speech over HTTP and Wyoming before publishing that candidate to GHCR. Pushes to `main` publish `latest` and `sha-<full-commit>` tags; version tags publish semantic version tags. Pull requests validate without publishing.

```sh
docker build -t pocket-tts-dual:test .
docker run --rm --user root --entrypoint sh \
  -v "$PWD/tests:/tests:ro" -v "$PWD/pytest.ini:/app/pytest.ini:ro" \
  pocket-tts-dual:test -c 'python -m pip install pytest pytest-asyncio httpx && python -m pytest -c /app/pytest.ini /tests -q -p no:cacheprovider'
```

Tests cover discovery, distinct voice labels, stock reference routing, custom model catalog filtering, aliases, PCM conversion, request validation, shutdown, HTTP authentication, single-engine loading, shared scheduling and cancellation. Unit tests stub inference; the workflow additionally exercises the real default model. Custom model assets can be validated separately in the target deployment.

References: [base image](https://hub.docker.com/r/epidoux/pocket-tts), [Pocket TTS](https://github.com/kyutai-labs/pocket-tts), [Wyoming](https://github.com/rhasspy/wyoming), [MOS](https://docs.mos-official.net/).
