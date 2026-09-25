# Munkalap-Eszköz App v0.23.0 – Beszerzés modul
## Codex implementációs specifikáció

**Kiinduló verzió:** `munkalap-eszkoz-app-v0.22.0`<br>
**Célverzió:** `v0.23.0`<br>
**Modul neve:** Beszerzés<br>
**Stack:** FastAPI + React + PostgreSQL + SQLAlchemy + Alembic + Docker Compose

---

# 1. Cél

A meglévő Munkalap-Eszköz alkalmazásba készüljön egy új **Beszerzés** modul, amelyben:

- bármely aktív, belépésre jogosult felhasználó létrehozhat beszerzési igényt;
- csak külön jogosultsággal rendelkező felhasználó hagyhatja jóvá vagy utasíthatja el az igényt;
- a kérelmező és a jóváhagyó szerepkör funkcionálisan váljon szét;
- a jóváhagyó áttekinthető listában lássa a korábbi és függő beszerzési igényeket;
- egy igényhez fájlok csatolhatók;
- kötelező legyen megadni a beszerzés tárgyát, célját, részletes leírását és összértékét;
- minden döntés és fontos állapotváltozás auditálható legyen.

A modul a meglévő alkalmazás jogosultsági, audit-, értesítési és fájltárolási mintáit használja.

---

# 2. Funkcionális alapelvek

## 2.1. Kérelmező

Minden aktív felhasználó, aki be tud jelentkezni az alkalmazásba, lehessen kérelmező.

Ehhez ne legyen szükség külön jóváhagyói jogosultságra.

A kérelmező:

- új beszerzési igényt hozhat létre;
- megtekintheti saját igényeit;
- megnyithatja saját igényeinek részleteit;
- letöltheti saját igényeinek csatolmányait;
- a még függőben lévő saját igényét visszavonhatja.

## 2.2. Jóváhagyó

Külön jogosultság:

```text
procurement.approve
```

Csak ezzel a jogosultsággal lehessen:

- az összes beszerzési igényt megtekinteni;
- függő igényt jóváhagyni;
- függő igényt elutasítani;
- korábbi igényeket listázni és keresni;
- más felhasználók igényeinek csatolmányait megtekinteni/letölteni.

## 2.3. Saját igény jóváhagyásának tiltása

A jóváhagyó **nem hagyhatja jóvá és nem utasíthatja el saját beszerzési igényét**.

Ez backend oldali üzleti szabály legyen, ne csak frontend tiltás.

Admin felhasználóra is vonatkozzon.

Hiba:

```http
403 Forbidden
```

Példa hibaüzenet:

```json
{
  "detail": "Saját beszerzési igény nem hagyható jóvá vagy utasítható el."
}
```

---

# 3. Jogosultságok

Javasolt új permission:

```text
procurement.approve
```

A modul használatához normál felhasználóknál ne legyen szükség külön `procurement.access` jogosultságra.

A Beszerzés modul minden aktív felhasználó számára jelenjen meg.

A jóváhagyási funkciók kizárólag `procurement.approve` jogosultsággal legyenek elérhetők.

A permission jelenjen meg:

```text
Admin → Felhasználók → Modulok és jogosultságok
```

felületen.

Az Admin szerepkör automatikusan rendelkezzen `procurement.approve` jogosultsággal, a meglévő alkalmazás admin-jogosultsági mintájához igazodva.

---

# 4. Beszerzési igény adatmezői

Egy beszerzési igény legalább az alábbi adatokat tartalmazza.

