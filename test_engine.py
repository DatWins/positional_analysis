#!/usr/bin/env python3
"""Quick Stockfish connectivity test for python-chess.
Run this before extract_positions.py to confirm the engine works.

Usage:
  python test_engine.py "C:\LAM_CHESS\positional_analysis\stockfish.exe"
"""
import sys

try:
    import chess
    import chess.engine
except ImportError:
    print("ERROR: python-chess not installed. Run: pip install python-chess")
    sys.exit(1)

sf_path = sys.argv[1] if len(sys.argv) > 1 else "stockfish"
print(f"Testing Stockfish at: {sf_path}")

# Test 1: start engine
try:
    engine = chess.engine.SimpleEngine.popen_uci(sf_path)
    print("PASS  Engine started OK")
except Exception as e:
    print(f"FAIL  Engine failed to start: {e}")
    sys.exit(1)

# Test 2: analyse starting position, multipv=1
try:
    board = chess.Board()
    info = engine.analyse(board, chess.engine.Limit(depth=10))
    pv = info.get("pv", [])
    move = board.san(pv[0]) if pv else "?"
    print(f"PASS  multipv=1 analysis OK — best move: {move}")
except Exception as e:
    print(f"FAIL  multipv=1 analysis failed: {e}")

# Test 3: multipv=3
try:
    board = chess.Board()
    infos = engine.analyse(board, chess.engine.Limit(depth=10), multipv=3)
    if isinstance(infos, dict):
        infos = [infos]
    moves = [board.san(i["pv"][0]) for i in infos if i.get("pv")]
    print(f"PASS  multipv=3 analysis OK — top moves: {moves}")
except Exception as e:
    print(f"FAIL  multipv=3 analysis failed: {e}")

# Test 4: quit cleanly
try:
    engine.quit()
    print("PASS  Engine quit cleanly")
except Exception as e:
    print(f"WARN  Engine quit raised: {e}")

print("\nDone.")
