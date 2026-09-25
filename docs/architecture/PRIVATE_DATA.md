# Privát adatforrások

A 2026-09-25-i Git-bevezetés során három helyi JSON fájlt különítettünk el a forráskódtól:

| Fájl a jelenlegi helyi példányban | Tartalom | Futás közbeni név |
|---|---|---|
| `backend/app/data/company_profiles.json` | céges és kapcsolattartói adatok | `company_profiles.json` |
| `backend/app/data/customer_assets_20260616.json` | ügyfél-, helyszín-, kapcsolattartó- és eszközadatok | `customer_assets_20260616.json` |
| `backend/app/data/hr_leave_2026_rlb.json` | munkavállalói és távolléti adatok | `hr_leave_2026_rlb.json` |

Ezek a fájlok helyben megmaradnak, de a `.gitignore` és a `.dockerignore` kizárja őket. Ne másold őket commitba, release ZIP-be, konténerképbe, hibajegybe vagy chatüzenetbe.

A korábbi `release-source-manifest.json` még a régi, privát adatot is tartalmazó kiadási állapothoz tartozik. Helyben megmarad, de a Git kizárja, és az új forrásellenőrzés már elutasítja a privát adatfájlok felvételét egy új manifestbe. Az aktuális módosításokhoz külön, ellenőrzött release manifest és acceptance futás kell; a régi manifest nem igazolja az új forrást.

## Betöltési sorrend

Az alkalmazás először a `RUNTIME_DIR` könyvtárban keresi az azonos nevű fájlt, és csak ezután a korábbi `backend/app/data/` helyen. A Compose alapértelmezett futási könyvtára az `app_runtime` volume alatt `/app/runtime`. A friss Docker-kép már nem tartalmazza a privát JSON fájlokat; konténeres futtatáshoz a jóváhagyott adatokat a volume-ba kell elhelyezni, megfelelő hozzáféréssel, még az indítás vagy frissítés előtt.

Ha az ügyfél/eszköz forrás hiányzik, a fejlesztői seed kihagyja azt, az import státusza nulla forrássort jelez, és az admin által indított kézi import 409 választ ad. Ha a HR-forrás hiányzik, nincs automatikus HR-import; az admin kézi párosítás 409 választ ad. Cégprofil nélkül a cégprofil-lista üres; nyomtatás és mentés előtt valós céges konfiguráció szükséges. A hiányzó adatforrást nem pótolja fiktív production adattal a rendszer.

## Fejlesztés és teszt

A `backend/tests/fixtures/` három szintetikus JSON fájlt tartalmaz. Az automatizált tesztek ezeket használják, és nem olvassák a helyi valós adatokat. Ha külön fejlesztői példányban a funkciókat kézzel szeretnéd kipróbálni, a mintákból a privát célútvonalra készíthetsz helyi másolatot; production környezetbe a minták nem valók.

Az éles adatok átadását, jogosultságait és visszaállíthatóságát külön üzemeltetési folyamatban kell jóváhagyni. Production frissítés előtt ellenőrizni kell, hogy az `app_runtime` volume tartalmazza a szükséges fájlokat, és az alkalmazás `10001:10001` felhasználója olvasni tudja őket. Ez a forráskód-beállítás nem telepít vagy migrál valós adatokat.