| Mező | Kötelező | Megjegyzés |
|---|---:|---|
| Tárgy | igen | Rövid megnevezés |
| Beszerzés célja | igen | Miért szükséges a beszerzés |
| Igény részletes leírása | igen | Nagy szövegbeviteli mező |
| Összérték | igen | Pozitív numerikus érték |
| Pénznem | igen | Alapértelmezett: HUF |
| Fájlok | nem | Több csatolmány támogatott |
| Kérelmező | automatikus | Bejelentkezett user |
| Beküldés időpontja | automatikus | Szerveridő |
| Státusz | automatikus | Kezdetben pending |
| Jóváhagyó | automatikus | Döntéskor |
| Jóváhagyói megjegyzés | opcionális / elutasításnál kötelező | Döntéskor |
| Döntés időpontja | automatikus | Jóváhagyás/elutasítás |

---

# 5. Beszerzési azonosító

Minden igény kapjon ember által olvasható egyedi azonosítót.

Formátum:

```text
BESZ-YYYY-NNNN
```

Példa:

```text
BESZ-2026-0001
BESZ-2026-0002
```

Követelmények:

- egyedi legyen;
- évente újraszámozható;
- adatbázis oldalon egyedi constraint legyen rajta;
- párhuzamos létrehozás esetén se keletkezhessen duplikáció.

---

# 6. Státuszmodell

Első verzióban az alábbi státuszok elegendők:

```text
pending
approved
rejected
withdrawn
```

Felhasználói megjelenítés:

| Backend érték | UI felirat |
|---|---|
| `pending` | Jóváhagyásra vár |
| `approved` | Jóváhagyva |
| `rejected` | Elutasítva |
| `withdrawn` | Visszavonva |

Engedélyezett állapotváltások:

```text
pending -> approved
pending -> rejected
pending -> withdrawn
```

Más állapotváltás ne legyen engedélyezett.

Jóváhagyott, elutasított vagy visszavont igényt ne lehessen törölni.

---

# 7. Adatbázismodell

Új Alembic migráció készüljön.

Javasolt migráció neve:

```text
0028_procurement
```

A tényleges sorszámot a repository aktuális Alembic head alapján kell meghatározni.

## 7.1. `procurement_requests`

Javasolt mezők:

```text
id
request_number

requester_user_id

subject
purpose
description

total_amount
currency

status

approved_by_user_id
approver_comment

submitted_at
decided_at

version
created_at
updated_at
```

### Típusok és constraint-ek

- `id`: bigint/int primary key a projekt meglévő mintája szerint
- `request_number`: varchar, unique, not null
- `requester_user_id`: FK users.id, not null
- `subject`: varchar, not null
- `purpose`: text/varchar, not null
- `description`: text, not null
- `total_amount`: `NUMERIC` / `DECIMAL`, not null
- `currency`: varchar(3), not null, default `HUF`
- `status`: enum vagy varchar a projekt meglévő mintája szerint, not null
- `approved_by_user_id`: nullable FK users.id
- `approver_comment`: text, nullable
- `submitted_at`: timestamp, not null
- `decided_at`: timestamp, nullable
- `version`: integer, not null, default 1
- `created_at`: timestamp
- `updated_at`: timestamp

### Összeg

Pénzügyi értéknél **tilos float/double típust használni**.

Javaslat:

```sql
NUMERIC(18, 2)
```

Validáció:

```text
total_amount > 0
```

---

# 8. Csatolmányok

Ne egyetlen fájlt, hanem több fájlt lehessen egy igényhez feltölteni.

Új tábla:

```text
procurement_attachments
```

Mezők:

```text
id
procurement_request_id

original_filename
storage_key
mime_type
size_bytes
sha256

uploaded_by_user_id
created_at
```

## 8.1. Engedélyezett fájltípusok

Első körben:

```text
.pdf
.docx
.xlsx
.csv
.jpg
.jpeg
.png
```

Ne legyen engedélyezett például:

```text
.exe
.bat
.cmd
.ps1
.js
.vbs
.dll
.scr
.com
.msi
.xlsm
.docm
```

## 8.2. Méretlimit

Maximum:

```text
25 MB / fájl
```

A limit backend oldalon is legyen kikényszerítve.

## 8.3. Tárolás

