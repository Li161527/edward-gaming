"""
Aim Trainer — Many moving targets (3-5 simultaneous spawns, constant step size)

Behavior changes per your request:
- Each spawn tick now spawns 3-5 targets simultaneously (subject to capacity and available candidate positions).
- Movement step no longer accelerates: each target moves by the same step_vector each MOVE_INTERVAL (restored).
- Targets are removed immediately when destroyed (no corpses).
- Targets are still not spawned from the candidate position closest to the front end.

Other gameplay:
- Targets advance every MOVE_INTERVAL (0.2s).
- If any target reaches REACH_DISTANCE to the front base before GAME_LENGTH_SECS -> LOSS.
- If the timer ends and no alive targets remain -> WIN, otherwise -> LOSS.

Save as a .py file and run with pygame installed.
"""
import pygame
import random
import math
import sys
import io
import wave
from typing import Tuple, Optional, List
from array import array

# ---------- CONFIG ----------
WINDOW_SIZE = (1600, 1000)
BG_COLOR = (28, 28, 34)
BODY_COLOR = (78, 160, 220)
HIT_BODY_COLOR = (220, 120, 120)
HEAD_COLOR = (250, 210, 150)
EYE_COLOR = (40, 40, 40)
ARM_COLOR = (95, 95, 95)
LEG_COLOR = (50, 50, 50)
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
MOVE_INTERVAL = 0.2      # each target advances every 0.2s
SPAWN_INTERVAL = 1.0     # spawn attempt every 1 second
REACH_DISTANCE = 48      # pixels considered "reached" (collision with front)
MAX_SIMULTANEOUS_ALIVE = 300  # soft cap for performance
MIN_SPAWN_SEPARATION = 160  # min pixel separation between concurrently spawned targets

# Spawn count per tick (user requested 3-5)
SPAWN_MIN = 3
SPAWN_MAX = 5
# ----------------------------

# Initialize pygame + mixer
pygame.init()
try:
    pygame.mixer.init(frequency=44100, size=-16, channels=2)
except Exception:
    pass

screen = pygame.display.set_mode(WINDOW_SIZE)
pygame.display.set_caption("Aim Trainer — Many Moving Targets (fixed step)")

clock = pygame.time.Clock()
font = pygame.font.Font(FONT_NAME, 20)
big_font = pygame.font.Font(FONT_NAME, 48)


def clamp(v, a, b):
    return max(a, min(b, v))


def lerp(a, b, t):
    return a + (b - a) * t


# --- sound helper ---
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


# SFX
"""HIT_SOUND = make_tone(900.0, 0.06, 0.6)
DESTROY_SOUND = make_tone(420.0, 0.18, 0.8)
MISS_SOUND = make_tone(160.0, 0.06, 0.4)

PISTOL_FIRE_SFX = make_tone(1400.0, 0.06, 0.9)
RIFLE_FIRE_SFX = make_tone(900.0, 0.04, 0.95)
EMPTY_CLICK = make_tone(240.0, 0.08, 0.25)
RELOAD_SFX = make_tone(320.0, 0.28, 0.7)
SHELL_EJECT_SFX = make_tone(800.0, 0.04, 0.25)"""

SAMPLE_RATE_GUN = 44100

def make_deep_boom_shot(duration=0.20, volume=0.70):
    """M14风格大口径低沉枪声，主频100Hz以内"""
    n = int(SAMPLE_RATE_GUN * duration)
    buf = array('h')
    for i in range(n):
        t = i / SAMPLE_RATE_GUN

        if t < 0.005:
            attack_env = t / 0.005
        else:
            attack_env = math.exp( -(t - 0.005) * 11 )

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
    """三角洲行动人体命中闷响"""
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


