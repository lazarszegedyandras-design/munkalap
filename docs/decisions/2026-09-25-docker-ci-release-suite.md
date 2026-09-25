# Elkülönített Docker-teszt GitHub Actions alatt

## Helyzet

A `main` ágon a backend és a webes kliens ellenőrzése már kötelező, de a PostgreSQL-migrációkat, a konténerképeket és a szolgáltatások együttműködését nem vizsgálják. A `test-release.sh --suite all` erre elkülönített tesztprojektet használ, de a korábbi helyi forrásmanifest elavult és nincs Gitben.

## Döntés

Ubuntu GitHub Actions futtatón a meglévő `test-release.sh --suite all` indul. A futás előtt a `scripts/create_release_manifest.py` kizárólag a checkoutban Git által követett, a teszthez szükséges forrásfájlokból készít új SHA-256 manifestet. A generátor a `safe_source_path` szabályait alkalmazza, a meglévő manifestet nem írja felül, és a Gitből kizárt privát adatokat nem veszi fel. A gyökér `.dockerignore` nem kerül a szűrt snapshotba, mert a tesztimage-eknek a webes és mobil tesztforrásra is szükségük van.

A workflow csak olvasási jogosultságot kap. Nem használ production titkot, adatbázist, runtime-mappát vagy távoli telepítési célpontot. Hibánál a tesztjelentést rövid ideig megőrzi a GitHubon. A `Docker release suite` job csak az első sikeres pull request-futás után válhat kötelező státuszellenőrzéssé.

## Következmények

A GitHubon futó ellenőrzés a checkout adott commitjának izolált, konténeres tesztje. Nem production jóváhagyás, és nem helyettesíti az Android eszköztesztet, a VPS/TLS, külső mentés vagy aktuális sérülékenységek ellenőrzését. A CI által generált manifest nem jelent külön, kézzel jóváhagyott release-forráslistát.
