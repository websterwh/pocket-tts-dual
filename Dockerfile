FROM epidoux/pocket-tts:0.1.1
USER root
RUN /opt/venv/bin/python -m pip install --no-cache-dir 'pocket-tts==3.3.0' 'wyoming==1.7.2' \
 && /opt/venv/bin/python -c "from importlib.metadata import version; assert version('pocket-tts') == '3.3.0'"
COPY dual /app/dual
LABEL org.opencontainers.image.source="https://github.com/websterwh/pocket-tts-dual"
EXPOSE 8000 10200
USER 1000:1000
ENTRYPOINT ["/opt/venv/bin/python", "-m", "uvicorn", "dual.main:app"]
CMD ["--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