# ========== 最终音效定义（直接覆盖你原来整段）==========
"""HIT_SOUND = make_delta_hit(duration=0.09, volume=0.65)
DESTROY_SOUND = make_tone(420.0, 0.18, 0.8)
MISS_SOUND = make_tone(160.0, 0.06, 0.4)

PISTOL_FIRE_SFX = make_deep_boom_shot(duration=0.12, volume=0.62)
RIFLE_FIRE_SFX = make_deep_boom_shot(duration=0.20, volume=0.70)
EMPTY_CLICK = make_tone(240.0, 0.08, 0.25)
RELOAD_SFX = make_tone(320.0, 0.28, 0.7)
SHELL_EJECT_SFX = make_tone(800.0, 0.04, 0.25)"""

HIT_SOUND = make_delta_hit(duration=0.11, volume=0.68)
DESTROY_SOUND = make_tone(420.0, 0.18, 0.8)
MISS_SOUND = make_tone(160.0, 0.06, 0.4)

PISTOL_FIRE_SFX = make_deep_boom_shot(duration=0.12, volume=0.62)
RIFLE_FIRE_SFX = make_deep_boom_shot(duration=0.20, volume=0.70)
EMPTY_CLICK = make_tone(240.0, 0.08, 0.25)
RELOAD_SFX = make_tone(320.0, 0.28, 0.7)
SHELL_EJECT_SFX = make_tone(800.0, 0.04, 0.25)





# --- collision helpers ---
def point_in_sphere(px, py, sx, sy, r):
    return (px - sx) ** 2 + (py - sy) ** 2 <= r * r


def point_in_cone(px, py, cx, base_y, base_w, height):
    if py < base_y or py > base_y + height:
        return False
    frac = (py - base_y) / height
    half_width_at_y = (1.0 - frac) * (base_w / 2.0)
    return abs(px - cx) <= half_width_at_y


# --- Target classes (Backend) ---
class ConeBody:
    def __init__(self, pos):
        self.center = pos
        self.hits_remaining = CONE_MAX_HITS
        self.alive = True

    def reset(self, pos):
        self.center = pos
        self.hits_remaining = CONE_MAX_HITS
        self.alive = True

    def damage(self, amount=1):
        self.hits_remaining = max(0, self.hits_remaining - amount)
        if self.hits_remaining == 0:
            self.alive = False


class PersonTarget:
    """
    Movement behavior:
    - move_vector is the per-step displacement applied every MOVE_INTERVAL
    - steps_remaining is used for initial step sizing; movement is constant (no acceleration)
    """

    def __init__(self, pos: Tuple[int, int], depth: float = 0.0, move_vector: Tuple[float, float] = (0.0, 0.0),
                 steps_remaining: int = 0):
        self.center = pos
        self.depth = clamp(depth, 0.0, 1.0)
        self.body = ConeBody(pos)
        self.move_vector = (float(move_vector[0]), float(move_vector[1]))
        self.steps_remaining = int(steps_remaining)
        self.update_geometry()
        self.alive = True

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

    def reset(self, pos: Tuple[int, int], depth: float = 0.0, move_vector=(0.0, 0.0), steps_remaining=0):
        self.center = pos
        self.depth = clamp(depth, 0.0, 1.0)
        self.body.reset(pos)
        self.move_vector = (float(move_vector[0]), float(move_vector[1]))
        self.steps_remaining = int(steps_remaining)
        self.update_geometry()
        self.alive = True

    def advance_step(self):
        if not self.alive:
            return
        sx, sy = self.move_vector
        cx, cy = self.center
        self.center = (cx + sx, cy + sy)
        self.steps_remaining = max(0, self.steps_remaining - 1)
        # NOTE: restored behavior: do NOT change the move_vector (no acceleration)
        self.update_geometry()

    def damage_body(self, amount=1):
        if not self.body.alive:
            return
        self.body.damage(amount)
        if not self.body.alive:
            self.alive = False

    def destroy_by_head(self):
        self.body.alive = False
        self.alive = False

    def bounding_box(self):
        cx, cy = self.screen_center
        half_w = int(self.cone_base_w / 2) + 20
        top_y = int(self.cone_top_y - SPHERE_RADIUS * self.scale * 1.3)
        bottom_y = int(self.cone_top_y + self.cone_height + 40)
        return (cx - half_w, top_y, cx + half_w, bottom_y)


