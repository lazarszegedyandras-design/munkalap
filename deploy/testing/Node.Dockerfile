FROM node:22.16.0-alpine
# These unit tests use Node built-ins only. No npm install/build is implied for
# the mobile client (the current mobile source does not have a lockfile).
COPY frontend/src /suite/frontend/src
COPY frontend/tests /suite/frontend/tests
COPY frontend/package.json /suite/frontend/package.json
COPY mobile/src /suite/mobile/src
COPY mobile/tests /suite/mobile/tests
COPY mobile/package.json /suite/mobile/package.json
USER node
WORKDIR /suite
ENTRYPOINT ["node", "--test"]
