#!/bin/sh

set -eu

export ICECAST_HOSTNAME="${ICECAST_HOSTNAME:-localhost}"
export ICECAST_LOCATION="${ICECAST_LOCATION:-HamVOX Host}"
export ICECAST_ADMIN="${ICECAST_ADMIN:-radio@localhost}"
export ICECAST_SOURCE_PASSWORD="${ICECAST_SOURCE_PASSWORD:-change-me-source}"
export ICECAST_RELAY_PASSWORD="${ICECAST_RELAY_PASSWORD:-change-me-relay}"
export ICECAST_ADMIN_PASSWORD="${ICECAST_ADMIN_PASSWORD:-change-me-admin}"
export ICECAST_STREAM_NAME="${ICECAST_STREAM_NAME:-HamVOX Radio Stream}"
export ICECAST_STREAM_DESCRIPTION="${ICECAST_STREAM_DESCRIPTION:-Self-hosted HamVOX live radio stream}"
export ICECAST_STREAM_GENRE="${ICECAST_STREAM_GENRE:-Scanner}"

mkdir -p /var/log/icecast /var/lib/icecast2
chown -R icecast2:icecast2 /var/log/icecast /var/lib/icecast2

envsubst < /opt/radio-recorder-icecast/icecast.xml.template > /etc/icecast2/icecast.xml

exec icecast2 -c /etc/icecast2/icecast.xml -n
