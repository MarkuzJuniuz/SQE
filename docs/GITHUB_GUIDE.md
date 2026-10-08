# Putting SQE on GitHub: steps, and what has to be in the repo

This is a practical checklist, not legal advice. I checked the licences and terms named below against their own pages (links in section 7); where something is my reading rather than a clear rule I say so. If real money, a company or a dispute ever gets involved, ask a lawyer.

---

## 1. The short version

1. **Free and non-commercial.** DCS's EULA requires anything built on it to stay freeware, and it names donations and crowdfunding. So: no Sponsors button, Patreon, Ko-fi or paid tier unless Eagle Dynamics approves in writing.
2. **Add a licence file.** Without one, GitHub's own docs say default copyright applies: nobody may legally use, copy or modify your code, even though it is public. **Decided: MIT**, copyright MarkuzJuniuz. The `LICENSE` file is already in the project, so you do not need to add it on GitHub (skip step 8's licence part and just `git pull` if you did add one).
3. **Ship the notices.** `THIRD_PARTY_NOTICES.md` and the README "Legal" section are already in the project. Keep them in the repo and inside every download.
4. **Never put DCS files in the repo** (no copy of `MissionScripting.lua`, no game screenshots you did not take of SQE itself, no textures/models/sounds).
5. **Fill in `AUTHOR` in `sqe/__init__.py`** before you publish. The EULA wants the creator named on mission material and the line "THIS MATERIAL IS NOT MADE OR SUPPORTED BY EAGLE DYNAMICS SA." SQE already writes that line into every briefing; `AUTHOR` adds your name or GitHub profile after "Created by".
6. **Do not commit your own data**: campaigns (`.sqe`), missions (`.miz`), settings. The `.gitignore` in the project covers them.
7. **Use GitHub's no-reply email** for commits so your real address is not in the history forever.

---

## 2. Choose the licence

| Licence | What it means for SQE | When to pick it |
|---|---|---|
| **MIT** (recommended) | Anyone may use, change and redistribute, including inside closed projects, as long as they keep your copyright and licence text. No warranty. | You want it used and do not care if someone forks it privately. |
| **Apache-2.0** | Same as MIT plus an explicit patent grant and a NOTICE mechanism. Longer text. | You want the patent language. |
| **GPL-3.0** | Anyone who distributes a modified SQE must release their source under GPL too. | You want forks to stay open. Works with the LGPL libraries SQE uses. |

Why none of these clash with the libraries: pydcs and PySide6 are LGPL-3.0 and SQE only *uses* them as separately installed packages. LGPL lets an app under any licence use them that way. What it asks of you is in section 4.

**Do not copy code from DCS Liberation or Retribution.** The Retribution repository's `LICENSE` file is LGPL-3.0 (I checked the file itself; I have not checked Liberation's). Code taken from it would have to stay under that licence with its notices, which is a constraint you do not want on an MIT project. SQE was written from scratch and only borrows ideas (the MissionScripting approach, the AI fuel setting, steerpoint order). Ideas are not protected; code is. You told me you pasted nothing from either project, and none of the SQE code was copied from them, so you are clear.

**How to add it (easy way):** after the first push, on the repo page choose *Add file > Create new file*, type `LICENSE` as the name, and GitHub shows a **Choose a license template** button. Pick MIT, put the year and your name (or handle), commit. That puts the standard text in place without you editing it.

A note on AI-assisted code: this project was written with Claude. You can still apply a licence and publish. The US Copyright Office's current position is that purely machine-generated parts may not be copyrightable without human authorship, while your design decisions, direction and edits are. In practice it does not stop you licensing the repo. It is just one more reason not to claim more than "SQE, by <you>".

---

## 3. What must be in the repository

