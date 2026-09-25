# Aktuális állapot

Utolsó felmérés: 2026-09-25. Ez dokumentációs pillanatkép, nem tesztelt kiadási jóváhagyás.

## Rendszer

- A `VERSION`, a webes és mobil `package.json`, valamint a README alapján a jelenlegi forrásverzió 0.31.0.
- Backend: FastAPI, PostgreSQL, Alembic; a migrációk között a `0032_push_notifications.py` a legutolsó számozott fájl.
- Web: React/Vite; mobil: React/Capacitor Android.
- Futtatás: Docker Compose; adatbázis, backend, migráció, push worker, mentési szolgáltatások, frontend és ClamAV.

## Fejlesztési alapállapot

- A felmérés kezdetén a `C:\Munkalap` nem volt Git-repository. Az első commit (`b8fbedd`) a GitHub `main` ágán van; a tárhely nyilvános. A `main` ágon GitHub ágvédelem kér pull requestet és három CI-job sikerét (backend, frontend, Docker release suite), tiltja a kényszerített feltöltést és a törlést, és az adminisztrátorra is vonatkozik.
- A `.gitignore` kizárja a `.env`, `secrets/`, mentés-, import- és teszteredmény-mappákat, a régi release manifestet és egy korábbról maradt, érvénytelen Alembic-fájlt. A kizárásokat `git check-ignore` paranccsal ellenőriztük.
- Három vállalati kapcsolattartói, ügyfél/eszköz és HR-adatokat tartalmazó `backend/app/data/*.json` fájl ki van zárva a Gitből, a Docker build contextből és az új release manifestből. A helyi állományok érintetlenek. Az alkalmazás a `RUNTIME_DIR` alatti privát fájlokat részesíti előnyben; hiány esetén nem tölt be fiktív production adatot. Részletek: `docs/architecture/PRIVATE_DATA.md`.
- Az automatizált tesztek szintetikus adatokra álltak át. A felvehető forrásfájlok és a kizárt privát fájlok pontos értékeinek összevetése nem talált átmásolt ügyfél- vagy HR-adatot. A közismert privátkulcs- és tokenformátumokra végzett fájlszintű keresés nem adott találatot. Ez nem helyettesít minden jövőbeli adatvédelmi felülvizsgálatot.
- A `.githooks/` helyi commit- és pushvédelme be van kapcsolva. A `main`/`master` munkafájljainak szerkesztését a Git-hookok nem tudják megakadályozni; ezért kötelező külön feladatágon dolgozni.

## Ellenőrzések

- A `chore/docker-ci` ágon elkészült a követett forrásból manifestet készítő generátor és a teljes elkülönített Docker release suite GitHub-jobja. A GitHubon a teljes futás sikeres lett: backend, frontend és Docker release suite.
- A `chore/ci-checks` ágon elkészült a GitHub Actions backend- és frontend-ellenőrzés. A workflow YAML szerkezetét ellenőriztük; 33 helyi frontend teszt sikeres. A GitHubon a `Backend tests` és a `Frontend tests and build` job egyaránt sikeres lett, és mindkettő kötelező ellenőrzés a `main` ágon.
- A Git által felvehető 353 fájlból készült tiszta másolatban 128 backend teszt sikeres; egy mobilfotós teszt Windowsos fájltörlési hibája miatt nem futott ebben a körben. A másolat elkészülte óta egy döntési dokumentum és egy Git-szabályfájl került a jelöltek közé; az új hiányzóforrás API-teszt külön sikeres.
- A kapcsolódó backend céltesztek: 10 sikeres. Frontend munkalaptesztek: 10 sikeres. Release-harness egységtesztek: 31 sikeres, 8 kihagyott.
- Az eredeti munkakönyvtár teljes backend futása tartalmazza a helyben megőrzött, érvénytelen régi migrációs fájlt, ezért két migrációs teszt ott továbbra is sikertelen. A tiszta, Gitbe kerülő másolatban ezek a tesztek sikeresek.
- Docker daemon nem futott, ezért teljes konténeres release acceptance és production ellenőrzés nem történt. A régi `release-source-manifest.json` az új forráshoz nem érvényes.

## Következő lépések

1. A `Docker release suite` kötelező CI-ellenőrzés; az elkülönített teszt nem production-jóváhagyás.
2. Production build vagy frissítés előtt a három jóváhagyott privát adatfájlt biztonságosan a `RUNTIME_DIR` volume-ba kell telepíteni; éles adatot ne tegyél a forrásba vagy a konténerképbe.
3. Új release manifest és teljes, izolált `test-release.ps1 -Suite all` acceptance szükséges, amint a Docker daemon rendelkezésre áll. A Windowsos mobilfotó-teszt eltérését Linux/konténeres környezetben kell megerősíteni.
