FROM postgres:16-alpine

RUN apk add --no-cache pgbackrest \
    && mkdir -p /var/lib/pgbackrest /etc/pgbackrest \
    && chown -R postgres:postgres /var/lib/pgbackrest /etc/pgbackrest

COPY database/pgbackrest.conf /etc/pgbackrest/pgbackrest.conf
RUN chown postgres:postgres /etc/pgbackrest/pgbackrest.conf \
    && chmod 640 /etc/pgbackrest/pgbackrest.conf