| File | Status | Purpose |
|---|---|---|
| `LICENSE` | in the project (MIT) | Lets people legally use the code. |
| `THIRD_PARTY_NOTICES.md` | in the project | Licences of pydcs, PySide6, Pillow, PyInstaller, Natural Earth; the "not affiliated with Eagle Dynamics" statement; real unit names disclaimer. |
| `README.md` | in the project (Legal section added) | Says what SQE is, that it is free, not made or supported by Eagle Dynamics, and exactly what the MissionScripting option does. |
| `.gitignore` | in the project | Keeps saves, missions, settings, build output and caches out. |
| `requirements.txt` | in the project | Pins pydcs to the exact fork commit, so people get the F-14B(U) build. |
| `docs/` | in the project | Guide, changes, this file. |

**What must not be in it**
- Anything copied from the DCS install (`MissionScripting.lua`, Lua scripts, liveries, models, sounds, terrain files, the DCS manual).
- Other people's content you do not have the right to post (GitHub's terms make you responsible for that).
- Your `.sqe` saves, `SQE_state.json`, `settings.json`, `.miz` files, backups. They hold your paths and campaign.
- Passwords or tokens. There are none in SQE today; keep it that way.
- Donation links or a `.github/FUNDING.yml` (see section 1, point 1).

---

## 4. The Windows download (the .exe)