A meglévő runtime tárolási logikát kell használni.

Javasolt könyvtár:

```text
/app/runtime/procurement_attachments/
```

Példa:

```text
/app/runtime/procurement_attachments/2026/09/<uuid>.pdf
```

A tárolt fájlnév ne az eredeti fájlnév legyen.

Használjunk UUID vagy más collision-safe storage key-t.

Az eredeti fájlnév csak metaadatként kerüljön adatbázisba.

## 8.4. Biztonság

- path traversal ellen védeni kell;
- a kliens által küldött fájlnevet nem szabad fájlrendszer-pathként használni;
- MIME típust és kiterjesztést ellenőrizni kell;
- fájlok kizárólag autentikált endpointon keresztül tölthetők le;
- SHA-256 hash kerüljön eltárolásra.

---

# 9. Backend API

Új router javasolt:

```text
backend/app/routers/procurement.py
```

A projekt tényleges router struktúrájához kell igazítani.

## 9.1. Igény létrehozása

```http
POST /api/procurement/requests
```

Jogosultság:

```text
minden autentikált aktív user
```

Kötelező mezők:

```json
{
  "subject": "2 db notebook beszerzése",
  "purpose": "Új munkatársak munkaállomása",
  "description": "Minimum 16 GB RAM...",
  "total_amount": "864000.00",
  "currency": "HUF"
}
```

A kérelmezőt a backend a bejelentkezett user alapján töltse ki.

A kliens ne adhasson meg más requester_user_id-t.

---

## 9.2. Saját igények listázása

```http
GET /api/procurement/requests
```

Normál user csak saját igényeket lásson.

Javasolt szűrések:

```text
status
date_from
date_to
search
```

---

## 9.3. Igény részlete

```http
GET /api/procurement/requests/{id}
```

Hozzáférés:

- requester saját igényéhez;
- `procurement.approve` jogosultságú user bármelyikhez;
- Admin a meglévő projektjogosultsági modell szerint.

Más felhasználó:

```http
403 Forbidden
```

vagy a projekt meglévő objektumszintű hozzáférési mintája szerint `404`.

---

## 9.4. Igény módosítása

Ha szükséges:

```http
PATCH /api/procurement/requests/{id}
```

Csak:

- saját igény;
- `pending` státusz;
- döntés előtt.

Ha a projekt szempontjából egyszerűbb, az első verzióból a módosítás kihagyható, de létrehozás után legalább visszavonás legyen.

---

## 9.5. Visszavonás

```http
POST /api/procurement/requests/{id}/withdraw
```

Feltételek:

- csak requester;
- csak `pending`;
- más user nem vonhatja vissza;
- jóváhagyott/elutasított igény nem vonható vissza.

---

## 9.6. Csatolmány feltöltése

```http
POST /api/procurement/requests/{id}/attachments
```

Csak:

- requester saját `pending` igényéhez;
- szükség esetén Admin a meglévő admin-szabály szerint.

Több fájl támogatása szükséges.

---

## 9.7. Csatolmány letöltése

```http
GET /api/procurement/attachments/{id}/download
```

Hozzáférés:

- requester;
- procurement approver;
- Admin.

---

## 9.8. Jóváhagyói lista

```http
GET /api/procurement/approvals
```

Jogosultság:

```text
procurement.approve
```

Javasolt paraméterek:

```text
status
requester
date_from
date_to
search
page
page_size
sort
```

---

## 9.9. Jóváhagyás

```http
POST /api/procurement/requests/{id}/approve
```

Jogosultság:

```text
procurement.approve
```

Feltételek:

- status == pending
- requester_user_id != current_user.id
- optimista verzióellenőrzés
- tranzakciós biztonság

Request példa:

```json
{
  "comment": "Jóváhagyva.",
  "version": 3
}
```

---

## 9.10. Elutasítás

```http
POST /api/procurement/requests/{id}/reject
```

