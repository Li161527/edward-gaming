# Full working Aim Trainer with respawners, specials, final-10s slowdown,
# Rifle magazine increased (+30), and Gatling unlocked at 60s.
import pygame
import random
import math
import sys
import io
import wave
import os
from typing import Tuple, Optional, List
from array import array

# ---------- CONFIG ----------
WINDOW_SIZE = (1600, 1000)
BG_COLOR = (28, 28, 34)
BODY_COLOR = (78, 160, 220)
HIT_BODY_COLOR = (220, 120, 120)
HEAD_COLOR = (250, 210, 150)
EYE_COLOR = (40, 40, 40)
HUD_COLOR = (230, 230, 230)

# Person target geometry (base sizes, will be scaled by depth)
CONE_BASE_WIDTH = 160
CONE_HEIGHT = 220
CONE_MAX_HITS = 4
SPHERE_RADIUS = 48

MARGIN = 36
GAME_LENGTH_SECS = 120

FONT_NAME = None
SFX_VOLUME = 0.16

# Movement / spawn tuning
MOVE_INTERVAL = 0.2
SPAWN_INTERVAL = 1.0
REACH_DISTANCE = 48
MAX_SIMULTANEOUS_ALIVE = 300
MIN_SPAWN_SEPARATION = 160

SPAWN_MIN = 3
SPAWN_MAX = 5

HEAL_INTERVAL = 3.0

# regular : healer : respawner : protector = 8 : 1 : 1 : 1
SPAWN_TYPE_WEIGHTS = [8, 1, 1, 1]

RESPAWN_DELAY = 2.0

SLOW_SPAWN_MULTIPLIER = 2.0
SLOW_SPAWN_DURATION = 40.0

LAST10_SPAWN_MULTIPLIER = 2.0

MUSIC_FILE = "background.mp3"
# ----------------------------

pygame.init()
try:
    pygame.mixer.init(frequency=44100, size=-16, channels=2)
except Exception:
    pass

screen = pygame.display.set_mode(WINDOW_SIZE)
pygame.display.set_caption("Aim Trainer — many moving targets")

clock = pygame.time.Clock()
font = pygame.font.Font(FONT_NAME, 20)
big_font = pygame.font.Font(FONT_NAME, 48)


def clamp(v, a, b):
    return max(a, min(b, v))


def lerp(a, b, t):
    return a + (b - a) * t