`build_exe.bat` makes `dist\SQE\` (a **folder**, not a single packed file). Keep it that way:

- The folder form keeps pydcs and PySide6 as separate files, which is what the LGPL asks for (users can replace them). A "one-file" exe hides them inside the exe and makes that harder to claim.
- The batch file now copies `LICENSE`, `THIRD_PARTY_NOTICES.md` and `README.md` into `dist\SQE\`. Check they are there before you zip it.
- Name the zip `SQE-v0.8.0-win64.zip`, attach it to a GitHub **Release** (not to the source tree).
- Put the SHA-256 in the release notes so people can verify it: `Get-FileHash .\SQE-v0.8.0-win64.zip` in PowerShell.
- Say plainly in the notes that Windows SmartScreen or an antivirus may warn about an unsigned app. This is common for PyInstaller builds; the source is in the repo so people can build it themselves.
- Pillow's and Qt's licence texts are inside their own package folders in the build, so they travel with it.

---

## 5. Step by step (Windows)

**A. One-time setup**
1. Create an account at github.com. Turn on two-factor sign-in (Settings > Password and authentication).
2. Settings > **Emails**: tick *Keep my email addresses private* and *Block command line pushes that expose my email*. Note the `ID+username@users.noreply.github.com` address shown there.
3. Install Git for Windows (git-scm.com). In PowerShell:

```powershell
git config --global user.name "Your Name or handle"
git config --global user.email "ID+username@users.noreply.github.com"
```

**B. Before the first commit**
4. In `sqe\__init__.py` set `AUTHOR = "Your name or github.com/yourhandle"`.
5. Check the project root has `.gitignore`, `THIRD_PARTY_NOTICES.md`, `README.md` and does **not** contain any `.sqe`, `.miz` or a copy of a DCS file. Run `python tools/smoke_test.py`: it must end with SMOKE TEST PASSED.

**C. Create the repo**
6. On github.com: **New repository**. Name it `squadron-campaign-engine` (avoid starting the name with "DCS"). Public. **Do not** tick "Add a README", ".gitignore" or "license" (you already have the first two and the licence is added in step 8). Create.
7. In PowerShell, from the project folder:

```powershell
git init -b main
git add .
git status          # read the list: no .sqe, .miz, settings, dist or build folders
git commit -m "SQE v0.8.0"
git remote add origin https://github.com/<yourhandle>/squadron-campaign-engine.git
git push -u origin main
```

   (GitHub Desktop does the same with *Add local repository > Publish*; it reads `.gitignore` too.)
8. Add the licence (section 2, "easy way"), then in PowerShell `git pull` to bring it down.

**D. Make it findable and safe**
9. Repo page > the gear next to *About*: add a description ("Lightweight dynamic campaign generator for DCS World: one flight, one package, low unit counts") and topics (`dcs-world`, `campaign`, `mission-generator`, `python`).
10. Settings > General: keep Issues on. Skip the Wiki. If you do not want sponsorship prompts, leave *Sponsorships* off.
11. **Releases > Draft a new release**: tag `v0.8.0`, title "SQE v0.8.0", paste the top entry of `docs/CHANGES.md`, attach `SQE-v0.8.0-win64.zip`, paste the SHA-256, publish.
12. Open the repo while signed out. Check: licence shown in the sidebar, README renders, no saves or personal paths anywhere (use the search box for your Windows user name).

---

## 6. Honest gray areas and risks

- **MissionScripting.lua.** DCS's EULA says you may not modify the Program without Eagle Dynamics' written consent (clause 3.1). SQE edits one local script on the user's own machine and puts it back, the same technique Liberation, Retribution and other community tools have used for years. I am not aware of ED acting against that, but I have not seen written permission either, so treat it as tolerated, not approved. What lowers the risk: it is the user's own choice, it is documented in the README, a backup is kept, it is restored on exit. A more conservative option is to ship with the setting **off by default** and a first-run prompt; say if you want that.
- **Multiplayer integrity checks.** A modified DCS script file can trip server integrity checks. SQE restores the file on exit; the README tells people to close SQE before multiplayer.
- **Tool vs missions.** The EULA's freeware and no-commercial wording is aimed at missions, campaigns and similar material made with DCS's own utilities. SQE is a separate third-party program, so no clause squarely covers it. Staying free and non-commercial is the conservative reading and the one I wrote this guide around.
- **Generated missions are "New Game Materials" under the EULA.** That means free to distribute, must say who made them and that they are not made by ED (SQE adds that line), and the EULA says ED owns such materials as derivative works. In practice this is the same footing as every community mission.
- **Real unit names** (VF-31, 77th FS and so on) are used as flavour. No insignia, no endorsement implied; the notices say so. If anyone with standing objected, renaming them is a small edit in `scenario.py`.
- **Trademarks.** "DCS World" and "Falcon BMS" appear only to say what SQE works with or resembles. Do not use ED's logos, and do not make a logo that looks like one.
- **Contributors.** GitHub's terms say contributions to a licensed public repo are licensed under that repo's licence ("inbound = outbound"), so you do not need a separate agreement for small pull requests. Do not merge code you suspect was copied from another project.
- **If Eagle Dynamics or anyone sends a takedown or complaint**, you can pause the repo (make it private) while you read it. Do not ignore it.

---

## 7. Sources I checked

- DCS End-User License Agreement (clauses 3.1 and 4.1): https://www.digitalcombatsimulator.com/en/support/license/
- GitHub, licensing a repository (no licence = default copyright): https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository
- GitHub Terms of Service (D.3 to D.6, "inbound = outbound"): https://docs.github.com/en/site-policy/github-terms/github-terms-of-service
- PySide6 licensing and what an app must do (LGPL-3.0, dynamic linking, ship the licence, source access to the library): https://www.pythonguis.com/faq/licensing-differences-between-pyqt6-and-pyside6/ and Qt for Python's licensing pages: https://doc.qt.io/qtforpython-6/commercial/index.html
- PyInstaller licence (built apps may carry any licence): https://pyinstaller.org/en/stable/license.html
- Natural Earth terms (public domain): https://www.naturalearthdata.com/about/terms-of-use/
- pydcs: the fork's own `LICENSE.txt` is LGPL-3.0; the pinned commit is in `requirements.txt`.
- Pillow's HPND licence and the US Copyright Office point are from general knowledge; I did not re-check them in this session, so confirm them if they matter to you.

## 8. Keeping it clean afterwards

- New library? Add it to `THIRD_PARTY_NOTICES.md` with its licence before you commit.
- Every release: version in `sqe/__init__.py`, entry in `docs/CHANGES.md`, smoke test, build, check the zip contains the licence files, tag.
- Never `git add -A` blindly; run `git status` first.


## Note: MissionScripting patch
SQE no longer edits DCS's `MissionScripting.lua` unless you agree. It asks on first run (default No); the choice lives in Settings. Without it the debrief cannot read results.