Jogosultság:

```text
procurement.approve
```

Elutasításnál a megjegyzés legyen kötelező.

Request:

```json
{
  "comment": "A keret jelenleg nem áll rendelkezésre.",
  "version": 3
}
```

---

# 10. Párhuzamos jóváhagyás és concurrency

A projekt HR moduljának meglévő concurrency mintáját kell újrahasznosítani.

A `procurement_requests` táblában legyen:

```text
version
```

mező.

Döntéskor:

- ellenőrizni kell a kliens által küldött version értéket;
- adatbázis tranzakcióban kell végrehajtani;
- szükség esetén row-level lock / SELECT FOR UPDATE használható.

Ha két jóváhagyó egyszerre próbál dönteni ugyanarról az igényről, csak az első legyen sikeres.

A második válasz:

```http
409 Conflict
```

Példa:

```json
{
  "detail": "A beszerzési igényt időközben már elbírálták."
}
```

---

# 11. Frontend

Új fő modul:

```text
Beszerzés
```

A meglévő modulnavigáció és vizuális rendszer mintáját kell használni.

Javasolt útvonalak:

```text
/procurement
/procurement/new
/procurement/requests/:id
/procurement/approvals
```

---

# 12. Saját beszerzési igények oldal

Útvonal:

```text
/procurement
```

Minden bejelentkezett user számára elérhető.

Táblázat:

| Azonosító | Tárgy | Összérték | Státusz | Beküldés | Jóváhagyó |
|---|---|---:|---|---|---|

Minimum funkciók:

- keresés;
- státuszszűrés;
- sor megnyitása;
- új beszerzési igény gomb.

A lista csak a bejelentkezett felhasználó saját igényeit mutassa.

---

# 13. Új beszerzési igény oldal

Útvonal:

```text
/procurement/new
```

Mezők:

## Tárgy

Egysoros input.

Kötelező.

## Beszerzés célja

Egysoros vagy közepes textarea.

Kötelező.

## Igény részletes leírása

Nagy textarea.

Kötelező.

Javasolt minimum UI magasság:

```text
8–12 sor
```

## Összérték

Numerikus pénzmező.

Kötelező.

Pozitív érték.

## Pénznem

Default:

```text
HUF
```

Első verzióban lehet csak HUF, de adatmodellben maradjon külön mező.

## Mellékletek

Drag & drop vagy normál file picker.

Több fájl kiválasztható.

Meg kell jeleníteni:

- fájlnév;
- méret;
- eltávolítás lehetőség beküldés előtt;
- hibajelzés tiltott fájlformátum vagy túlméret esetén.

## Beküldés

Gomb:

```text
Beszerzési igény beküldése
```

Siker után navigáció az igény részletező oldalára.

---

# 14. Jóváhagyói oldal

Útvonal:

```text
/procurement/approvals
```

Csak `procurement.approve` jogosultsággal.

Két logikai nézet:

```text
Jóváhagyásra vár
Korábbi igények
```

Lehet tab, szegmens vagy két külön blokk.

Minimum táblázati oszlopok:

| Azonosító | Kérelmező | Tárgy | Összeg | Státusz | Dátum |
|---|---|---|---:|---|---|

Kötelezően látszódjon:

- kérelmező neve;
- tárgy;
- összeg;
- státusz;
- beküldés dátuma.

Szűrések:

- szabad szöveges keresés;
- kérelmező;
- státusz;
- dátumtól;
- dátumig.

Alapértelmezett rendezés:

```text
pending előre
submitted_at DESC
```

---

# 15. Igény részletező oldal

Útvonal:

```text
/procurement/requests/:id
```

Megjelenítendő:

```text
Azonosító
Kérelmező
Tárgy
Beszerzés célja
Részletes leírás
Összérték
Pénznem
Beküldés dátuma
Státusz
Jóváhagyó
Döntés dátuma
Jóváhagyói megjegyzés
Csatolmányok
```

