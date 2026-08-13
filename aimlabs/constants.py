# constants.py
# 所有常量及通用辅助函数

import math

# ---------- WINDOW ----------
WINDOW_SIZE = (1600, 1000)
BG_COLOR = (28, 28, 34)
BODY_COLOR = (78, 160, 220)
HIT_BODY_COLOR = (220, 120, 120)
HEAD_COLOR = (250, 210, 150)
EYE_COLOR = (40, 40, 40)
HUD_COLOR = (230, 230, 230)

# Person target geometry
CONE_BASE_WIDTH = 160
CONE_HEIGHT = 220
CONE_MAX_HITS = 4
SPHERE_RADIUS = 48

MARGIN = 36
GAME_LENGTH_SECS = 120

FONT_NAME = None
SFX_VOLUME = 0.16

# Movement / spawn
MOVE_INTERVAL = 0.2
SPAWN_INTERVAL = 1.0
REACH_DISTANCE = 48
MAX_SIMULTANEOUS_ALIVE = 300
MIN_SPAWN_SEPARATION = 160

SPAWN_MIN = 3
SPAWN_MAX = 5

HEAL_INTERVAL = 3.0

SPAWN_TYPE_WEIGHTS = [8, 1, 1, 1]   # regular : healer : respawner : protector

RESPAWN_DELAY = 2.0

SLOW_SPAWN_MULTIPLIER = 2.0
SLOW_SPAWN_DURATION = 40.0

LAST10_SPAWN_MULTIPLIER = 2.0

MUSIC_FILE = "background.mp3"

# ---------- helpers ----------
def clamp(v, a, b):
    return max(a, min(b, v))

def lerp(a, b, t):
    return a + (b - a) * t