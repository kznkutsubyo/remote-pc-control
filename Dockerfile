FROM python:3.12-slim
WORKDIR /app
COPY pc-phone-remote/app.py pc-phone-remote/companion.py pc-phone-remote/relay_server.py pc-phone-remote/unlock_ipc.py ./
USER 65532:65532
EXPOSE 8080
CMD ["python", "-u", "relay_server.py"]