# --- Backend (spawning / movement) ---
class Backend:
    def __init__(self, screen_size):
        self.screen_w, self.screen_h = screen_size
        self.targets: List[PersonTarget] = []
        self.spawn_margin = MARGIN
        self.move_acc = 0.0
        self.spawn_acc = 0.0
        self.reached = False
        self.total_spawned = 0

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
        """
        Spawn n_to_spawn targets at far-end candidate positions simultaneously,
        excluding the candidate position that is closest to the front_pos.
        Avoid positions that are too close to currently alive targets or duplicate among spawns.
        """
        if n_to_spawn <= 0:
            return []

        # cap total alive to prevent runaway
        alive_now = len([t for t in self.targets if t.alive])
        if alive_now >= MAX_SIMULTANEOUS_ALIVE:
            return []

        candidates = self.candidate_positions()
        fx, fy = front_pos

        # compute distances to front_pos and sort ascending to find the closest
        candidates_with_dist = [(p, math.hypot(p[0] - fx, p[1] - fy)) for p in candidates]
        candidates_with_dist.sort(key=lambda x: x[1])  # closest first

        # remove the closest candidate (user requested not to spawn from closest part)
        if candidates_with_dist:
            candidates_with_dist.pop(0)

        # now sort by distance descending (farthest first)
        candidates_with_dist.sort(key=lambda x: x[1], reverse=True)
        ordered_candidates = [p for (p, _) in candidates_with_dist]

        spawned = []
        alive_positions = [t.screen_center for t in self.targets if t.alive]

        for p in ordered_candidates:
            if len(spawned) >= n_to_spawn:
                break
            # skip if too close to existing alive positions or already chosen
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

            # compute depth
            d = math.hypot(p[0] - fx, p[1] - fy)
            min_cx, max_cx, min_cy, max_cy = self.compute_spawn_bounds()
            max_possible = math.hypot(max_cx - min_cx, max_cy - min_cy) or 1.0
            depth = clamp(d / max_possible, 0.0, 1.0)

            # compute steps so target would reach at end of remaining_time_s if not destroyed
            steps_total = max(1, int(max(0.0, remaining_time_s) / MOVE_INTERVAL))
            sx = (fx - p[0]) / float(steps_total)
            sy = (fy - p[1]) / float(steps_total)

            t = PersonTarget(p, depth=depth, move_vector=(sx, sy), steps_remaining=steps_total)
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
        # Remove dead targets immediately (no corpses)
        self.targets = [t for t in self.targets if t.alive]

    def update(self, dt: float, front_pos: Tuple[int, int], remaining_time_s: float):
        """
        - Spawn 3-5 targets simultaneously (per SPAWN_INTERVAL tick) at far ends excluding the closest candidate.
        - Advance all alive targets by their (constant) move_vector every MOVE_INTERVAL.
        - Remove dead targets immediately (no corpse).
        - Mark self.reached True if any alive target gets within REACH_DISTANCE of front_pos.
        """
        # Clean up dead immediately
        self.remove_dead()

        # spawn logic
        if remaining_time_s > 0.0:
            self.spawn_acc += dt
            while self.spawn_acc >= SPAWN_INTERVAL:
                self.spawn_acc -= SPAWN_INTERVAL
                spawn_n = random.randint(SPAWN_MIN, SPAWN_MAX)
                alive_now = len([t for t in self.targets if t.alive])
                capacity = max(0, MAX_SIMULTANEOUS_ALIVE - alive_now)
                spawn_n = min(spawn_n, capacity, len(self.candidate_positions()) - 1)  # minus one to exclude closest
                if spawn_n <= 0:
                    break
                self.spawn_many_farthest(front_pos, remaining_time_s, spawn_n)

        # movement logic
        if not self.targets:
            return

        self.move_acc += dt
        while self.move_acc >= MOVE_INTERVAL:
            self.move_acc -= MOVE_INTERVAL
            # advance each alive target
            for t in list(self.targets):
                if not t.alive:
                    continue
                t.advance_step()  # constant step, restored behavior
                fx, fy = front_pos
                dist = math.hypot(t.screen_center[0] - fx, t.screen_center[1] - fy)
                if dist <= REACH_DISTANCE:
                    self.reached = True
                    return
            # After movement pass, remove dead ones
            self.remove_dead()

    def alive_count(self):
        return sum(1 for t in self.targets if t.alive)


