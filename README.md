# Strategic Training Library

Positional training exercises drawn from TWIC master games, split into five phases:
opening plans, transition to middlegame, middlegame plans, transition to endgame, and basic endgame technique.

- `index.html`: the library page with the weekly sets.
- `issues/training/week1/`: Week 1 index plus 50 exercises (10 per phase).
- `validate_exercises.py`: checks each exercise's correct plan against Stockfish. Run `pip install python-chess`, then `python validate_exercises.py --stockfish "C:/path/to/stockfish.exe"`, or `--no-engine` for a syntax-only check.

The weekly TWIC review lives at https://datwins.github.io/Chess_Weekly_Review/.

## Adding a new week

Create `issues/training/weekN/` with the same phase folders, then add an entry to the `WEEKS` list in `index.html`.
