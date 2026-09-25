# Helyi fejlesztési munkafolyamat

1. A projektbeszélgetésben elfogadott követelményt írd le a `docs/features/` mappában. A tartós technikai döntés a `docs/decisions/` mappába kerüljön.
2. A munka kezdetén ellenőrizd a Git állapotát. A `main`/`master` ágon ne módosíts; feladatonként külön branch vagy worktree használatos.
3. A VS Code-ban futó Codex olvassa el az `AGENTS.md`, `CURRENT_STATUS.md` és az érintett specifikációt. A meglévő helyi módosításokat őrizze meg.
4. A megvalósítás után fusson a releváns teszt, majd `git diff` és `git status` ellenőrzés. A teljes release teszt folyamatát a `STEP1_TEST_BASELINE_v0.30.1.md` írja le.
5. A `CURRENT_STATUS.md` tartalmazza az eredményt és a nyitott kérdéseket. Commit, push, merge és telepítés csak külön felhasználói utasításra történjen.

Helyi Git-hook önmagában nem tudja megakadályozni egy branch munkafájljainak szerkesztését; a `main` tényleges védelmét a külön munkaág és egy későbbi távoli tárhelyen beállított branch protection adja. Távoli tárhely még nem került felmérésre.
