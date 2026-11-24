FROM python:3.12-slim AS protocol-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY deos-protocol/include /build/include
COPY deos-protocol/src /build/src

RUN gcc -std=c99 -Wall -Wextra -O2 -fPIC -shared \
    -I/build/include \
    /build/src/deos_frame.c \
    /build/src/deos_codec.c \
    /build/src/deos_registry.c \
    -o /build/libdeos_protocol.so


FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/shared
ENV DEOS_PROTOCOL_LIB_PATH=/usr/local/lib/libdeos_protocol.so

COPY --from=protocol-builder /build/libdeos_protocol.so /usr/local/lib/libdeos_protocol.so
RUN ldconfig

COPY services/web-ui/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY deos-protocol/include /app/deos-protocol/include
COPY shared/ /app/shared/
COPY services/web-ui/app.py app.py
COPY services/web-ui/static /app/static

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
