FROM debian:12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends icecast2 gettext-base media-types \
    && if ! getent group icecast2 >/dev/null; then groupadd --system icecast2; fi \
    && if ! id -u icecast2 >/dev/null 2>&1; then useradd --system --gid icecast2 --home-dir /var/lib/icecast2 --no-create-home icecast2; fi \
    && rm -rf /var/lib/apt/lists/*

COPY docker/icecast/icecast.xml.template /opt/radio-recorder-icecast/icecast.xml.template
COPY docker/icecast/start-icecast.sh /opt/radio-recorder-icecast/start-icecast.sh

RUN sed -i 's/\r$//' /opt/radio-recorder-icecast/start-icecast.sh /opt/radio-recorder-icecast/icecast.xml.template \
    && chmod +x /opt/radio-recorder-icecast/start-icecast.sh

EXPOSE 8000

CMD ["/opt/radio-recorder-icecast/start-icecast.sh"]
