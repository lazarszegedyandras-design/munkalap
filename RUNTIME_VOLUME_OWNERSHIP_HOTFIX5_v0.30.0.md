# v0.30.0 Runtime Volume Ownership Hotfix 5

## Hiba
A backend már `10001:10001` non-root userként indul, de a korábbi kiadásokból meglévő `app_runtime` Docker volume gyökere és/vagy tartalma root tulajdonú maradt. Emiatt az entrypoint fail-closed ellenőrzése leállt:

```text
Runtime directory is not writable by uid 10001: /app/runtime
```

## Javítás
- Új egyszer futó `runtime-permissions` service.
- Csak az `app_runtime` volume-ot mountolja RW módban.
- Nincs hálózata (`network_mode: none`).
- `cap_drop: ALL` után csak `CHOWN`, `FOWNER`, `DAC_OVERRIDE` capabilityket kap.
- A volume teljes tartalmát `10001:10001` ownerre rendezi, az owner számára szükséges írási/traverse jogokat biztosítja.
- A backend továbbra is `10001:10001`, `cap_drop: ALL`, `no-new-privileges` alatt fut.
- A backend és a backup-agent csak a permission initializer sikeres befejezése után indulhat.
- A fizikai runtime restore után a backup-agent újra normalizálja a restored fájlok ownershipjét, hogy egy későbbi restore se tegye indíthatatlanná a non-root backendet.

## Adatbiztonság
A hotfix nem törli és nem cseréli le az `app_runtime` volume-ot. Csak ownershipet és az ownerhez tartozó szükséges permission biteket módosítja. `docker compose down -v` továbbra is tilos.