A csatolmányok legyenek letölthetők.

---

# 16. Jóváhagyási UI

Ha:

```text
current_user has procurement.approve
AND request.status == pending
AND request.requester_user_id != current_user.id
```

akkor jelenjen meg:

```text
Jóváhagyás
Elutasítás
```

gomb.

Jóváhagyói megjegyzés mező:

- jóváhagyásnál opcionális;
- elutasításnál kötelező.

A döntés előtt opcionálisan megjelenhet megerősítő dialog.

A frontend tiltás mellett a backend is minden szabályt ellenőrizzen.

---

# 17. Értesítések

A meglévő központi notification infrastruktúrát kell használni.

## Új igény

Új beszerzési igény létrehozásakor minden `procurement.approve` jogosultságú aktív felhasználó kapjon értesítést.

Példa:

```text
Új beszerzési igény
Minta Dolgozó – Notebook beszerzés – 480 000 Ft
```

Link:

```text
/procurement/requests/{id}
```

## Jóváhagyás

A requester kapjon értesítést.

Példa:

```text
Beszerzési igény jóváhagyva
BESZ-2026-0015 – Notebook beszerzés
```

## Elutasítás

A requester kapjon értesítést.

Példa:

```text
Beszerzési igény elutasítva
BESZ-2026-0015 – Notebook beszerzés
```

---

# 18. Audit napló

A meglévő audit infrastruktúrát kell használni.

Javasolt események:

```text
PROCUREMENT_REQUEST_CREATED
PROCUREMENT_REQUEST_UPDATED
PROCUREMENT_ATTACHMENT_UPLOADED
PROCUREMENT_ATTACHMENT_DOWNLOADED
PROCUREMENT_REQUEST_WITHDRAWN
PROCUREMENT_REQUEST_APPROVED
PROCUREMENT_REQUEST_REJECTED
```

Auditban legalább:

```text
request_id
request_number
requester_user_id
acting_user_id
previous_status
new_status
amount
currency
timestamp
correlation/request id
```

Döntésnél tárolni kell a jóváhagyó user ID-ját és a megjegyzést.

---

# 19. Menürendszer

A Beszerzés modul navigációja:

```text
Beszerzési igényeim
Új beszerzési igény
Jóváhagyások
```

`Jóváhagyások` csak akkor jelenjen meg, ha:

```text
hasPermission("procurement.approve")
```

A backend endpoint ugyanettől függetlenül is végezze el a jogosultság-ellenőrzést.

---

# 20. Validáció

## Tárgy

- trim után nem lehet üres;
- javasolt max. 255 karakter.

## Cél

- trim után nem lehet üres.

## Leírás

- trim után nem lehet üres.

## Összeg

- kötelező;
- `> 0`;
- DECIMAL-ként kezelendő.

## Pénznem

- ISO 4217-szerű 3 karakter;
- első verzió default `HUF`.

## Elutasítás

Elutasításkor:

```text
approver_comment required
```

---

# 21. Biztonsági követelmények

A frontend soha ne legyen az egyetlen védelmi réteg.

Backend oldalon kötelező:

- autentikáció;
- objektumszintű hozzáférés;
- permission ellenőrzés;
- requester ownership ellenőrzés;
- saját igény jóváhagyásának tiltása;
- fájl-hozzáférés ellenőrzése;
- path traversal elleni védelem;
- fájlméret limit;
- engedélyezett kiterjesztések/MIME;
- concurrency védelem;
- DB tranzakció a döntéseknél.

---

# 22. Backup

A csatolmányok a meglévő:

```text
/app/runtime
```

volume alá kerüljenek.

A jelenlegi backup-agent runtime mentési logikájába illeszkedjenek.

Ne készüljön külön új backup-mechanizmus, ha a meglévő runtime könyvtár rekurzívan mentésre kerül.

