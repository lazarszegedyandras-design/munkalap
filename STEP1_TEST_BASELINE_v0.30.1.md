# Munkalap v0.30.1 – elkülönített kiadási tesztalap

**Kiindulás:** v0.30.0 localhost-port hotfix6.<br>
**Kiadás:** 0.30.1, security fejlesztési terv 1. lépése.<br>
**Minősítés:** a tesztinfrastruktúra implementálva; a teljes Docker/PostgreSQL futás célkörnyezeti igazolásra vár. **Nem publikus VPS-jóváhagyás.**

## 1. Mi változott?

A tesztindító nem a production Compose-ot módosítja. Saját, önálló konfigurációt generál, minden futáshoz egyedi `munkalap-test-<azonosito>` projekttel. Nem olvassa a helyi `.env` vagy `.env.production` fájlt. Nem csatol éles adatbázist, runtime könyvtárat, secretet vagy Docker socketet, és nem publikál hostportot.

A build kontextusa a `release-source-manifest.json` szerint engedélyezett és SHA-256-tal ellenőrzött forrásmásolat. A listán kívüli helyi fájlok nem jutnak a tesztimage-ekbe. Módosult vagy hiányzó, listázott forrásnál a folyamat megáll. A manifest integritásellenőrzés, nem digitális aláírás.

A teszt PostgreSQL 16 saját, ideiglenes memóriabeli adattárat kap. Adatbázisneve `munkalap_test`, belső hosztneve `test-db`; a módosító ellenőrzések futásonkénti DB-markert is vizsgálnak. A tesztvégi takarítás kizárólag ennek az egyedi projektnek a konténereit és hálózatát érinti; globális prune vagy production volume-törlés nincs.

A backend, migrate, db-role-provisioner, runtime-permissions és push-worker ugyanazt a névvel/verzióval ellátott backend image-et használja. A tesztfutás során a konfiguráció már a tényleges image ID-kat rögzíti. A tesztparancs explicit belépési ponttal fut; a normál backend/migrate entrypoint pedig mellékhatás előtt elutasítja a tévesen hozzáadott parancsargumentumokat (exit 64).

## 2. Első futtatás Windows alatt

A csomagot először **külön könyvtárba**, például `C:\Munkalap-Step1` alá bontsd ki. A most működő telepítést ne írd felül csak a teszt kedvéért.

Előfeltétel: Python 3.10 vagy újabb, futó Docker Desktop Linux-konténerekkel és Compose v2-vel. A buildhez internetelérés kell az alapimage-ek és a függőségek letöltéséhez. A build erőforrást használ; elsőként ne az éles VPS-en teszteld.

Windows alatt a release runner megtartja a `ProgramFiles` rendszerkörnyezeti változót, mert a Docker CLI ezen keresztül keresi a rendszer-szintű Compose plugint. Ez célzott kompatibilitási kivétel: a production Compose- és alkalmazáskörnyezeti változók továbbra sem öröklődnek.

```powershell
cd C:\Munkalap-Step1
Set-ExecutionPolicy -Scope Process Bypass
.\test-release.ps1 -Suite all
```

Linuxon:

```sh
sh ./test-release.sh --suite all
```

Csak a forrás és a tervezett izoláció ellenőrzése, konténerindítás nélkül:

```powershell
.\test-release.ps1 -Plan
```

A `-Plan` eredménye **PLAN_ONLY**, nem sikeres teszt. A `-Suite unit` és `-Suite pg` részfuttatás; ezek nem váltják ki az `all` kört.

## 3. Mit futtat a teljes kör?

- A teljes meglévő backend pytest csomagot a release backend Python-környezetéből származó tesztimage-ben. Az API-tesztek továbbra is SQLite-ot használnak; ezt nem nevezzük PostgreSQL API-lefedettségnek.
- A backup-agent és runner unit/forrástesztjeit, az új tesztindító saját regresszióit, valamint a frontend és mobil Node unit tesztjeit. A backup unit tesztek a backend tesztkörnyezetében futnak; ez nem az agent/runner teljes runtime vagy fizikai restore tesztje.
- Valódi PostgreSQL 16-on üres adatbázis migrációját, és külön egy `0026_location_active_status` állapotról történő frissítést szintetikus tesztadatokkal.
- A provisioner/migráció ismételt futtatását, a commit külön kapcsolaton történő ellenőrzését, az MFA-oszlop és a kapcsolódó táblák létezését, a runtime DB-role jogait, a serial/identity sequence ownership regressziót és a régi tesztadatok megőrzését.
- A release backend és frontend tényleges indulását, belső readiness/HTML/verzió-proxy próbáját, majd újraindítás utáni ellenőrzését.

A DDL tiltásteszt kizárólag a PostgreSQL `42501` (insufficient privilege) kódját fogadja el. Szintaxishiba vagy hiányzó tábla nem jelenthet security PASS-t.

## 4. Eredmények és hibakezelés

Minden futás a `test-results/<ido>-<projekt>/` alá ír. A `report.json` tartalmazza a kért scope-ot, a forrásazonosítót, az image ID-kat, a tényleges parancsokat, kilépési kódokat és a szakaszonkénti logfájlokat. Az ideiglenes tesztjelszavakat a naplózó kitakarja.