# --- Visual / Gun Model Helpers ---
def vec_angle(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return math.degrees(math.atan2(-dy, dx))


# --- Gun models (kept similar) ---
class GunModel:
    def __init__(self):
        self.recoil = 0.0
        self.rot_recoil = 0.0
        self.shells = []
        self.muzzle_flashes = []
        self.tracers = []

    def update(self, dt):
        if self.recoil > 0:
            self.recoil = max(0.0, self.recoil - dt * self.recoil * 6.0 - dt * 60.0)
        if self.rot_recoil > 0:
            self.rot_recoil = max(0.0, self.rot_recoil - dt * 160.0)
        for s in list(self.shells):
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            s[3] += 700.0 * dt
            s[4] += s[5] * dt
            s[6] -= dt
            if s[6] <= 0:
                try:
                    self.shells.remove(s)
                except ValueError:
                    pass
        for mf in list(self.muzzle_flashes):
            mf[1] -= dt
            if mf[1] <= 0:
                try:
                    self.muzzle_flashes.remove(mf)
                except ValueError:
                    pass
        for tr in list(self.tracers):
            tr[3] -= dt
            if tr[3] <= 0:
                try:
                    self.tracers.remove(tr)
                except ValueError:
                    pass

    def spawn_shell(self, pos, dir_angle_deg):
        ang = math.radians(dir_angle_deg + random.uniform(-20, 20))
        speed = random.uniform(240.0, 420.0)
        vx = math.cos(ang) * speed
        vy = -math.sin(ang) * speed
        rot = random.uniform(-720, 720)
        self.shells.append([pos[0], pos[1], vx, vy, 0.0, rot, 1.2])
        try:
            SHELL_SFX = make_tone(1200.0 + random.uniform(-200, 200), 0.04, 0.18)
            SHELL_SFX.play()
        except Exception:
            pass

    def add_muzzle_flash(self, pos):
        self.muzzle_flashes.append([pos, 0.08])

    def add_tracer(self, start, end, duration=0.12):
        self.tracers.append([start, end, duration, duration])


class PistolModel(GunModel):
    def __init__(self):
        super().__init__()
        self.slide_back = 0.0
        self.slide_vel = 0.0
        self.slide_speed = 8.0
        self.width = 480
        self.height = 120
        self.muzzle_local = (0.82, 0.28)

    def on_fire(self, muzzle_world, muzzle_angle_deg):
        self.recoil += 8.0
        self.rot_recoil += random.uniform(1.8, 4.2)
        self.slide_vel = 1.0
        self.spawn_shell(muzzle_world, muzzle_angle_deg - 90)
        self.add_muzzle_flash(muzzle_world)

    def update(self, dt):
        super().update(dt)
        self.slide_back += self.slide_vel * dt
        self.slide_vel -= self.slide_back * self.slide_speed * dt * 2.0
        self.slide_vel *= (1.0 - dt * 6.0)
        self.slide_back = clamp(self.slide_back, 0.0, 1.0)

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
        self.width = 820
        self.height = 160
        self.muzzle_local = (0.92, 0.30)

    def on_fire(self, muzzle_world, muzzle_angle_deg):
        self.recoil += 4.0
        self.rot_recoil += random.uniform(2.2, 5.0)
        self.bolt_vel = 1.2 + random.uniform(0.0, 0.4)
        self.spawn_shell(muzzle_world, muzzle_angle_deg - 100)
        self.add_muzzle_flash(muzzle_world)

    def update(self, dt):
        super().update(dt)
        self.bolt += self.bolt_vel * dt
        self.bolt_vel -= self.bolt * 8.0 * dt
        self.bolt_vel *= (1.0 - dt * 8.0)
        self.bolt = clamp(self.bolt, 0.0, 1.0)
        self.sway_phase += dt * 1.2

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


# --- Weapon (logic/state) ---
class Weapon:
    def __init__(self, name, mag_size, reserve, fire_rate, automatic, reload_time, model: GunModel):
        self.name = name
        self.mag_size = mag_size
        self.ammo = mag_size
        self.reserve = reserve
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
        self.cooldown = 1.0 / self.fire_rate
        self.model.on_fire(muzzle_world, muzzle_angle_deg)
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
        self.model.update(dt)


# --- Frontend (UI / player) ---
class Frontend:
    def __init__(self, screen, backend: Backend):
        self.screen = screen
        self.backend = backend
        self.points = 0
        self.hits = 0
        self.shots = 0
        self.start_time = pygame.time.get_ticks()
        self.duration_ms = GAME_LENGTH_SECS * 1000
        # weapons
        self.pistol_model = PistolModel()
        self.rifle_model = RifleModel()
        self.weapons = [
            Weapon("Pistol", mag_size=12, reserve=48, fire_rate=5.0, automatic=False, reload_time=1.3, model=self.pistol_model),
            Weapon("Rifle", mag_size=30, reserve=120, fire_rate=12.0, automatic=True, reload_time=2.4, model=self.rifle_model),
        ]
        self.current_weapon_idx = 0
        self.crosshair_pos = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2)
        self.left_mouse_held = False
        self.front_end_exclude = self.compute_frontend_exclusion_rect()
        self.game_state = 'playing'  # 'playing', 'won', 'lost'

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

    def update(self, dt):
        # update weapons
        for w in self.weapons:
            w.update(dt)

        # backend update
        base_pos = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] - 150)
        remaining_time_s = max(0.0, (self.duration_ms - (pygame.time.get_ticks() - self.start_time)) / 1000.0)
        self.backend.update(dt, base_pos, remaining_time_s)

        # immediate lose if reached
        if self.backend.reached and self.game_state == 'playing':
            self.game_state = 'lost'

        # if time over, evaluate win/loss
        if (pygame.time.get_ticks() - self.start_time) >= self.duration_ms and self.game_state == 'playing':
            alive = self.backend.alive_count()
            if alive == 0:
                self.game_state = 'won'
            else:
                self.game_state = 'lost'

    def current_weapon(self):
        return self.weapons[self.current_weapon_idx]

    def fire(self):
        if self.is_over():
            return
        w = self.current_weapon()
        base_pos = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] - 150)
        aim_angle = vec_angle(base_pos, self.crosshair_pos)
        muzzle_world, _ = w.model.draw(pygame.Surface((1, 1)), base_pos, aim_angle, scale=1.0)
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
                    self.hits += 1
                    t.destroy_by_head()
                    self.points += 1
                    try:
                        DESTROY_SOUND.play()
                    except Exception:
                        pass
                    hit_any = True
                    break
                cx = t.screen_center[0]
                if point_in_cone(mx, my, cx, t.cone_top_y, t.cone_base_w, t.cone_height):
                    self.hits += 1
                    t.damage_body(1)
                    try:
                        HIT_SOUND.play()
                    except Exception:
                        pass
                    if not t.alive:
                        self.points += 1
                        try:
                            DESTROY_SOUND.play()
                        except Exception:
                            pass
                    hit_any = True
                    break
            if not hit_any:
                try:
                    MISS_SOUND.play()
                except Exception:
                    pass
            w.model.add_tracer(muzzle_world, self.crosshair_pos, duration=0.14)
            # remove dead immediately (no corpses)
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

    # --- render ---
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

        # right HUD
        w = self.current_weapon()
        txt_weapon = font.render(f"Weapon: {w.name}", True, color)
        txt_ammo = font.render(f"Ammo: {w.ammo}/{w.mag_size}  Reserve: {w.reserve}", True, color)
        hint = font.render("1=Pistol  2=Rifle  E=Reload  R=Restart", True, (200, 200, 200))
        surface.blit(txt_weapon, (WINDOW_SIZE[0] - 380, top))
        surface.blit(txt_ammo, (WINDOW_SIZE[0] - 380, top + gap))
        surface.blit(hint, (WINDOW_SIZE[0] - 720, WINDOW_SIZE[1] - 40))

    def draw_person(self, surface, t: PersonTarget):
        cx = int(t.screen_center[0])
        cy = int(t.screen_center[1])
        base_y = int(t.cone_top_y)
        base_w = int(t.cone_base_w)
        height = int(t.cone_height)
        depth_tint = int(lerp(0, 60, t.depth))
        if not t.alive:
            body_col = (110, 110, 110)
        else:
            base_col = BODY_COLOR if t.body.hits_remaining == CONE_MAX_HITS else HIT_BODY_COLOR
            body_col = (max(0, base_col[0] - depth_tint), max(0, base_col[1] - depth_tint),
                        max(0, base_col[2] - depth_tint))

        left_base = (cx - base_w // 2, base_y)
        right_base = (cx + base_w // 2, base_y)
        apex = (cx, base_y + height)
        pygame.draw.polygon(surface, (max(0, body_col[0] - 18), max(0, body_col[1] - 18), max(0, body_col[2] - 18)),
                            [left_base, right_base, apex])
        pygame.draw.polygon(surface, body_col, [left_base, right_base, apex])
        fold_color = (min(255, body_col[0] + 20), min(255, body_col[1] + 20), min(255, body_col[2] + 20))
        pygame.draw.polygon(surface, fold_color,
                            [(cx, base_y + int(height * 0.12)), (cx - base_w // 8, base_y + height // 2),
                             (cx + base_w // 8, base_y + height // 2)])
        arm_y = int(t.arm_y)
        arm_len = int(base_w / 1.6)
        left_arm_start = (cx - base_w // 2 + 6, arm_y)
        left_arm_end = (cx - base_w // 2 - int(arm_len * 0.2), arm_y + 36)
        right_arm_start = (cx + base_w // 2 - 6, arm_y)
        right_arm_end = (cx + base_w // 2 + int(arm_len * 0.2), arm_y + 36)
        pygame.draw.line(surface, ARM_COLOR, left_arm_start, left_arm_end, max(3, int(8 * t.scale)))
        pygame.draw.line(surface, ARM_COLOR, right_arm_start, right_arm_end, max(3, int(8 * t.scale)))
        leg_w = max(6, base_w // 8)
        leg_h = max(10, int(26 * t.scale))
        leg_x_left = cx - base_w // 6 - leg_w // 2
        leg_x_right = cx + base_w // 6 - leg_w // 2
        leg_y = apex[1] + 8
        pygame.draw.rect(surface, LEG_COLOR, (leg_x_left, leg_y, leg_w, leg_h), border_radius=6)
        pygame.draw.rect(surface, LEG_COLOR, (leg_x_right, leg_y, leg_w, leg_h), border_radius=6)
        sx, sy = int(t.sphere_center[0]), int(t.sphere_center[1])
        scaled_head_radius = max(6, int(SPHERE_RADIUS * t.scale))
        if t.alive:
            pygame.draw.circle(surface, (255, 245, 225), (sx, sy), scaled_head_radius + max(3, int(6 * t.scale)))
            pygame.draw.circle(surface, HEAD_COLOR, (sx, sy), scaled_head_radius)
            eye_offset_x = max(6, scaled_head_radius // 3)
            eye_offset_y = -6
            pygame.draw.circle(surface, EYE_COLOR, (sx - eye_offset_x, sy + eye_offset_y), max(2, int(6 * t.scale)))
            pygame.draw.circle(surface, EYE_COLOR, (sx + eye_offset_x, sy + eye_offset_y), max(2, int(6 * t.scale)))
            smile_rect = pygame.Rect(sx - max(8, int(14 * t.scale)), sy + max(2, int(4 * t.scale)),
                                     max(16, int(28 * t.scale)), max(8, int(16 * t.scale)))
            pygame.draw.arc(surface, EYE_COLOR, smile_rect, math.radians(18), math.radians(162), max(1, int(2 * t.scale)))
        else:
            pygame.draw.circle(surface, (130, 130, 130), (sx, sy), scaled_head_radius, 2)

        bar_w = base_w
        bar_h = max(6, int(10 * t.scale))
        bar_x = cx - bar_w // 2
        bar_y = apex[1] + 8 + leg_h + 10
        pygame.draw.rect(surface, (60, 60, 60), (bar_x, bar_y, bar_w, bar_h), border_radius=6)
        if t.alive:
            fill = int((t.body.hits_remaining / CONE_MAX_HITS) * bar_w)
            pygame.draw.rect(surface, (200, 70, 70), (bar_x, bar_y, fill, bar_h), border_radius=6)
        else:
            pygame.draw.rect(surface, (80, 80, 80), (bar_x, bar_y, bar_w, bar_h), border_radius=6)
        label = font.render(f"{t.body.hits_remaining if t.body.hits_remaining > 0 else 0}", True, (240, 240, 240))
        lbl_rect = label.get_rect(center=(cx, bar_y + bar_h + 16))
        surface.blit(label, lbl_rect)

    def draw_crosshair(self, surface):
        x, y = self.crosshair_pos
        color = (255, 200, 80)
        pygame.draw.line(surface, color, (x - 20, y), (x - 8, y), 3)
        pygame.draw.line(surface, color, (x + 8, y), (x + 20, y), 3)
        pygame.draw.line(surface, color, (x, y - 20), (x, y - 8), 3)
        pygame.draw.line(surface, color, (x, y + 8), (x, y + 20), 3)
        pygame.draw.circle(surface, (255, 255, 255), (x, y), 3)

    def draw_effects(self, surface):
        for w in self.weapons:
            model = w.model
            for tr in model.tracers:
                t = max(0.0, tr[3] / tr[2]) if tr[2] > 0 else 0.0
                col = (255, 220, 120)
                pygame.draw.line(surface, col, tr[0], tr[1], max(1, int(8 * t)))
            for mf in model.muzzle_flashes:
                size = int(36 * (mf[1] / 0.08))
                pygame.draw.circle(surface, (255, 240, 140), (int(mf[0][0]), int(mf[0][1])), size)
            for s in model.shells:
                sx, sy, vx, vy, rot, spin, timer = s
                pygame.draw.ellipse(surface, (210, 180, 80), (sx - 6, sy - 3, 12, 6))

    def render(self, surface):
        surface.fill(BG_COLOR)
        targets_sorted_draw = sorted(self.backend.get_targets(), key=lambda t: t.depth, reverse=True)
        for t in targets_sorted_draw:
            self.draw_person(surface, t)

        self.draw_hud(surface)
        base_pos = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] - 150)
        aim_angle = vec_angle(base_pos, self.crosshair_pos)
        current = self.current_weapon()
        muzzle_world, gun_rect = current.model.draw(surface, base_pos, aim_angle, scale=1.0)
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


# --- Main wiring ---
def main():
    global screen
    backend = Backend(WINDOW_SIZE)
    frontend = Frontend(screen, backend)

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
                    # restart game
                    frontend.points = 0
                    frontend.hits = 0
                    frontend.shots = 0
                    frontend.start_time = pygame.time.get_ticks()
                    frontend.game_state = 'playing'
                    backend.targets = []
                    backend.total_spawned = 0
                    backend.move_acc = 0.0
                    backend.spawn_acc = 0.0
                    backend.reached = False
                elif event.key == pygame.K_e:
                    frontend.reload_current()
                elif event.key == pygame.K_1:
                    frontend.switch_weapon(0)
                elif event.key == pygame.K_2:
                    frontend.switch_weapon(1)
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

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()