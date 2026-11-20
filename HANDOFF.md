# Strategic Training Library — Handoff Notes

**GitHub repo:** https://github.com/DatWins/positional_analysis  
**Live site:** https://datwins.github.io/positional_analysis/  
**Purpose:** 50 positional exercises per week, drawn from TWIC master games. Each week is split across five phases of a chess game. Players guess the plan, then study why it works.

**Related site:** TWIC Weekly Review → https://datwins.github.io/Chess_Weekly_Review/

---

## Site structure

```
positional_analysis/
├── index.html                        ← Training Library home (week grid)
├── validate_exercises.py             ← Stockfish validator script
├── README.md
└── issues/
    └── training/
        └── week1/
            ├── index.html            ← Week 1 — 50 exercises overview page
            ├── opening/              ← Phase 1: 10 exercises (ex01–ex10.html)
            ├── transition_mg/        ← Phase 2: 10 exercises
            ├── middlegame/           ← Phase 3: 10 exercises
            ├── transition_eg/        ← Phase 4: 10 exercises
            └── endgame/              ← Phase 5: 10 exercises
```

Each `ex01.html` through `ex10.html` is a **standalone self-contained exercise page** — no external JS libraries, just inline HTML/CSS/JS with an SVG chessboard.

---

## Five phases

| Folder | Phase label | Tag colour |
|---|---|---|
| `opening/` | Opening | Green |
| `transition_mg/` | → Middlegame | Blue |
| `middlegame/` | Middlegame | Blue |
| `transition_eg/` | → Endgame | Yellow |
| `endgame/` | Endgame | Red |

---

## index.html (training home) — how it works

Weeks are stored in a JavaScript array `WEEKS` near the bottom of the file:

```js
{
  num: 1,
  title: 'TWIC Master Games — Week 1',
  date: 'Oct 2026',
  href: 'issues/training/week1/index.html',
  total: 50,
  ready: 50,
  phases: ['o','tmg','m','teg','e']   // tag abbreviations for the colour pills
}
```

**To add Week 2:** create `issues/training/week2/` with the same structure as `week1/`, then add one entry to `WEEKS` in `index.html`.

### Progress tracking
Exercise completion is stored in `localStorage` as a JSON array of exercise numbers:
- Key: `w1done` for Week 1, `w2done` for Week 2, etc.
- Stored per browser origin — progress is **not shared** between this site and the old Chess_Weekly_Review URL.

---

## Exercise HTML pages (ex01–ex10.html)

Each exercise is self-contained with:
- Inline SVG chessboard (`const FEN = '...'`)
- Two or three plan choices (A, B, C) each with a `<span class="choice-plan">` label
- `const CORRECT = 'A'` (or B/C) declares the right answer
- Reveal button, next/prev navigation
- Sticky nav bar with links back up the hierarchy

### Nav bar link structure (from phase folder)
```
../../../../index.html          ← Strategic Training home
../index.html                   ← Week 1 overview
(next/prev) ex02.html etc.
```

### Nav bar link structure (from week1/index.html)
```
../../../index.html             ← Strategic Training home
```

**Nav brand text:** "Strategic Training" (links to `../../../../index.html` from phase, or `../../../index.html` from week overview)

---

## validate_exercises.py — the Stockfish validator

**Run from the repo root:**
```bash
python validate_exercises.py
# or with explicit Stockfish path:
python validate_exercises.py --stockfish "C:/path/to/stockfish.exe"
# FEN/syntax check only (no engine):
python validate_exercises.py --no-engine
```

**What it checks:**
1. Parses every exercise HTML to extract `FEN`, `CORRECT`, and the `<span class="choice-plan">` text
2. Runs Stockfish at depth 20 on each FEN
3. Parses the correct plan's text for a SAN move (e.g. `f4`, `Nd5!`)
4. Compares against engine top-3 moves

**Output codes:**
- `PASS` — plan matches engine top move
- `WARN` — plan matches engine top move with annotation differences
- `FAIL` — engine strongly disagrees (review manually)
- `NEEDS-REVIEW` — no parseable SAN found in plan text

**Requires:** `pip install python-chess` and Stockfish installed.  
On Windows, Stockfish default path: `C:/Program Files/Stockfish/stockfish.exe` (check the script top).

---

## Adding a new week — checklist

1. Create `issues/training/week2/` with subfolders: `opening/`, `transition_mg/`, `middlegame/`, `transition_eg/`, `endgame/`.
2. Add `ex01.html` through `ex10.html` in each subfolder (copy an existing one as a template, update FEN + plans + CORRECT + title).
3. Add `issues/training/week2/index.html` (copy `week1/index.html`, update links and title — `../../../index.html` is the training home from this depth).
4. In `index.html` (training home), add an entry to `WEEKS`.
5. Commit and push to `main`. GitHub Pages updates in ~1 minute.

---

## Git / deployment

- Branch: `main`
- GitHub Pages source: root of `main` — **must be enabled in repo Settings → Pages** (branch: main, folder: / root)
- No build system — push HTML directly
- Shallow clone is fine: `git clone --depth 1 https://github.com/DatWins/positional_analysis`

---

## History

This site was split out of `Chess_Weekly_Review` in November 2026. Previously the training exercises lived at `Chess_Weekly_Review/issues/training/` and the home page was `Chess_Weekly_Review/training.html`. After the split:
- `Chess_Weekly_Review` holds only the TWIC game library (`index.html`)
- `positional_analysis` holds the five-phase training library
