import secrets
from constants import HORSE_NUMBERS, TRACK_LENGTHS


class GameState:
    def __init__(self):
        self.phase     = 'racing'   # 'racing' | 'done'
        self.positions : dict[int, int] = {n: 0 for n in HORSE_NUMBERS}
        self.winner    : int | None = None
        self.last_roll : tuple[int, int] | None = None
        self.roll_log  : list[tuple[int, int]] = []

    # ── Dice ─────────────────────────────────────────────────────────────────

    def roll_dice(self) -> tuple[int, int]:
        """Cryptographically secure roll using OS entropy (secrets module)."""
        d1 = secrets.randbelow(6) + 1
        d2 = secrets.randbelow(6) + 1
        self.last_roll = (d1, d2)
        self.roll_log.append((d1, d2))
        return d1, d2

    def apply_roll(self, d1: int, d2: int) -> tuple[int, bool]:
        """
        Apply a roll (from digital or webcam dice).
        Returns (horse_number, did_win).
        """
        horse = d1 + d2
        self.last_roll = (d1, d2)
        if horse not in HORSE_NUMBERS:
            return horse, False
        self.positions[horse] = min(self.positions[horse] + 1, TRACK_LENGTHS[horse])
        won = self.positions[horse] >= TRACK_LENGTHS[horse]
        if won:
            self.winner = horse
            self.phase  = 'done'
        return horse, won

    # ── Admin ─────────────────────────────────────────────────────────────────

    def set_position(self, horse: int, pos: int):
        """Admin: manually set a horse's peg position (0 = start)."""
        pos = max(0, min(pos, TRACK_LENGTHS[horse]))
        self.positions[horse] = pos
        if pos >= TRACK_LENGTHS[horse]:
            self.winner = horse
            self.phase  = 'done'

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def reset(self):
        self.__init__()
