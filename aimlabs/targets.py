# targets.py
# 目标实体类：ConeBody 和 PersonTarget

import math
from typing import Tuple, Optional
import pygame  # 仅用于类型提示，不强制
from constants import clamp, lerp, CONE_BASE_WIDTH, CONE_HEIGHT, CONE_MAX_HITS, SPHERE_RADIUS, RESPAWN_DELAY

class ConeBody:
    def __init__(self, pos, max_hits=CONE_MAX_HITS):
        self.center = pos
        self.max_hits = int(max_hits)
        self.hits_remaining = int(self.max_hits)
        self.alive = True

    def reset(self, pos):
        self.center = pos
        self.hits_remaining = int(self.max_hits)
        self.alive = True

    def damage(self, amount=1):
        self.hits_remaining = max(0, self.hits_remaining - int(amount))
        if self.hits_remaining == 0:
            self.alive = False


class PersonTarget:
    def __init__(self, pos: Tuple[int, int], depth: float = 0.0,
                 move_vector: Tuple[float, float] = (0.0, 0.0),
                 steps_remaining: int = 0, target_type: str = 'regular'):
        self.center = pos
        self.depth = clamp(depth, 0.0, 1.0)
        self.body = ConeBody(pos, max_hits=CONE_MAX_HITS)
        self.move_vector = (float(move_vector[0]), float(move_vector[1]))
        self.steps_remaining = int(steps_remaining)
        self.target_type = target_type
        self.shielded = True if self.target_type == 'protector' else False
        self.update_geometry()
        self.alive = True
        self._torso_rect = None
        self.spawn_params = (pos, self.depth, self.move_vector, self.steps_remaining, self.target_type)
        self.respawn_timer: Optional[float] = None
        self.respawned_once = False

    def update_geometry(self):
        cx, cy = self.center
        parallax_y = int(lerp(-30, 30, self.depth))
        self.screen_center = (cx, cy + parallax_y)
        self.scale = lerp(1.2, 0.55, self.depth)
        self.cone_top_y = self.screen_center[1] - (CONE_HEIGHT / 2.0) * self.scale
        self.cone_base_w = CONE_BASE_WIDTH * self.scale
        self.cone_height = CONE_HEIGHT * self.scale
        self.sphere_center = (self.screen_center[0], self.cone_top_y - SPHERE_RADIUS * 0.28 * self.scale)
        self.arm_y = self.cone_top_y + self.cone_height * 0.12

    def reset(self, pos: Tuple[int, int], depth: float = 0.0,
              move_vector=(0.0, 0.0), steps_remaining=0, target_type: str = 'regular'):
        self.center = pos
        self.depth = clamp(depth, 0.0, 1.0)
        self.body = ConeBody(pos, max_hits=CONE_MAX_HITS)
        self.move_vector = (float(move_vector[0]), float(move_vector[1]))
        self.steps_remaining = int(steps_remaining)
        self.target_type = target_type
        self.shielded = True if self.target_type == 'protector' else False
        self.update_geometry()
        self.alive = True
        self._torso_rect = None
        self.respawn_timer = None
        self.spawn_params = (pos, self.depth, self.move_vector, self.steps_remaining, self.target_type)

    def advance_step(self):
        if not self.alive:
            return
        sx, sy = self.move_vector
        cx, cy = self.center
        self.center = (cx + sx, cy + sy)
        self.steps_remaining = max(0, self.steps_remaining - 1)
        self.update_geometry()

    def on_death(self):
        if self.target_type == 'respawner' and (not self.respawned_once):
            self.respawn_timer = RESPAWN_DELAY
            self.alive = False
            self.respawned_once = True
        else:
            self.respawn_timer = None
            self.alive = False

    def damage_body(self, amount=1):
        if self.shielded:
            self.shielded = False
            return
        if not self.body.alive:
            return
        self.body.damage(amount)
        if not self.body.alive:
            self.on_death()

    def destroy_by_head(self):
        if self.shielded:
            self.shielded = False
            return
        self.body.alive = False
        self.on_death()

    def bounding_box(self):
        cx, cy = self.screen_center
        half_w = int(self.cone_base_w / 2) + 20
        top_y = int(self.cone_top_y - SPHERE_RADIUS * self.scale * 1.3)
        bottom_y = int(self.cone_top_y + self.cone_height + 40)
        return (cx - half_w, top_y, cx + half_w, bottom_y)