A release teszt során ellenőrizni kell, hogy a procurement attachment fájlok MASTER backupból visszaállíthatók.

---

# 23. Backend tesztek

Minimum automata tesztek:

## Jogosultság

1. normál user létrehozhat igényt;
2. normál user saját igényeit látja;
3. normál user más igényét nem látja;
4. normál user nem hívhat approve endpointot;
5. approver látja az összes igényt;
6. approver jóváhagyhat más user által létrehozott pending igényt;
7. approver nem hagyhatja jóvá saját igényét;
8. approver nem utasíthatja el saját igényét.

## Állapot

9. pending -> approved működik;
10. pending -> rejected működik;
11. pending -> withdrawn működik;
12. approved nem hagyható újra jóvá;
13. rejected nem hagyható jóvá;
14. withdrawn nem hagyható jóvá.

## Validáció

15. üres subject -> 422;
16. üres purpose -> 422;
17. üres description -> 422;
18. 0 vagy negatív total_amount -> 422;
19. reject komment nélkül -> 422 vagy domain validation error.

## Concurrency

20. két párhuzamos approve közül csak az egyik sikeres;
21. második kérés 409 Conflict.

## Fájl

22. engedélyezett PDF feltöltése működik;
23. tiltott `.exe` feltöltése elutasítva;
24. 25 MB feletti fájl elutasítva;
25. idegen user nem töltheti le más igényének fájlját;
26. approver letöltheti az igény csatolmányát.

---

# 24. Frontend QA

Minimum ellenőrzések:

- Beszerzés modul minden aktív usernél látszik;
- normál usernél nincs Jóváhagyások menüpont;
- approvernél van Jóváhagyások menüpont;
- új igény űrlap validáció működik;
- több fájl kiválasztható;
- 25 MB feletti fájl UI-ban is hibát ad;
- beküldés után az igény megjelenik a saját listában;
- approver listában látszik a kérelmező, tárgy és összeg;
- jóváhagyás után státusz frissül;
- elutasítás komment nélkül nem küldhető el;
- requester értesítést kap;
- approver saját igényén nem jelenik meg döntési lehetőség;
- mobil/desktop layout nem törik.

---

# 25. Acceptance criteria

A fejlesztés akkor tekinthető késznek, ha az alábbiak mind teljesülnek.

## AC-01

Minden aktív, bejelentkezett felhasználó létre tud hozni beszerzési igényt.

## AC-02

A következő mezők kötelezőek:

```text
Tárgy
Beszerzés célja
Részletes leírás
Összérték
```

## AC-03

Egy igényhez több fájl csatolható.

## AC-04

Fájlonként maximum 25 MB engedélyezett.

## AC-05

Minden igény automatikus `BESZ-YYYY-NNNN` azonosítót kap.

## AC-06

Normál user csak saját igényeit látja.

## AC-07

`procurement.approve` jogosultságú user látja az összes beszerzési igényt.

## AC-08

A jóváhagyói listában minimum látszik:

```text
kérelmező
tárgy
összeg
státusz
dátum
```

## AC-09

Csak `procurement.approve` jogosultságú user hagyhat jóvá vagy utasíthat el.

## AC-10

Saját igényt senki nem hagyhat jóvá vagy utasíthat el.

## AC-11

Elutasításkor kötelező a jóváhagyói megjegyzés.

## AC-12

Függő saját igény visszavonható.

## AC-13

Jóváhagyott, elutasított vagy visszavont igény nem törölhető.

## AC-14

Minden fontos művelet auditnaplóba kerül.

## AC-15

Új igénynél a jóváhagyók értesítést kapnak.

## AC-16

Jóváhagyás/elutasítás esetén a kérelmező értesítést kap.

## AC-17

Párhuzamos jóváhagyási kísérlet nem okozhat kettős döntést.

## AC-18

A csatolmányok bekerülnek a meglévő runtime backupba.

## AC-19

