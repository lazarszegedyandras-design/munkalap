# Döntés: privát induló adatok a forráskódon kívül

Dátum: 2026-09-25

## Helyzet

A korábbi forrásfa három JSON fájlja valós vállalati kapcsolattartói, ügyfél/eszköz- és HR-adatokat tartalmaz. A backend egyes importfolyamatai és tesztjei közvetlenül ezekre támaszkodtak. Az első Git-mentés és az új konténerkép így adatokat terjesztene.

## Döntés

- A három fájl helyben megmarad, de a Git, a Docker build context és az új release manifest kizárja őket.
- Futás közben az alkalmazás először a `RUNTIME_DIR` alatt keresi a jóváhagyott privát fájlokat. A meglévő helyi statikus útvonal kompatibilitási tartalék.
- Hiányzó adatforrás esetén a fejlesztői seed kihagyja a privát importot; az admin által indított import egyértelmű hibát ad. A tesztek szintetikus fixture-öket használnak.
- A cégkódhoz kötött konkrét munkalapi telefon és email kikerült a forráskódból. Ha egy régi cégprofil nem tartalmaz külön munkalapi elérhetőséget, az általános profil-elérhetőség érvényesül.

## Következmények

- Tiszta checkoutból a privát importadatok nem állnak rendelkezésre. Ez szándékos. Production futtatás előtt a szükséges fájlokat külön, ellenőrzött üzemeltetési lépésben kell a futási volume-ba telepíteni.
- A korábbi release manifest az új forráshoz nem használható; új, privát fájlokat kizáró manifest és teljes acceptance futás szükséges.
- A meglévő helyi JSON fájlok nem törlődtek vagy módosultak. Az automatikus tesztek a valós adatokat nem igénylik.