# --- sound helpers ---
def make_tone(freq=440.0, duration=0.12, volume=0.5, sample_rate=44100):
    n_samples = int(sample_rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            decay = math.exp(-4.0 * t)
            s = 0.6 * math.sin(2.0 * math.pi * freq * t) + 0.25 * math.sin(2.0 * math.pi * freq * 2.0 * t)
            sample = int(volume * decay * 32767.0 * s)
            frames += sample.to_bytes(2, byteorder='little', signed=True)
        wf.writeframes(frames)
    buf.seek(0)
    try:
        sound = pygame.mixer.Sound(file=buf)
    except TypeError:
        buf.seek(0)
        sound = pygame.mixer.Sound(buf.read())
    sound.set_volume(SFX_VOLUME)
    return sound


SAMPLE_RATE_GUN = 44100


def make_deep_boom_shot(duration=0.20, volume=0.70):
    n = int(SAMPLE_RATE_GUN * duration)
    buf = array('h')
    for i in range(n):
        t = i / SAMPLE_RATE_GUN
        if t < 0.005:
            attack_env = t / 0.005
        else:
            attack_env = math.exp(-(t - 0.005) * 11)
        boom_low = math.sin(2 * math.pi * 55 * t)
        boom_low_env = math.exp(-t * 7.5)
        sub_boom = math.sin(2 * math.pi * 80 * t)
        sub_boom_env = math.exp(-t * 10)
        metal_res = math.sin(2 * math.pi * 130 * t)
        metal_res_env = math.exp(-t * 14)
        crack_noise = random.uniform(-0.8, 0.8)
        noise_env = math.exp(-t * 35)
        mixed = (
            boom_low * 0.75 * boom_low_env
            + sub_boom * 0.35 * sub_boom_env
            + metal_res * 0.18 * metal_res_env
            + crack_noise * 0.12 * noise_env
        )
        final = mixed * attack_env * volume
        final = max(-1.0, min(1.0, final))
        buf.append(int(final * 32767))
    return pygame.mixer.Sound(buf)


def make_delta_hit(duration=0.09, volume=0.65):
    n = int(SAMPLE_RATE_GUN * duration)
    buf = array('h')
    for i in range(n):
        t = i / SAMPLE_RATE_GUN
        if t < 0.004:
            env_attack = t / 0.004
        else:
            env_attack = math.exp(-(t - 0.004) * 22)
        body_thud = math.sin(2 * math.pi * 82 * t)
        body_env = math.exp(-t * 13)
        crack = random.uniform(-0.65, 0.65)
        crack_env = math.exp(-t * 42)
        mixed = (
            body_thud * 0.70 * body_env
            + crack * 0.20 * crack_env
        )
        sample = mixed * env_attack * volume
        sample = max(-1.0, min(1.0, sample))
        buf.append(int(sample * 32767))
    return pygame.mixer.Sound(buf)


HIT_SOUND = make_delta_hit(duration=0.11, volume=0.68)
DESTROY_SOUND = make_tone(420.0, 0.18, 0.8)
MISS_SOUND = make_tone(160.0, 0.06, 0.4)
PISTOL_FIRE_SFX = make_deep_boom_shot(duration=0.12, volume=0.62)
RIFLE_FIRE_SFX = make_deep_boom_shot(duration=0.20, volume=0.70)
EMPTY_CLICK = make_tone(140.0, 0.08, 0.25)
RELOAD_SFX = make_tone(220.0, 0.28, 0.7)


# --- collision helpers ---
def point_in_sphere(px, py, sx, sy, r):
    return (px - sx) ** 2 + (py - sy) ** 2 <= r * r


def point_in_rect(px, py, rx, ry, rw, rh):
    return (px >= rx) and (px <= rx + rw) and (py >= ry) and (py <= ry + rh)


# --- Targets ---
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
    def __init__(self, pos: Tuple[int, int], depth: float = 0.0, move_vector: Tuple[float, float] = (0.0, 0.0),
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

    def reset(self, pos: Tuple[int, int], depth: float = 0.0, move_vector=(0.0, 0.0), steps_remaining=0, target_type: str = 'regular'):
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


# --- Backend ---
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

            ttype = random.choices(['regular', 'healer', 'respawner', 'protector'], weights=SPAWN_TYPE_WEIGHTS, k=1)[0]
            t = PersonTarget(p, depth=depth, move_vector=(sx, sy), steps_remaining=steps_total, target_type=ttype)
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
                    t.reset(pos, depth=depth, move_vector=mv, steps_remaining=steps, target_type=ttype)
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


# --- Gun / Weapon models ---
class GunModel:
    def __init__(self):
        self.recoil = 0.0
        self.rot_recoil = 0.0

    def update(self, dt):
        if self.recoil > 0:
            self.recoil = max(0.0, self.recoil - dt * self.recoil * 6.0 - dt * 60.0)
        if self.rot_recoil > 0:
            self.rot_recoil = max(0.0, self.rot_recoil - dt * 160.0)

    def reset(self):
        self.recoil = 0.0
        self.rot_recoil = 0.0


class PistolModel(GunModel):
    def __init__(self):
        super().__init__()
        self.slide_back = 0.0
        self.slide_vel = 0.0
        self.slide_speed = 8.0
        self.width = 640
        self.height = 160
        self.muzzle_local = (0.82, 0.28)

    def on_fire(self, muzzle_world, muzzle_angle_deg):
        self.recoil += 10.0
        self.rot_recoil += random.uniform(1.8, 4.2)
        self.slide_vel = 1.0

    def update(self, dt):
        super().update(dt)
        self.slide_back += self.slide_vel * dt
        self.slide_vel -= self.slide_back * self.slide_speed * dt * 2.0
        self.slide_vel *= (1.0 - dt * 6.0)
        self.slide_back = clamp(self.slide_back, 0.0, 1.0)

    def reset(self):
        super().reset()
        self.slide_back = 0.0
        self.slide_vel = 0.0

    def draw(self, surface, base_pos, aim_angle_deg, scale=1.0):
        cx, cy = base_pos
        w = int(self.width * scale)
        h = int(self.height * scale)
        gun_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        gun_surf = gun_surf.convert_alpha()
        frame_color = (40, 40, 42)
        slide_color = (90, 90, 95)
        grip_color = (25, 25, 25)
        pygame.draw.rect(gun_surf, frame_color, (int(w * 0.06), int(h * 0.46), int(w * 0.6), int(h * 0.32)), border_radius=8)
        pygame.draw.rect(gun_surf, grip_color, (int(w * 0.66), int(h * 0.54), int(w * 0.24), int(h * 0.36)), border_radius=6)
        slide_back_px = int(self.slide_back * (w * 0.06))
        pygame.draw.rect(gun_surf, slide_color, (int(w * 0.04) + slide_back_px, int(h * 0.16), int(w * 0.7), int(h * 0.28)), border_radius=6)
        barrel_x = int(w * 0.76) + slide_back_px
        barrel_y = int(h * 0.26)
        barrel_w = int(w * 0.2)
        barrel_h = int(h * 0.14)
        pygame.draw.rect(gun_surf, (28, 28, 28), (barrel_x, barrel_y, barrel_w, barrel_h), border_radius=6)
        pygame.draw.rect(gun_surf, (200, 200, 200), (int(w * 0.38), int(h * 0.08), int(w * 0.06), 6))
        pygame.draw.rect(gun_surf, (200, 200, 200), (int(w * 0.84), int(h * 0.06), int(w * 0.04), 6))
        pygame.draw.rect(gun_surf, (20, 20, 20), (int(w * 0.46), int(h * 0.7), int(w * 0.1), int(h * 0.24)), border_radius=4)
        pygame.draw.line(gun_surf, (100, 100, 100), (int(w * 0.05), int(h * 0.22)), (int(w * 0.85), int(h * 0.22)), 2)
        rotated = pygame.transform.rotate(gun_surf, aim_angle_deg - self.rot_recoil)
        rect = rotated.get_rect(center=(cx, cy - int(self.recoil)))
        surface.blit(rotated, rect.topleft)
        m_local_x = int(w * self.muzzle_local[0])
        m_local_y = int(h * self.muzzle_local[1])
        m_local_x += slide_back_px
        center_local = (w / 2.0, h / 2.0)
        relx = m_local_x - center_local[0]
        rely = m_local_y - center_local[1]
        ang_rad = math.radians(-(aim_angle_deg - self.rot_recoil))
        rx = relx * math.cos(ang_rad) - rely * math.sin(ang_rad)
        ry = relx * math.sin(ang_rad) + rely * math.cos(ang_rad)
        muzzle_world = (rect.left + center_local[0] + rx, rect.top + center_local[1] + ry)
        gun_rect = rect
        return muzzle_world, gun_rect


class RifleModel(GunModel):
    def __init__(self):
        super().__init__()
        self.bolt = 0.0
        self.bolt_vel = 0.0
        self.sway_phase = 0.0
        self.width = 980
        self.height = 200
        self.muzzle_local = (0.92, 0.30)

    def on_fire(self, muzzle_world, muzzle_angle_deg):
        self.recoil += 6.0
        self.rot_recoil += random.uniform(2.2, 5.0)
        self.bolt_vel = 1.2 + random.uniform(0.0, 0.4)

    def update(self, dt):
        super().update(dt)
        self.bolt += self.bolt_vel * dt
        self.bolt_vel -= self.bolt * 8.0 * dt
        self.bolt_vel *= (1.0 - dt * 8.0)
        self.bolt = clamp(self.bolt, 0.0, 1.0)
        self.sway_phase += dt * 1.2

    def reset(self):
        super().reset()
        self.bolt = 0.0
        self.bolt_vel = 0.0
        self.sway_phase = 0.0

    def draw(self, surface, base_pos, aim_angle_deg, scale=1.0):
        cx, cy = base_pos
        w = int(self.width * scale)
        h = int(self.height * scale)
        gun_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        gun_surf = gun_surf.convert_alpha()
        body_col = (35, 35, 35)
        metal_col = (60, 60, 60)
        pygame.draw.rect(gun_surf, (28, 28, 28), (int(w * 0.02), int(h * 0.56), int(w * 0.22), int(h * 0.32)), border_radius=8)
        pygame.draw.rect(gun_surf, body_col, (int(w * 0.18), int(h * 0.34), int(w * 0.46), int(h * 0.26)), border_radius=6)
        pygame.draw.rect(gun_surf, (22, 22, 22), (int(w * 0.66), int(h * 0.48), int(w * 0.12), int(h * 0.26)), border_radius=6)
        barrel_x = int(w * 0.7)
        barrel_y = int(h * 0.22)
        barrel_w = int(w * 0.28)
        barrel_h = int(h * 0.12)
        pygame.draw.rect(gun_surf, metal_col, (barrel_x, barrel_y, barrel_w, barrel_h), border_radius=6)
        muzzle_w = int(w * 0.06)
        muzzle_h = int(h * 0.16)
        muzzle_x = barrel_x + barrel_w - 6
        muzzle_y = barrel_y - int(h * 0.02)
        pygame.draw.rect(gun_surf, (22, 22, 22), (muzzle_x, muzzle_y, muzzle_w, muzzle_h), border_radius=6)
        pygame.draw.rect(gun_surf, (70, 70, 70), (int(w * 0.3), int(h * 0.12), int(w * 0.36), int(h * 0.08)), border_radius=4)
        bolt_back_px = int(self.bolt * (w * 0.03))
        pygame.draw.rect(gun_surf, (40, 40, 40), (int(w * 0.28) + bolt_back_px, int(h * 0.3), int(w * 0.08), int(h * 0.12)), border_radius=4)
        pygame.draw.rect(gun_surf, (20, 20, 20), (int(w * 0.44), int(h * 0.48), int(w * 0.06), int(h * 0.26)), border_radius=4)
        pygame.draw.line(gun_surf, (100, 100, 100), (int(w * 0.2), int(h * 0.2)), (int(w * 0.78), int(h * 0.2)), 2)
        sway_rot = math.sin(self.sway_phase) * 1.2
        total_angle = aim_angle_deg - (self.rot_recoil * 0.7) + sway_rot
        rotated = pygame.transform.rotate(gun_surf, total_angle)
        rect = rotated.get_rect(center=(cx, cy - int(self.recoil)))
        surface.blit(rotated, rect.topleft)
        m_local_x = int(w * self.muzzle_local[0])
        m_local_y = int(h * self.muzzle_local[1])
        center_local = (w / 2.0, h / 2.0)
        relx = m_local_x - center_local[0]
        rely = m_local_y - center_local[1]
        ang_rad = math.radians(-(aim_angle_deg - (self.rot_recoil * 0.7) + sway_rot))
        rx = relx * math.cos(ang_rad) - rely * math.sin(ang_rad)
        ry = relx * math.sin(ang_rad) + rely * math.cos(ang_rad)
        muzzle_world = (rect.left + center_local[0] + rx, rect.top + center_local[1] + ry)
        gun_rect = rect
        return muzzle_world, gun_rect


class GatlingModel(GunModel):
    def __init__(self):
        super().__init__()
        self.spin = 0.0
        self.width = 1100
        self.height = 220
        self.muzzle_local = (0.96, 0.34)

    def on_fire(self, muzzle_world, muzzle_angle_deg):
        self.recoil += 4.0
        self.rot_recoil += random.uniform(1.0, 3.0)
        self.spin += 0.5

    def update(self, dt):
        super().update(dt)
        # decay spin slowly
        self.spin = max(0.0, self.spin - dt * 0.6)

    def reset(self):
        super().reset()
        self.spin = 0.0

    def draw(self, surface, base_pos, aim_angle_deg, scale=1.0):
        cx, cy = base_pos
        w = int(self.width * scale)
        h = int(self.height * scale)
        gun_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        gun_surf = gun_surf.convert_alpha()
        pygame.draw.rect(gun_surf, (24, 24, 24), (int(w * 0.05), int(h * 0.48), int(w * 0.7), int(h * 0.28)), border_radius=10)
        # barrels
        bar_x = int(w * 0.72)
        bar_y = int(h * 0.22)
        pygame.draw.rect(gun_surf, (60, 60, 60), (bar_x, bar_y, int(w * 0.24), int(h * 0.12)))
        # rotate slightly with rot_recoil
        total_angle = aim_angle_deg - (self.rot_recoil * 0.6)
        rotated = pygame.transform.rotate(gun_surf, total_angle)
        rect = rotated.get_rect(center=(cx, cy - int(self.recoil)))
        surface.blit(rotated, rect.topleft)
        m_local_x = int(w * self.muzzle_local[0])
        m_local_y = int(h * self.muzzle_local[1])
        center_local = (w / 2.0, h / 2.0)
        relx = m_local_x - center_local[0]
        rely = m_local_y - center_local[1]
        ang_rad = math.radians(-(total_angle))
        rx = relx * math.cos(ang_rad) - rely * math.sin(ang_rad)
        ry = relx * math.sin(ang_rad) + rely * math.cos(ang_rad)
        muzzle_world = (rect.left + center_local[0] + rx, rect.top + center_local[1] + ry)
        gun_rect = rect
        return muzzle_world, gun_rect


# --- Weapon logic ---
class Weapon:
    def __init__(self, name, mag_size, reserve, fire_rate, automatic, reload_time, model: GunModel):
        self.name = name
        self.mag_size = mag_size
        self.ammo = mag_size
        self.reserve = reserve
        self.initial_reserve = int(reserve)
        self.fire_rate = fire_rate
        self.automatic = automatic
        self.reload_time = reload_time
        self.model = model
        self.cooldown = 0.0
        self.reloading = False
        self.reload_timer = 0.0

    def can_fire(self):
        return (not self.reloading) and (self.cooldown <= 0.0) and self.ammo > 0

    def do_fire(self, muzzle_world, muzzle_angle_deg):
        if self.ammo <= 0:
            try:
                EMPTY_CLICK.play()
            except Exception:
                pass
            self.cooldown = 0.12
            return False
        self.ammo -= 1
        self.cooldown = 1.0 / self.fire_rate if self.fire_rate > 0 else 0.1
        try:
            self.model.on_fire(muzzle_world, muzzle_angle_deg)
        except Exception:
            pass
        try:
            if self.name == "Pistol":
                PISTOL_FIRE_SFX.play()
            else:
                RIFLE_FIRE_SFX.play()
        except Exception:
            pass
        return True

    def start_reload(self):
        if self.reloading or self.ammo == self.mag_size or self.reserve <= 0:
            return False
        self.reloading = True
        self.reload_timer = self.reload_time
        try:
            RELOAD_SFX.play()
        except Exception:
            pass
        return True

    def update(self, dt):
        if self.cooldown > 0.0:
            self.cooldown -= dt
        if self.reloading:
            self.reload_timer -= dt
            if self.reload_timer <= 0.0:
                needed = self.mag_size - self.ammo
                take = min(needed, self.reserve)
                self.ammo += take
                self.reserve -= take
                self.reloading = False
        try:
            self.model.update(dt)
        except Exception:
            pass

    def restore_initial_state(self):
        self.ammo = self.mag_size
        self.reserve = int(self.initial_reserve)
        self.reloading = False
        self.reload_timer = 0.0
        self.cooldown = 0.0
        try:
            self.model.reset()
        except Exception:
            try:
                self.model.recoil = 0.0
                self.model.rot_recoil = 0.0
            except Exception:
                pass


# --- Frontend / Player ---
class Frontend:
    def __init__(self, screen, backend: Backend):
        self.screen = screen
        self.backend = backend
        self.points = 0
        self.hits = 0
        self.shots = 0
        self.start_time = pygame.time.get_ticks()
        self.duration_ms = GAME_LENGTH_SECS * 1000

        self.pistol_model = PistolModel()
        self.rifle_model = RifleModel()
        self.gatling_model = GatlingModel()

        # Weapon 1: Pistol
        w1 = Weapon("Pistol", mag_size=24, reserve=96, fire_rate=5.0, automatic=False, reload_time=1.3, model=self.pistol_model)
        # Weapon 2: Rifle (increased magazine by +30 => 90)
        w2 = Weapon("Rifle", mag_size=90, reserve=360, fire_rate=12.0, automatic=True, reload_time=2.4, model=self.rifle_model)
        self.weapons: List[Weapon] = [w1, w2]
        self.gatling_unlocked = False
        self.gatling_index = None

        self.current_weapon_idx = 0
        self.crosshair_pos = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2)
        self.left_mouse_held = False
        self.front_end_exclude = self.compute_frontend_exclusion_rect()
        self.game_state = 'playing'
        self.hit_feedback: List[Tuple[int, int, float, Tuple[int, int, int]]] = []

        self.special_choice_available = False
        self.special_choice_used = False

    def compute_frontend_exclusion_rect(self):
        cx = WINDOW_SIZE[0] // 2
        gun_w = 900
        gun_h = 260
        x1 = cx - gun_w // 2 - 20
        x2 = cx + gun_w // 2 + 20
        y2 = WINDOW_SIZE[1] - 30
        y1 = y2 - gun_h
        return (x1, y1, x2, y2)

    def time_left_ms(self):
        elapsed = pygame.time.get_ticks() - self.start_time
        return max(0, self.duration_ms - elapsed)

    def is_over(self):
        return self.game_state != 'playing'

    def maybe_unlock_gatling(self):
        if not self.gatling_unlocked:
            # create gatling weapon and append
            g = Weapon("Gatling", mag_size=240, reserve=960, fire_rate=24.0, automatic=True, reload_time=4.8, model=self.gatling_model)
            self.weapons.append(g)
            self.gatling_unlocked = True
            self.gatling_index = len(self.weapons) - 1

    def update(self, dt):
        for w in self.weapons:
            w.update(dt)

        base_pos = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] - 150)
        remaining_time_s = max(0.0, (self.duration_ms - (pygame.time.get_ticks() - self.start_time)) / 1000.0)

        # unlock gatling at 60s
        elapsed_s = (pygame.time.get_ticks() - self.start_time) / 1000.0
        if elapsed_s >= 60.0 and not self.gatling_unlocked:
            self.maybe_unlock_gatling()

        self.backend.update(dt, base_pos, remaining_time_s)

        if self.backend.reached and self.game_state == 'playing':
            self.game_state = 'lost'

        if (pygame.time.get_ticks() - self.start_time) >= self.duration_ms and self.game_state == 'playing':
            alive = self.backend.alive_count()
            if alive == 0:
                self.game_state = 'won'
            else:
                self.game_state = 'lost'

        new_feedback = []
        for x, y, rem, col in self.hit_feedback:
            rem -= dt
            if rem > 0:
                new_feedback.append((x, y, rem, col))
        self.hit_feedback = new_feedback

        if (elapsed_s >= 60.0) and (not self.special_choice_used):
            self.special_choice_available = True

    def current_weapon(self) -> Weapon:
        return self.weapons[self.current_weapon_idx]

    def fire(self):
        if self.is_over():
            return
        w = self.current_weapon()
        base_pos = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] - 150)
        aim_angle = vec_angle(base_pos, self.crosshair_pos)
        muzzle_world, _ = w.model.draw(self.screen, base_pos, aim_angle, scale=1.0)
        if not w.can_fire():
            if w.ammo == 0 and not w.reloading:
                try:
                    EMPTY_CLICK.play()
                except Exception:
                    pass
            return False
        fired = w.do_fire(muzzle_world, aim_angle)
        if fired:
            self.shots += 1
            mx, my = self.crosshair_pos
            alive_targets = [t for t in self.backend.get_targets() if t.alive]
            alive_targets.sort(key=lambda t: t.depth)
            hit_any = False
            for t in alive_targets:
                sx, sy = t.sphere_center
                scaled_radius = max(4, int(SPHERE_RADIUS * t.scale))
                if point_in_sphere(mx, my, sx, sy, scaled_radius):
                    if t.shielded:
                        t.shielded = False
                        try:
                            MISS_SOUND.play()
                        except Exception:
                            pass
                        self.hit_feedback.append((mx, my, 0.18, (200, 80, 80)))
                        hit_any = True
                        break
                    self.hits += 1
                    t.destroy_by_head()
                    if getattr(t, "respawn_timer", None) is None:
                        self.points += 1
                        try:
                            DESTROY_SOUND.play()
                        except Exception:
                            pass
                    else:
                        try:
                            HIT_SOUND.play()
                        except Exception:
                            pass
                    self.hit_feedback.append((mx, my, 0.28, (120, 255, 160)))
                    hit_any = True
                    break

                cx = int(t.screen_center[0])
                torso = getattr(t, "_torso_rect", None)
                if torso is None:
                    torso_w = int(t.cone_base_w * 0.6)
                    torso_h = int(t.cone_height * 0.5)
                    torso_x = int(cx - torso_w // 2)
                    torso_y = int(t.cone_top_y + t.cone_height * 0.15)
                else:
                    torso_x, torso_y, torso_w, torso_h = torso

                if point_in_rect(mx, my, torso_x, torso_y, torso_w, torso_h):
                    if t.shielded:
                        t.shielded = False
                        try:
                            MISS_SOUND.play()
                        except Exception:
                            pass
                        self.hit_feedback.append((mx, my, 0.18, (200, 80, 80)))
                        hit_any = True
                        break
                    self.hits += 1
                    t.damage_body(1)
                    try:
                        HIT_SOUND.play()
                    except Exception:
                        pass
                    if not t.alive and getattr(t, "respawn_timer", None) is None:
                        self.points += 1
                        try:
                            DESTROY_SOUND.play()
                        except Exception:
                            pass
                    self.hit_feedback.append((mx, my, 0.28, (120, 255, 160)))
                    hit_any = True
                    break

            if not hit_any:
                try:
                    MISS_SOUND.play()
                except Exception:
                    pass
                self.hit_feedback.append((mx, my, 0.18, (220, 90, 90)))

            self.backend.remove_dead()
        return True

    def click_fire(self):
        w = self.current_weapon()
        if not w.automatic:
            self.fire()

    def start_auto_fire(self):
        self.left_mouse_held = True

    def stop_auto_fire(self):
        self.left_mouse_held = False

    def switch_weapon(self, idx):
        if 0 <= idx < len(self.weapons):
            self.current_weapon_idx = idx

    def reload_current(self):
        self.current_weapon().start_reload()

    def restore_all_weapons_to_initial(self):
        for w in self.weapons:
            w.restore_initial_state()

    def slow_spawn_choice(self):
        self.backend.spawn_interval_multiplier = SLOW_SPAWN_MULTIPLIER
        self.backend.spawn_slow_timer = SLOW_SPAWN_DURATION

    # --- rendering ---
    def draw_hud(self, surface):
        left = 12
        top = 8
        gap = 28
        color = HUD_COLOR
        time_left = max(0, (self.duration_ms - (pygame.time.get_ticks() - self.start_time)) // 1000)
        txt_points = font.render(f"Points: {self.points}", True, color)
        txt_hits = font.render(f"Hits: {self.hits}", True, color)
        txt_shots = font.render(f"Shots: {self.shots}", True, color)
        acc = (f"{(self.hits / self.shots * 100):.1f}%" if self.shots > 0 else "0.0%")
        txt_acc = font.render(f"Acc: {acc}", True, color)
        txt_time = font.render(f"Time: {time_left}s", True, color)
        txt_spawned = font.render(f"Spawned: {self.backend.total_spawned}", True, color)
        txt_alive = font.render(f"Alive: {self.backend.alive_count()}", True, color)
        surface.blit(txt_points, (left, top))
        surface.blit(txt_hits, (left, top + gap))
        surface.blit(txt_shots, (left, top + gap * 2))
        surface.blit(txt_acc, (left, top + gap * 3))
        surface.blit(txt_time, (left + 760, top))
        surface.blit(txt_spawned, (left, top + gap * 4))
        surface.blit(txt_alive, (left, top + gap * 5))

        w = self.current_weapon()
        txt_weapon = font.render(f"Weapon: {w.name}", True, color)
        txt_ammo = font.render(f"Ammo: {w.ammo}/{w.mag_size}  Reserve: {w.reserve}", True, color)
        hint_str = "1=Pistol  2=Rifle  E=Reload  R=Restart"
        if self.gatling_unlocked:
            hint_str = "1=Pistol  2=Rifle  3=Gatling  E=Reload  R=Restart"
        hint = font.render(hint_str, True, (200, 200, 200))
        surface.blit(txt_weapon, (WINDOW_SIZE[0] - 380, top))
        surface.blit(txt_ammo, (WINDOW_SIZE[0] - 380, top + gap))
        surface.blit(hint, (WINDOW_SIZE[0] - 720, WINDOW_SIZE[1] - 40))

        if self.special_choice_available and (not self.special_choice_used):
            choice_txt = font.render("CHOICE: L = Restore ALL weapons  |  S = Slow spawns (one-time)", True, (220, 220, 150))
            surface.blit(choice_txt, (WINDOW_SIZE[0] // 2 - choice_txt.get_width() // 2, WINDOW_SIZE[1] - 70))

        if self.backend.spawn_slow_timer > 0.0:
            txt_slow = font.render(f"Spawn slow: {int(math.ceil(self.backend.spawn_slow_timer))}s", True, (180, 220, 255))
            surface.blit(txt_slow, (WINDOW_SIZE[0] - 220, top + gap * 3))

    def draw_person(self, surface, t: PersonTarget):
        cx = int(t.screen_center[0])
        base_y = int(t.cone_top_y)
        base_w = int(t.cone_base_w)
        height = int(t.cone_height)
        depth_tint = int(lerp(0, 60, t.depth))

        if not t.alive:
            skin_col = (120, 110, 100)
            cloth_col = (90, 90, 90)
        else:
            skin_base = (250, 210, 150)
            if t.target_type == 'healer':
                cloth_base = (100, 200, 120)
            elif t.target_type == 'protector':
                cloth_base = (120, 160, 220)
            elif t.target_type == 'respawner':
                cloth_base = (180, 120, 220)
            else:
                cloth_base = BODY_COLOR if t.body.hits_remaining == t.body.max_hits else HIT_BODY_COLOR
            skin_col = (max(0, skin_base[0] - depth_tint), max(0, skin_base[1] - depth_tint), max(0, skin_base[2] - depth_tint))
            cloth_col = (max(0, cloth_base[0] - depth_tint), max(0, cloth_base[1] - depth_tint), max(0, cloth_base[2] - depth_tint))

        sx, sy = int(t.sphere_center[0]), int(t.sphere_center[1])
        scaled_head_radius = max(6, int(SPHERE_RADIUS * t.scale))
        if t.alive:
            pygame.draw.circle(surface, (20, 20, 20), (sx, sy), scaled_head_radius + max(3, int(6 * t.scale)))
            pygame.draw.circle(surface, skin_col, (sx, sy), scaled_head_radius)
            hair_h = int(scaled_head_radius * 0.6)
            pygame.draw.ellipse(surface, (40, 30, 20), (sx - scaled_head_radius, sy - scaled_head_radius, scaled_head_radius * 2, hair_h))
            eye_offset_x = max(6, scaled_head_radius // 3)
            eye_offset_y = -max(4, int(6 * t.scale))
            eye_r = max(1, int(3 * t.scale))
            pygame.draw.circle(surface, (40, 40, 40), (sx - eye_offset_x, sy + eye_offset_y), eye_r)
            pygame.draw.circle(surface, (40, 40, 40), (sx + eye_offset_x, sy + eye_offset_y), eye_r)
            nose = [(sx, sy - 2), (sx - 4, sy + 4), (sx + 4, sy + 4)]
            pygame.draw.polygon(surface, (200, 160, 120), nose)
            mouth_rect = pygame.Rect(sx - int(8 * t.scale), sy + int(8 * t.scale), int(16 * t.scale), max(6, int(8 * t.scale)))
            pygame.draw.arc(surface, (100, 60, 60), mouth_rect, math.radians(20), math.radians(160), max(1, int(2 * t.scale)))
        else:
            pygame.draw.circle(surface, (130, 130, 130), (sx, sy), scaled_head_radius, 2)

        torso_w = int(base_w * 0.6)
        torso_h = int(height * 0.5)
        torso_x = cx - torso_w // 2
        torso_y = int(base_y + height * 0.15)
        pygame.draw.rect(surface, cloth_col, (torso_x, torso_y, torso_w, torso_h), border_radius=max(4, int(6 * t.scale)))

        neck_w = max(6, int(torso_w * 0.18))
        neck_h = max(6, int(8 * t.scale))
        pygame.draw.rect(surface, skin_col, (cx - neck_w // 2, torso_y - neck_h, neck_w, neck_h), border_radius=3)

        shoulder_col = tuple(max(0, min(255, c + 12)) for c in cloth_col)
        pygame.draw.ellipse(surface, shoulder_col, (torso_x - int(torso_w * 0.1), torso_y - int(torso_h * 0.08), int(torso_w * 1.2), int(torso_h * 0.35)))

        arm_thickness = max(5, int(12 * t.scale))
        upper_len = int(torso_h * 0.6)
        lower_len = int(torso_h * 0.55)
        left_sh_x = torso_x
        left_sh_y = torso_y + int(torso_h * 0.2)
        elbow_lx = left_sh_x - int(upper_len * 0.6)
        elbow_ly = left_sh_y + int(upper_len * 0.45)
        hand_lx = elbow_lx - int(lower_len * 0.55)
        hand_ly = elbow_ly + int(lower_len * 0.2)
        pygame.draw.line(surface, cloth_col, (left_sh_x, left_sh_y), (elbow_lx, elbow_ly), arm_thickness)
        pygame.draw.line(surface, skin_col, (elbow_lx, elbow_ly), (hand_lx, hand_ly), arm_thickness - 2)
        pygame.draw.circle(surface, skin_col, (hand_lx, hand_ly), max(4, int(6 * t.scale)))

        right_sh_x = torso_x + torso_w
        right_sh_y = left_sh_y
        elbow_rx = right_sh_x + int(upper_len * 0.6)
        elbow_ry = right_sh_y + int(upper_len * 0.45)
        hand_rx = elbow_rx + int(lower_len * 0.55)
        hand_ry = elbow_ry + int(lower_len * 0.2)
        pygame.draw.line(surface, cloth_col, (right_sh_x, right_sh_y), (elbow_rx, elbow_ry), arm_thickness)
        pygame.draw.line(surface, skin_col, (elbow_rx, elbow_ry), (hand_rx, hand_ry), arm_thickness - 2)
        pygame.draw.circle(surface, skin_col, (hand_rx, hand_ry), max(4, int(6 * t.scale)))

        thigh_w = max(8, int(torso_w * 0.22))
        thigh_h = int(height * 0.28)
        shin_h = int(height * 0.2)
        leg_y = torso_y + torso_h
        lx = cx - int(torso_w * 0.22)
        pygame.draw.rect(surface, (40, 40, 40), (lx - thigh_w // 2, leg_y, thigh_w, thigh_h), border_radius=6)
        pygame.draw.rect(surface, (30, 30, 30), (lx - thigh_w // 2, leg_y + thigh_h, thigh_w, shin_h), border_radius=6)
        pygame.draw.rect(surface, (20, 20, 20), (lx - thigh_w // 2, leg_y + thigh_h + shin_h, thigh_w, max(8, int(10 * t.scale))), border_radius=4)
        rx = cx + int(torso_w * 0.22)
        pygame.draw.rect(surface, (40, 40, 40), (rx - thigh_w // 2, leg_y, thigh_w, thigh_h), border_radius=6)
        pygame.draw.rect(surface, (30, 30, 30), (rx - thigh_w // 2, leg_y + thigh_h, thigh_w, shin_h), border_radius=6)
        pygame.draw.rect(surface, (20, 20, 20), (rx - thigh_w // 2, leg_y + thigh_h + shin_h, thigh_w, max(8, int(10 * t.scale))), border_radius=4)

        bar_w = base_w
        bar_h = max(6, int(10 * t.scale))
        bar_x = cx - bar_w // 2
        bar_y = torso_y + torso_h + thigh_h + shin_h + max(4, int(6 * t.scale))
        pygame.draw.rect(surface, (60, 60, 60), (bar_x, bar_y, bar_w, bar_h), border_radius=6)
        if t.alive:
            fill = int((t.body.hits_remaining / float(t.body.max_hits)) * bar_w)
            pygame.draw.rect(surface, (200, 70, 70), (bar_x, bar_y, fill, bar_h), border_radius=6)
        else:
            pygame.draw.rect(surface, (80, 80, 80), (bar_x, bar_y, bar_w, bar_h), border_radius=6)
        label = font.render(f"{t.body.hits_remaining if t.body.hits_remaining > 0 else 0}", True, (240, 240, 240))
        lbl_rect = label.get_rect(center=(cx, bar_y + bar_h + 16))
        surface.blit(label, lbl_rect)

        if t.target_type == 'healer' and t.alive:
            plus_color = (230, 250, 230)
            px = cx
            py = torso_y + torso_h // 2
            size = max(6, int(10 * t.scale))
            pygame.draw.rect(surface, plus_color, (px - size // 6, py - size, size // 3, size * 2))
            pygame.draw.rect(surface, plus_color, (px - size, py - size // 6, size * 2, size // 3))
        if t.target_type == 'protector' and t.alive:
            ring_color = (120, 200, 255) if t.shielded else (70, 120, 160)
            ring_radius = int(max(torso_w, torso_h) * 0.9)
            pygame.draw.circle(surface, ring_color, (cx, torso_y + torso_h // 2), ring_radius, max(2, int(3 * t.scale)))
        if t.target_type == 'respawner' and not t.alive:
            rt = getattr(t, "respawn_timer", None)
            if rt is not None:
                try:
                    txt = font.render(f"{max(0, int(math.ceil(rt)))}", True, (200, 200, 255))
                    surface.blit(txt, (sx + scaled_head_radius + 6, sy - scaled_head_radius))
                except Exception:
                    pass

        t._torso_rect = (torso_x, torso_y, torso_w, torso_h)

    def draw_crosshair(self, surface):
        x, y = self.crosshair_pos
        color = (255, 200, 80)
        pygame.draw.line(surface, color, (x - 20, y), (x - 8, y), 3)
        pygame.draw.line(surface, color, (x + 8, y), (x + 20, y), 3)
        pygame.draw.line(surface, color, (x, y - 20), (x, y - 8), 3)
        pygame.draw.line(surface, color, (x, y + 8), (x, y + 20), 3)
        pygame.draw.circle(surface, (255, 255, 255), (x, y), 3)

    def draw_effects(self, surface):
        for x, y, rem, col in self.hit_feedback:
            t = rem / 0.28
            t = clamp(t, 0.0, 1.0)
            radius = int(28 * t) + 4
            width = max(1, int(6 * t))
            pygame.draw.circle(surface, col, (int(x), int(y)), radius, width)

    def render(self, surface):
        surface.fill(BG_COLOR)
        targets_sorted_draw = sorted(self.backend.get_targets(), key=lambda t: t.depth, reverse=True)
        for t in targets_sorted_draw:
            self.draw_person(surface, t)

        self.draw_hud(surface)
        base_pos = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] - 150)
        aim_angle = vec_angle(base_pos, self.crosshair_pos)
        current = self.current_weapon()
        _, gun_rect = current.model.draw(surface, base_pos, aim_angle, scale=1.0)
        self.draw_crosshair(surface)
        self.draw_effects(surface)

        if self.game_state == 'won':
            txt = big_font.render("YOU WIN!", True, (180, 255, 180))
            r = txt.get_rect(center=(WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2))
            surface.blit(txt, r)
        elif self.game_state == 'lost':
            txt = big_font.render("YOU LOSE!", True, (255, 140, 120))
            r = txt.get_rect(center=(WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2))
            surface.blit(txt, r)

        return gun_rect


# --- utility ---
def vec_angle(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return math.degrees(math.atan2(-dy, dx))


# --- main ---
def main():
    global screen
    backend = Backend(WINDOW_SIZE)
    frontend = Frontend(screen, backend)

    # music
    try:
        if os.path.exists(MUSIC_FILE):
            try:
                pygame.mixer.music.load(MUSIC_FILE)
                pygame.mixer.music.set_volume(0.2)
                pygame.mixer.music.play(loops=-1)
            except Exception as e:
                print(f"Warning: failed to play '{MUSIC_FILE}': {e}")
        else:
            print(f"Hint: background music file '{MUSIC_FILE}' not found.")
    except Exception:
        pass

    running = True
    last_time = pygame.time.get_ticks()

    while running:
        now = pygame.time.get_ticks()
        dt = (now - last_time) / 1000.0
        last_time = now

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                    break
                elif event.key == pygame.K_r:
                    # restart
                    frontend = Frontend(screen, backend=Backend(WINDOW_SIZE))
                    backend = frontend.backend
                elif event.key == pygame.K_e:
                    frontend.reload_current()
                elif event.key == pygame.K_1:
                    frontend.switch_weapon(0)
                elif event.key == pygame.K_2:
                    frontend.switch_weapon(1)
                elif event.key == pygame.K_3:
                    if frontend.gatling_unlocked:
                        frontend.switch_weapon(frontend.gatling_index)
                elif event.key == pygame.K_l:
                    if frontend.special_choice_available and (not frontend.special_choice_used):
                        frontend.restore_all_weapons_to_initial()
                        frontend.special_choice_used = True
                        frontend.special_choice_available = False
                elif event.key == pygame.K_s:
                    if frontend.special_choice_available and (not frontend.special_choice_used):
                        frontend.slow_spawn_choice()
                        frontend.special_choice_used = True
                        frontend.special_choice_available = False
            elif event.type == pygame.MOUSEMOTION:
                frontend.crosshair_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                frontend.click_fire()
                frontend.start_auto_fire()
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                frontend.stop_auto_fire()

        # auto fire
        if frontend.left_mouse_held and not frontend.is_over():
            w = frontend.current_weapon()
            if w.automatic and w.can_fire():
                frontend.fire()

        frontend.update(dt)

        gun_rect = frontend.render(screen)
        if gun_rect:
            frontend.front_end_exclude = (gun_rect.left - 40, gun_rect.top - 40, gun_rect.right + 40, gun_rect.bottom + 120)

        pygame.display.flip()
        clock.tick(120)

    try:
        pygame.mixer.music.stop()
    except Exception:
        pass
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()