`PASS_REQUESTED_SCOPE`: a kért kör parancsai sikeresek. `FAIL`: teszthiba. `BLOCKED`: előfeltétel/build/DB-indítás/migráció miatt nem zárható a kör. `BLOCKED_CLEANUP`: a tesztprojekt takarítása nem sikerült. A hibát nem alakítjuk sikeres eredménnyé; a folyamat nem nulla kilépési kódot ad.

A futás végén a teszt-DB megszűnik, a logok megmaradnak. Ha a Docker daemon futás közben elérhetetlenné válik, a takarítás sem garantálható; a riport rögzíti a saját projekt nevét. Ilyenkor ne használj globális Docker prune-t vagy az éles projektet törlő parancsot.

## 5. Ugyanazt az image-et használd, amelyet teszteltél

Csak teljes `--suite all` PASS után:

```powershell
py -3 .\scripts\promote_tested_images.py .\test-results\<futas>\report.json
```

A parancs nem indít szolgáltatást, nem módosít adatbázist. A már letesztelt image ID-khoz adja a verziós telepítési tageket, és `release-images.lock.json` fájlt ír. Hiányos/hibás riport vagy eltérő forrás/image esetén megtagadja a műveletet. A tesztriport nem kriptográfiailag hitelesített attestáció.

A már tesztelt image-ekből csak tudatos helyi/staging frissítési döntés után indíts alkalmazást. A meglévő helyi launcher neve kompatibilitás miatt maradt `start-v0.30.0-hotfix.ps1`; ilyenkor `-SkipBuild` szükséges. **Ezt ne a külön tesztkönyvtárból indítsd a működő telepítés helyett.** A helyi launcher a `munkalap` projektet kezeli, nem a tesztprojektet.

A production deploy most tesztelt-image lockot követel, és nem fordítja újra az alkalmazásimage-eket. A lockot a telepítés előtt és a konténereken utána is ellenőrzi. Ez **nem oldja fel** a biztonsági felülvizsgálat további NO-GO pontjait.

## 6. Szándékosan nem javított, további feladatok

A mostani kiadás nem módosítja az aláírásmentés üzleti logikáját, a PostgreSQL MFA/refresh/snapshot sorzárolását, a bizonyítéktár védelmét, a production secretek elérési modelljét, a bootstrap kulcsrotációs hibáját vagy a restore üzleti folyamatát. Ezek a következő lépések.

Nincs állítás Android-eszközös E2E-ről, teljes offline működésről, TLS/külső portvizsgálatról, fizikai backup/restore-ról, aktuális CVE-scanről vagy publikus production biztonságról.

A meglévő backend közvetett Python-függőségeit és alapimage-eit ez a lépés nem rögzíti új lockfájlba. A futás a tényleges Python-csomaglistát/image ID-kat rögzíti, és azok újraépítés nélküli használatát teszi lehetővé. A mobilhoz jelenleg nincs npm lock: annak Node unit tesztje nem npm/Android release-build.

A forrásba korábban beépített importadatok (például a HR import JSON) ebben a lépésben változatlanok. Az eredeti tesztek, illetve az alkalmazás indulása ezeket a **külön tesztkörnyezetben** beolvashatják. Ez nem anonimizált forráscsomag: az izoláció az éles adatbázis/secretek/runtime csatolását zárja ki. A csomagot és a tesztimage-eket ennek megfelelően belső anyagként kezeld.

## 7. Hivatkozások

A command és az entrypoint külön felülírási pont; a `compose run` alapból a szolgáltatás volume- és környezeti beállításait is átveszi. Ezért kell a külön tesztmodell, nem csak egy `ENVIRONMENT=development` felülírás.

- Docker Compose run: https://docs.docker.com/reference/cli/docker/compose/run/
- Compose build/image: https://docs.docker.com/reference/compose-file/build/
- Pytest invocation/exit status: https://docs.pytest.org/en/stable/reference/exit-codes.html

A felhasznált Docker-dokumentáció ellenőrzésének napja: 2026-09-11.

## 8. Windows acceptance follow-up hotfix

A teljes Windows acceptance a Compose-kornyezeti javitas utan vegigfutott a Docker/PostgreSQL eletcikluson, de ket unit stage hibas maradt. A backend ket bukasa elavult HTTP-statusz elvaras volt; az alkalmazas implementalt biztonsagi szerzodese valtozatlan maradt. A release-harness negy bukasa exit 126-tal jelentkezett, mert az entrypoint-teszt futas kozben letrehozott parancs-stubokat akart vegrehajtani ideiglenes runtime fajlrendszerrol.

A javitas a stubokat a tesztimage-be epiti be `/opt/release-entrypoint-test-bin` alatt, ezert a teszt nem igenyel irhato+vegrehajthato runtime mountot. A production kontenerek jogosultsagai, `cap_drop: ALL`, `no-new-privileges`, non-root uid/gid es az alkalmazas entrypointjai nem lazulnak.

A ket backend regresszios teszt most a tenyleges szerzodest ellenorzi: mobil refresh-token replay -> HTTP 401 + session revoke; mar felhasznalt MFA step-up TOTP egy ervenyes web sessionben -> HTTP 400.
