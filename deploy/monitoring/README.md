# Monitoring - v0.26.0

The production stack exposes two safe public probes through HTTPS:

- `https://APP_DOMAIN/health` - frontend/edge liveness.
- `https://APP_DOMAIN/api/health/ready` - backend readiness including PostgreSQL, runtime storage and ClamAV.

## External monitoring is mandatory

At least one monitor must run outside the VPS. Configure a third-party uptime monitor to check both URLs every 60 seconds and alert after two or three consecutive failures. This external monitor is the only component that can alert when the whole VPS, provider network or DNS path is unavailable.

## Optional local Uptime Kuma

The production Compose file contains an optional `monitoring` profile pinned to Uptime Kuma 2.5.3. It binds only to `127.0.0.1:3001` by default and is not public.

Enable it by adding this to `.env.production`:

```
ENABLE_LOCAL_MONITORING=true
UPTIME_KUMA_PORT=3001
```

Open it through an SSH tunnel, for example from an administrator workstation:

```
ssh -L 3001:127.0.0.1:3001 user@VPS
```

Then browse to `http://127.0.0.1:3001` locally and create monitors for:

- `https://APP_DOMAIN/health`
- `https://APP_DOMAIN/api/health/ready`
- TLS certificate expiry

Local Uptime Kuma is useful for history and component visibility, but it does not replace the external monitor.
