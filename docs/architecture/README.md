# Rendszerarchitektúra

Felmérési dátum: 2026-09-25. Forrás: `README.md`, `compose.yaml`, `backend/`, `frontend/`, `mobile/`, `database/`, `deploy/`.

## Fő összetevők

- **Webes kliens:** `frontend/`, React 18 és Vite 5. A böngészős munkalap-, eszköz-, HR-, CRM-, beszerzési és adminfelületeket tartalmazza.
- **Mobilkliens:** `mobile/`, React és Capacitor 8. Android technikusi folyamatok, kamera, aláírás és push értesítések.
- **API és üzleti logika:** `backend/app/`, FastAPI. A `routers/` adja a végpontokat, a `services/` a fő üzleti műveleteket; a modellek, sémák és jogosultsági réteg ugyanitt találhatók.
- **Adattárolás:** PostgreSQL; az adatbázis-séma változásai `backend/migrations/versions/` alatt, Alembic-kel.
- **Futtatás és biztonság:** `compose.yaml` szervezi a szolgáltatásokat és hálózatokat. A migráció külön one-shot szolgáltatás, a push worker külön folyamat. A mentési agent és runner elkülönül; a malware ellenőrzéshez ClamAV szolgáltatás van.
- **Telepítés és ellenőrzés:** `deploy/` tartalmazza a VPS és security eljárásokat; `scripts/` és `test-release.ps1` a kiadási ellenőrzéseket.

## Adatfolyam

```text
React web / Capacitor mobil
            |
            v
       FastAPI backend ----> PostgreSQL
            |                    ^
            +--> ClamAV          |
            +--> backup agent    +-- Alembic migrate
            +--> push outbox --> push worker
```

## Fontos határok

- A `compose.yaml` több külön hálózatot és service-szintű jogosultságot definiál. Ezeket változtatás előtt a teljes Compose-konfigurációval együtt kell ellenőrizni.
- A mentési könyvtárak futási/üzemeltetési adatok; nem kerülhetnek a forrásverziókövetésbe.
- A production eljárásokat a meglévő security és release dokumentációval együtt kell követni. Ez a leírás nem helyettesíti azokat.
