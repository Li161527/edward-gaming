# backend.py
# 管理所有目标的生成、移动、存活状态

import random
import math
from typing import List, Tuple
from constants import (
    MARGIN, MOVE_INTERVAL, SPAWN_INTERVAL, REACH_DISTANCE,
    MAX_SIMULTANEOUS_ALIVE, MIN_SPAWN_SEPARATION,
    SPAWN_MIN, SPAWN_MAX, HEAL_INTERVAL,
    SPAWN_TYPE_WEIGHTS, RESPAWN_DELAY,
    LAST10_SPAWN_MULTIPLIER,
    CONE_HEIGHT, SPHERE_RADIUS, CONE_BASE_WIDTH,
    clamp, lerp
)
from targets import PersonTarget

class Backend:
    def __init__(self, screen_size):
        self.screen_w, self.screen_h = screen_size
        self.targets: List[PersonTarget] = []
        self.spawn_margin = MARGIN
        self.move_acc = 0.0
        self.spawn_acc = 0.0
        self.reached = False
        self.total_spawned = 0
        self.heal_acc = 0.0
        self.spawn_interval_multiplier = 1.0
        self.spawn_slow_timer = 0.0

    def compute_spawn_bounds(self):
        top_offset = - (CONE_HEIGHT / 2.0) - (SPHERE_RADIUS * 1.28)
        bottom_offset = (CONE_HEIGHT / 2.0) + 48
        left_offset = - (CONE_BASE_WIDTH / 2.0) - 8
        right_offset = (CONE_BASE_WIDTH / 2.0) + 8

        min_cx = int(self.spawn_margin - left_offset)
        max_cx = int(self.screen_w - self.spawn_margin - right_offset)
        min_cy = int(self.spawn_margin - top_offset)
        max_cy = int(self.screen_h - self.spawn_margin - bottom_offset)

        min_cx = clamp(min_cx, self.spawn_margin, self.screen_w - self.spawn_margin)
        max_cx = clamp(max_cx, self.spawn_margin, self.screen_w - self.spawn_margin)
        min_cy = clamp(min_cy, self.spawn_margin, self.screen_h - self.spawn_margin)
        max_cy = clamp(max_cy, self.spawn_margin, self.screen_h - self.spawn_margin)

        return min_cx, max_cx, min_cy, max_cy

    def candidate_positions(self):
        min_cx, max_cx, min_cy, max_cy = self.compute_spawn_bounds()
        candidates = [
            (min_cx, min_cy),
            (min_cx, max_cy),
            (max_cx, min_cy),
            (max_cx, max_cy),
            (min_cx, (min_cy + max_cy) // 2),
            (max_cx, (min_cy + max_cy) // 2),
            ((min_cx + max_cx) // 2, min_cy),
            ((min_cx + max_cx) // 2, max_cy),
        ]
        return candidates

    def spawn_many_farthest(self, front_pos: Tuple[int, int], remaining_time_s: float, n_to_spawn: int):
        if n_to_spawn <= 0:
            return []
        alive_now = len([t for t in self.targets if t.alive])
        if alive_now >= MAX_SIMULTANEOUS_ALIVE:
            return []

        candidates = self.candidate_positions()
        fx, fy = front_pos
        candidates_with_dist = [(p, math.hypot(p[0] - fx, p[1] - fy)) for p in candidates]
        candidates_with_dist.sort(key=lambda x: x[1])
        if candidates_with_dist:
            candidates_with_dist.pop(0)
        candidates_with_dist.sort(key=lambda x: x[1], reverse=True)
        ordered = [p for (p, _) in candidates_with_dist]

        spawned = []
        alive_positions = [t.screen_center for t in self.targets if t.alive]

        for p in ordered:
            if len(spawned) >= n_to_spawn:
                break
            too_close = False
            for ap in alive_positions:
                if math.hypot(ap[0] - p[0], ap[1] - p[1]) < MIN_SPAWN_SEPARATION:
                    too_close = True
                    break
            if too_close:
                continue
            for sp in spawned:
                if math.hypot(sp[0] - p[0], sp[1] - p[1]) < MIN_SPAWN_SEPARATION:
                    too_close = True
                    break
            if too_close:
                continue

            d = math.hypot(p[0] - fx, p[1] - fy)
            min_cx, max_cx, min_cy, max_cy = self.compute_spawn_bounds()
            max_possible = math.hypot(max_cx - min_cx, max_cy - min_cy) or 1.0
            depth = clamp(d / max_possible, 0.0, 1.0)

            steps_total = max(1, int(max(0.0, remaining_time_s) / MOVE_INTERVAL))
            sx = (fx - p[0]) / float(steps_total)
            sy = (fy - p[1]) / float(steps_total)

            ttype = random.choices(['regular', 'healer', 'respawner', 'protector'],
                                   weights=SPAWN_TYPE_WEIGHTS, k=1)[0]
            t = PersonTarget(p, depth=depth, move_vector=(sx, sy),
                             steps_remaining=steps_total, target_type=ttype)
            self.targets.append(t)
            spawned.append(p)
            alive_positions.append(t.screen_center)
            self.total_spawned += 1

            alive_now = len([tt for tt in self.targets if tt.alive])
            if alive_now >= MAX_SIMULTANEOUS_ALIVE:
                break

        return spawned

    def get_targets(self) -> List[PersonTarget]:
        return self.targets

    def remove_dead(self):
        new_targets = []
        for t in self.targets:
            if t.alive:
                new_targets.append(t)
            else:
                if getattr(t, "respawn_timer", None) is not None:
                    new_targets.append(t)
        self.targets = new_targets

    def update(self, dt: float, front_pos: Tuple[int, int], remaining_time_s: float):
        if self.spawn_slow_timer > 0.0:
            self.spawn_slow_timer -= dt
            if self.spawn_slow_timer <= 0.0:
                self.spawn_interval_multiplier = 1.0
                self.spawn_slow_timer = 0.0

        self.remove_dead()

        for t in list(self.targets):
            if not t.alive and getattr(t, "respawn_timer", None) is not None:
                t.respawn_timer -= dt
                if t.respawn_timer <= 0.0:
                    pos, depth, mv, steps, ttype = t.spawn_params
                    t.reset(pos, depth=depth, move_vector=mv,
                            steps_remaining=steps, target_type=ttype)
                    self.total_spawned += 1

        if remaining_time_s > 0.0:
            self.spawn_acc += dt
            last10_mult = LAST10_SPAWN_MULTIPLIER if remaining_time_s <= 10.0 else 1.0
            current_spawn_interval = SPAWN_INTERVAL * self.spawn_interval_multiplier * last10_mult
            while self.spawn_acc >= current_spawn_interval:
                self.spawn_acc -= current_spawn_interval
                spawn_n = random.randint(SPAWN_MIN, SPAWN_MAX)
                alive_now = len([t for t in self.targets if t.alive])
                capacity = max(0, MAX_SIMULTANEOUS_ALIVE - alive_now)
                spawn_n = min(spawn_n, capacity, len(self.candidate_positions()) - 1)
                if spawn_n <= 0:
                    break
                self.spawn_many_farthest(front_pos, remaining_time_s, spawn_n)

        if any(t.alive and t.target_type == 'healer' for t in self.targets):
            self.heal_acc += dt
            while self.heal_acc >= HEAL_INTERVAL:
                self.heal_acc -= HEAL_INTERVAL
                for t in self.targets:
                    if t.alive:
                        t.body.hits_remaining = min(t.body.max_hits, t.body.hits_remaining + 1)

        if not self.targets:
            return

        self.move_acc += dt
        while self.move_acc >= MOVE_INTERVAL:
            self.move_acc -= MOVE_INTERVAL
            for t in list(self.targets):
                if not t.alive:
                    continue
                t.advance_step()
                fx, fy = front_pos
                dist = math.hypot(t.screen_center[0] - fx, t.screen_center[1] - fy)
                if dist <= REACH_DISTANCE:
                    self.reached = True
                    return
            self.remove_dead()

    def alive_count(self):
        return sum(1 for t in self.targets if t.alive)