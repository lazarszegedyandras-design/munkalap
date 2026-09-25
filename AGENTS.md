# Fejlesztési szabályok – Munkalap

## Projekt

A LUNA IT munkalap- és eszköznyilvántartó rendszere. A jelenlegi kiadás a `VERSION` fájl szerint 0.31.0. A fő részek: FastAPI backend, React/Vite webes kliens, React/Capacitor mobilkliens, PostgreSQL/Alembic és Docker Compose.

## Minden feladat előtt

- Olvasd el a `CURRENT_STATUS.md` és az érintett `docs/` fájlokat, majd ellenőrizd a `git status --short --branch` kimenetét.
- A `main`/`master` ágon ne módosíts fájlokat. Hozz létre külön feladatágat vagy worktree-t. Meglévő, nem commitolt változtatást ne írj felül.
- A termékkövetelményeket és architekturális döntéseket a `docs/features/` és `docs/decisions/` alatt rögzítsd, mielőtt nagyobb megvalósításba kezdesz.
- Ne commitolj, ne pusholj és ne telepíts külön felhasználói utasítás nélkül.

## Biztonság és adatok

- Ne olvass be vagy jeleníts meg titkokat a `.env`, credential, kulcs, adatbázis-dump vagy mentésfájlokból, ha a feladat nem igényli kifejezetten.
- A meglévő security kontrollokat ne gyengítsd. A backend, migrate és push-worker non-root működése, a `cap_drop: ALL` és a `no-new-privileges` beállítások megtartandók. A kiemelt jogosultságú segédszolgáltatásokat csak külön terv és ellenőrzés alapján módosítsd.
- A mentési és visszaállítási folyamatot, valamint a production környezetet ne indítsd vagy módosítsd automatikusan.

## Módosítás után

- Futtasd a változtatáshoz releváns teszteket. A teljes kiadási ellenőrzés belépési pontja `./test-release.ps1 -Suite all`; futtatása előtt olvasd el a `STEP1_TEST_BASELINE_v0.30.1.md` leírást.
- Ellenőrizd a diffet, sorold fel a módosított fájlokat és a teszteredményeket.
- Frissítsd a `CURRENT_STATUS.md` fájlt: kész munka, ellenőrzés, ismert hiány és következő lépés.
