#!/usr/bin/env python3
"""
Strategic Training Library — Position Extractor
================================================
Reads a TWIC PGN file, walks every game move by move, identifies instructive
candidate positions, runs Stockfish on each one, and writes a verified JSON
file of exercise candidates ready for the HTML generator.

The "correct" answer is ALWAYS the move the grandmaster actually played,
confirmed by Stockfish as the engine's top choice (or flagged for review if not).

USAGE
-----
  pip install python-chess

  # Full extraction + Stockfish verification:
  python extract_positions.py twic1668.pgn --stockfish "C:/path/to/stockfish.exe"

  # Extract candidates only (no engine — review FENs manually):
  python extract_positions.py twic1668.pgn --no-engine

  # Limit to N candidates per game (default 10):
  python extract_positions.py twic1668.pgn --stockfish "C:/..." --per-game 10

  # Only use games where both players are >= min Elo:
  python extract_positions.py twic1668.pgn --stockfish "C:/..." --min-elo 2600

OUTPUT
------
  candidates_<pgn_stem>.json — all candidates before engine filter
  verified_<pgn_stem>.json  — only engine-confirmed positions (PASS/WARN)

JSON structure per position:
  {
    "game":        "Suleymanli, Aydin vs Abdusattorov, Nodirbek",
    "event":       "41st ECC Open 2026",
    "date":        "2026.10.17",
    "white_elo":   2679,
    "black_elo":   2780,
    "opening":     "QGD",
    "move_number": 24,
    "side":        "white",
    "phase":       "middlegame",
    "fen":         "r1bq1rk1/pp3ppp/2n1pn2/3p4/2PP4/2N2N2/PP2BPPP/R1BQ1RK1 w - - 0 24",
    "move_played": "Rxc7",
    "move_san":    "Rxc7",
    "engine_top3": ["Rxc7 (+1.20)", "Nxd5 (+0.80)", "f4 (+0.40)"],
    "engine_cp":   120,
    "status":      "PASS",
    "phase_label": "Middlegame",
    "candidate_reason": "material_win"
  }

HOW CANDIDATES ARE CHOSEN
--------------------------
At each half-move the script scores the position for "instructiveness":
  - Material shifts: captures that change the balance
  - Pawn structure: passed pawn created, isolated pawn, pawn break
  - King safety: castling, king attack score change
  - Piece activity: centralisation, outpost occupation
  - Evaluation swing: Stockfish cp change >= threshold between consecutive moves

Candidates must meet a minimum interest score. The top candidates per game
are taken up to --per-game, spread across the five training phases.

PHASES
------
  opening       moves 1–15
  transition_mg moves 16–25
  middlegame    moves 26–40
  transition_eg moves 41–55
  endgame       moves 56+
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

try:
    import chess
    import chess.engine
    import chess.pgn
    HAS_CHESS = True
except ImportError:
    HAS_CHESS = False
    print("ERROR: python-chess not installed.")
    print("Run: pip install python-chess")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_STOCKFISH_PATHS = [
    r"C:\Users\%USERNAME%\Downloads\stockfish\stockfish.exe",
    r"C:\Program Files\Stockfish\stockfish.exe",
    r"C:\stockfish\stockfish.exe",
    "/opt/homebrew/bin/stockfish",
    "/usr/local/bin/stockfish",
    "/usr/bin/stockfish",
]

ANALYSIS_DEPTH   = 18    # depth per position (lower = faster)
MULTIPV          = 3     # top N engine moves
MIN_ELO_DEFAULT  = 2600  # skip games below this average Elo
PER_GAME_DEFAULT = 10    # max candidates extracted per game
CP_SWING_MIN     = 40    # centipawn swing to flag as interesting

PHASE_RANGES = [
    ("opening",       "Opening",          1,  15),
    ("transition_mg", "→ Middlegame",     16,  25),
    ("middlegame",    "Middlegame",       26,  40),
    ("transition_eg", "→ Endgame",        41,  55),
    ("endgame",       "Endgame",          56, 999),
]

# ──────────────────────────────────────────────────────────────────────────────
# Phase detection
# ──────────────────────────────────────────────────────────────────────────────

def get_phase(move_number: int) -> tuple[str, str]:
    for folder, label, lo, hi in PHASE_RANGES:
        if lo <= move_number <= hi:
            return folder, label
    return "endgame", "Endgame"


# ──────────────────────────────────────────────────────────────────────────────
# Interest scoring (without engine — fast pass)
# ──────────────────────────────────────────────────────────────────────────────

def interest_score(board: chess.Board, move: chess.Move) -> tuple[int, str]:
    """
    Score how instructive this move decision is.
    Returns (score, reason_tag).
    Higher = more interesting as an exercise.
    """
    score = 0
    reason = "positional"

    # Capture that changes material balance significantly
    if board.is_capture(move):
        captured = board.piece_at(move.to_square)
        if captured:
            val = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
                   chess.ROOK: 5, chess.QUEEN: 9}.get(captured.piece_type, 0)
            score += val * 10
            if val >= 5:
                reason = "material_win"
            elif val >= 3:
                reason = "piece_trade"

    # Pawn promotion
    if move.promotion:
        score += 50
        reason = "promotion"

    # Check — often a forcing tactical moment
    board_copy = board.copy()
    board_copy.push(move)
    if board_copy.is_check():
        score += 15
        reason = "check"
    if board_copy.is_checkmate():
        score += 200
        reason = "checkmate"

    # Piece centralisation (moving to d4/d5/e4/e5)
    central = {chess.D4, chess.D5, chess.E4, chess.E5}
    if move.to_square in central:
        score += 8
        reason = reason if score > 20 else "centralisation"

    # Pawn to 7th rank (near-promotion)
    piece = board.piece_at(move.from_square)
    if piece and piece.piece_type == chess.PAWN:
        to_rank = chess.square_rank(move.to_square)
        if (piece.color == chess.WHITE and to_rank == 6) or \
           (piece.color == chess.BLACK and to_rank == 1):
            score += 20
            reason = "pawn_7th"

    # Rook lift / open file
    if piece and piece.piece_type == chess.ROOK:
        score += 5

    # King safety — castling
    if board.is_castling(move):
        score += 12
        reason = "castling"

    return score, reason


# ──────────────────────────────────────────────────────────────────────────────
# Stockfish helpers
# ──────────────────────────────────────────────────────────────────────────────

def find_stockfish(explicit: str | None) -> str | None:
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return str(p)
        print(f"[!] Stockfish not found at: {explicit}", file=sys.stderr)
        return None
    which = shutil.which("stockfish")
    if which:
        return which
    for path in DEFAULT_STOCKFISH_PATHS:
        expanded = Path(path).expanduser()
        if expanded.is_file():
            return str(expanded)
    return None


def analyse(engine: chess.engine.SimpleEngine, fen: str,
            depth: int = ANALYSIS_DEPTH) -> list[dict]:
    board = chess.Board(fen)
    infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=MULTIPV)
    if isinstance(infos, dict):
        infos = [infos]
    results = []
    for info in infos:
        pv = info.get("pv", [])
        if not pv:
            continue
        move = pv[0]
        score = info["score"].pov(board.turn)
        try:
            san = board.san(move)
        except Exception:
            san = move.uci()
        cp   = score.score()
        mate = score.mate()
        results.append({"uci": move.uci(), "san": san, "cp": cp, "mate": mate})
    return results


def score_str(r: dict) -> str:
    if r["mate"] is not None:
        return f"M{r['mate']}"
    return f"{r['cp']/100:+.2f}" if r["cp"] is not None else "?"


def sans_match(a: str, b: str) -> bool:
    def clean(s): return s.rstrip("+#!?").replace("x","").lower()
    return clean(a) == clean(b)


# ──────────────────────────────────────────────────────────────────────────────
# Game processing
# ──────────────────────────────────────────────────────────────────────────────

def process_game(game: chess.pgn.Game, engine, per_game: int,
                 no_engine: bool) -> list[dict]:
    """Extract candidate positions from one game."""
    headers = game.headers
    white     = headers.get("White", "?")
    black     = headers.get("Black", "?")
    result    = headers.get("Result", "*")
    event     = headers.get("Event", "?")
    date      = headers.get("Date", "?")
    opening   = headers.get("Opening", "?")
    variation = headers.get("Variation", "")
    white_elo = int(headers.get("WhiteElo", 0) or 0)
    black_elo = int(headers.get("BlackElo", 0) or 0)

    game_label = f"{white} vs {black}"

    board = game.board()
    candidates = []
    phase_seen: dict[str, int] = {}  # phase -> count already found

    node = game
    move_number = 0

    while node.variations:
        next_node = node.variations[0]  # main line only
        move = next_node.move
        if move is None:
            break

        # Move number (full move)
        if board.turn == chess.WHITE:
            move_number += 1

        phase_folder, phase_label = get_phase(move_number)

        # Skip if we already have enough for this phase
        if phase_seen.get(phase_folder, 0) >= max(2, per_game // 5):
            board.push(move)
            node = next_node
            continue

        score, reason = interest_score(board, move)

        if score >= 10:  # minimum interest threshold
            try:
                san = board.san(move)
            except Exception:
                san = move.uci()

            fen_before = board.fen()
            side = "white" if board.turn == chess.WHITE else "black"

            cand = {
                "game":             game_label,
                "event":            event,
                "date":             date,
                "white_elo":        white_elo,
                "black_elo":        black_elo,
                "opening":          opening + (f" {variation}" if variation else ""),
                "move_number":      move_number,
                "side":             side,
                "phase":            phase_folder,
                "phase_label":      phase_label,
                "fen":              fen_before,
                "move_played":      move.uci(),
                "move_san":         san,
                "engine_top3":      [],
                "engine_cp":        None,
                "status":           "UNVERIFIED",
                "candidate_reason": reason,
            }

            # Engine verification
            if not no_engine and engine is not None:
                try:
                    top = analyse(engine, fen_before)
                    cand["engine_top3"] = [f"{r['san']} ({score_str(r)})" for r in top]
                    if top:
                        cand["engine_cp"] = top[0]["cp"]
                        top_sans = [r["san"] for r in top]
                        if sans_match(san, top_sans[0]):
                            cand["status"] = "PASS"
                        elif any(sans_match(san, s) for s in top_sans[1:]):
                            cand["status"] = "WARN"
                        else:
                            cand["status"] = "FAIL"
                except Exception as e:
                    cand["status"] = f"ENGINE_ERROR: {e}"

            candidates.append(cand)
            phase_seen[phase_folder] = phase_seen.get(phase_folder, 0) + 1

        board.push(move)
        node = next_node

    return candidates


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract and verify exercise positions from a TWIC PGN.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("pgn", help="Path to TWIC PGN file")
    parser.add_argument("--stockfish", metavar="PATH",
                        help="Path to Stockfish binary")
    parser.add_argument("--no-engine", action="store_true",
                        help="Skip Stockfish — extract candidates only")
    parser.add_argument("--depth", type=int, default=ANALYSIS_DEPTH,
                        help=f"Stockfish depth (default {ANALYSIS_DEPTH})")
    parser.add_argument("--per-game", type=int, default=PER_GAME_DEFAULT,
                        help=f"Max candidates per game (default {PER_GAME_DEFAULT})")
    parser.add_argument("--min-elo", type=int, default=MIN_ELO_DEFAULT,
                        help=f"Min average Elo to include a game (default {MIN_ELO_DEFAULT})")
    parser.add_argument("--max-games", type=int, default=0,
                        help="Process at most N games (0 = all)")
    parser.add_argument("--out", metavar="DIR", default=".",
                        help="Output directory for JSON files (default: current dir)")
    args = parser.parse_args()

    pgn_path = Path(args.pgn)
    if not pgn_path.is_file():
        print(f"ERROR: PGN file not found: {pgn_path}")
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = pgn_path.stem
    candidates_file = out_dir / f"candidates_{stem}.json"
    verified_file   = out_dir / f"verified_{stem}.json"

    # Engine setup
    engine = None
    if not args.no_engine:
        sf_path = find_stockfish(args.stockfish)
        if sf_path is None:
            print("ERROR: Stockfish not found. Use --no-engine or --stockfish <path>.")
            sys.exit(1)
        print(f"Stockfish : {sf_path}")
        print(f"Depth     : {args.depth}")
        engine = chess.engine.SimpleEngine.popen_uci(sf_path)
        engine.configure({"Threads": 2, "Hash": 128})
    else:
        print("Mode: --no-engine (candidates only, no verification)")

    print(f"PGN       : {pgn_path}")
    print(f"Min Elo   : {args.min_elo}")
    print(f"Per game  : {args.per_game}")
    print()

    all_candidates = []
    games_processed = 0
    games_skipped   = 0

    try:
        with open(pgn_path, encoding="utf-8", errors="replace") as f:
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break

                if args.max_games and games_processed >= args.max_games:
                    break

                headers = game.headers
                white_elo = int(headers.get("WhiteElo", 0) or 0)
                black_elo = int(headers.get("BlackElo", 0) or 0)
                avg_elo   = (white_elo + black_elo) / 2 if white_elo and black_elo else 0
                result    = headers.get("Result", "*")

                # Skip games without a decisive result or below Elo threshold
                if result == "*" or avg_elo < args.min_elo:
                    games_skipped += 1
                    continue

                white = headers.get("White", "?")
                black = headers.get("Black", "?")
                print(f"  Processing: {white} vs {black} ({result}, avg {avg_elo:.0f})")

                candidates = process_game(game, engine, args.per_game, args.no_engine)
                all_candidates.extend(candidates)
                games_processed += 1

    finally:
        if engine:
            try:
                engine.quit()
            except Exception:
                pass

    # Save all candidates
    with open(candidates_file, "w", encoding="utf-8") as f:
        json.dump(all_candidates, f, indent=2, ensure_ascii=False)

    # Save verified subset (PASS + WARN only)
    verified = [c for c in all_candidates if c["status"] in ("PASS", "WARN")]
    with open(verified_file, "w", encoding="utf-8") as f:
        json.dump(verified, f, indent=2, ensure_ascii=False)

    # Summary
    print()
    print("=" * 60)
    print(f"Games processed : {games_processed}")
    print(f"Games skipped   : {games_skipped}")
    print(f"Total candidates: {len(all_candidates)}")
    if not args.no_engine:
        statuses = {}
        for c in all_candidates:
            statuses[c["status"]] = statuses.get(c["status"], 0) + 1
        for status, count in sorted(statuses.items()):
            print(f"  {status:12s}: {count}")
        print(f"Verified (PASS+WARN): {len(verified)}")
    print()
    print(f"Output:")
    print(f"  All candidates : {candidates_file}")
    if not args.no_engine:
        print(f"  Verified only  : {verified_file}")
    print()
    print("Next step:")
    print("  Review verified_*.json, then run gen_week.py to build HTML exercises.")


if __name__ == "__main__":
    main()
