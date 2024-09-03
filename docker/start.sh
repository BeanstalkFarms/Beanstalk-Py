#!/bin/bash

cd $(dirname "$0")

DOCKER_ENV=$1
if [ -z "$DOCKER_ENV" ]; then
  DOCKER_ENV="dev"
fi

export DOCKER_ENV

# Can optionally provide a specific service to start. Defaults to all
docker compose -p bots-$DOCKER_ENV up -d