A migráció tiszta adatbázison és meglévő v0.22.0 adatbázison is lefut.

## AC-20

A meglévő modulok működése nem regresszál.

---

# 26. Nem része a v0.23.0 scope-nak

Első körben ne kerüljön bele:

- többszintű jóváhagyás;
- összegfüggő jóváhagyási lánc;
- költséghely;
- budget / keretkezelés;
- szállító törzs;
- PO / megrendelésszám;
- számlaillesztés;
- ERP integráció;
- automatikus beszerzési rendelés generálás;
- beszerzési kategóriák;
- projektkód;
- havi/éves költségkeret.

Az adatmodellt viszont úgy kell kialakítani, hogy ezek később hozzáadhatók legyenek nagy újratervezés nélkül.

---

# 27. Javasolt implementációs sorrend

1. Repository és meglévő HR/jogosultsági/audit/notification minták feltérképezése.
2. Permission modell bővítése `procurement.approve` jogosultsággal.
3. SQLAlchemy modellek.
4. Alembic migráció.
5. Pydantic request/response sémák.
6. Backend service/domain logika.
7. API router.
8. Csatolmánykezelés.
9. Audit események.
10. Notification integráció.
11. Frontend routing.
12. Saját igények lista.
13. Új igény űrlap.
14. Igény részletező oldal.
15. Jóváhagyói lista.
16. Approve/reject UI.
17. Backend automata tesztek.
18. Frontend/build ellenőrzés.
19. Docker Compose build és smoke test.
20. Verziófrissítés és CHANGELOG.

---

# 28. Verziózás

A funkció elkészülte után:

```text
v0.22.0 -> v0.23.0
```

Frissítendő legalább:

- alkalmazás verzió;
- `CHANGELOG.md`;
- README, ha a projekt ott vezeti a modulokat;
- release/handoff dokumentáció, ha van.

Javasolt changelog bejegyzés:

```markdown
## v0.23.0

### Added
- Új Beszerzés modul.
- Beszerzési igény létrehozása minden aktív felhasználónak.
- Külön `procurement.approve` jogosultság.
- Jóváhagyási és elutasítási workflow.
- Több csatolmány kezelése, maximum 25 MB/fájl.
- Saját igény visszavonása.
- Jóváhagyói előzménylista és keresés.
- Audit- és értesítési integráció.
- Optimista concurrency védelem jóváhagyási műveleteknél.
```

---

# 29. Codex végrehajtási utasítás

A fejlesztést a meglévő v0.22.0 kódbázis mintáihoz igazítva végezd el.

**Ne hozz létre párhuzamos vagy új jogosultsági rendszert**, ha a projektben már van használható permission mechanizmus.

**Ne hozz létre külön audit rendszert**, hanem a meglévőt használd.

**Ne hozz létre külön notification rendszert**, hanem a meglévőt használd.

**A HR modul jóváhagyási és concurrency mintáját vizsgáld meg először**, és ahol ésszerű, ugyanazt a megközelítést használd.

Minden hozzáférési és üzleti szabály backend oldalon is legyen kikényszerítve.

A fejlesztés végén:

1. futtasd a backend teszteket;
2. futtasd a frontend buildet;
3. futtasd az Alembic migrációt;
4. ellenőrizd az aktuális Alembic head-et;
5. építsd újra a Docker image-eket;
6. futtasd a projekt meglévő smoke/acceptance tesztjeit, ha vannak;
7. ellenőrizd, hogy a v0.22.0 meglévő funkciók nem regresszáltak;
8. frissítsd a verziót `v0.23.0`-ra;
9. frissítsd a `CHANGELOG.md`-t;
10. a végén készíts rövid implementációs összefoglalót a módosított fájlokról, migrációról, teszteredményekről és az esetleges fennmaradó korlátozásokról.

**Ne állj meg pusztán terv készítésénél: implementáld a teljes modult a kódbázisban.**
