# main.py
# 前端界面、游戏状态、事件处理及主循环

import pygame
import math
import sys
import os
from typing import List, Tuple

# ---------- 必须在使用 sounds 之前初始化 mixer ----------
pygame.init()
try:
    pygame.mixer.init(frequency=44100, size=-16, channels=2)
except Exception:
    pass

# 然后导入自定义模块
from constants import *
from sounds import *
from targets import *
from backend import *
from weapons import *

from constants import (
    WINDOW_SIZE, BG_COLOR, BODY_COLOR, HIT_BODY_COLOR,
    HEAD_COLOR, EYE_COLOR, HUD_COLOR, CONE_BASE_WIDTH,
    CONE_HEIGHT, CONE_MAX_HITS, SPHERE_RADIUS,
    GAME_LENGTH_SECS, FONT_NAME, REACH_DISTANCE,
    SLOW_SPAWN_MULTIPLIER, SLOW_SPAWN_DURATION,
    MUSIC_FILE, clamp, lerp
)
from sounds import (
    HIT_SOUND, DESTROY_SOUND, MISS_SOUND,
    PISTOL_FIRE_SFX, RIFLE_FIRE_SFX,
    EMPTY_CLICK, RELOAD_SFX
)
from targets import PersonTarget
from backend import Backend
from weapons import PistolModel, RifleModel, GatlingModel, Weapon

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


def vec_angle(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return math.degrees(math.atan2(-dy, dx))


def point_in_sphere(px, py, sx, sy, r):
    return (px - sx) ** 2 + (py - sy) ** 2 <= r * r


def point_in_rect(px, py, rx, ry, rw, rh):
    return (px >= rx) and (px <= rx + rw) and (py >= ry) and (py <= ry + rh)


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

        w1 = Weapon("Pistol", mag_size=24, reserve=96, fire_rate=5.0,
                    automatic=False, reload_time=1.3, model=self.pistol_model)
        w2 = Weapon("Rifle", mag_size=90, reserve=360, fire_rate=12.0,
                    automatic=True, reload_time=2.4, model=self.rifle_model)
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
            g = Weapon("Gatling", mag_size=240, reserve=960, fire_rate=24.0,
                       automatic=True, reload_time=4.8, model=self.gatling_model)
            self.weapons.append(g)
            self.gatling_unlocked = True
            self.gatling_index = len(self.weapons) - 1

    def update(self, dt):
        for w in self.weapons:
            w.update(dt)

        base_pos = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] - 150)
        remaining_time_s = max(0.0, (self.duration_ms - (pygame.time.get_ticks() - self.start_time)) / 1000.0)

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

        if elapsed_s >= 60.0 and (not self.special_choice_used):
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

        # 选择合适的射击音效
        if w.name == "Pistol":
            fire_sfx = PISTOL_FIRE_SFX
        else:
            fire_sfx = RIFLE_FIRE_SFX

        if not w.can_fire():
            if w.ammo == 0 and not w.reloading:
                try:
                    EMPTY_CLICK.play()
                except Exception:
                    pass
            return False

        fired = w.do_fire(muzzle_world, aim_angle, fire_sfx, EMPTY_CLICK)
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
        self.current_weapon().start_reload(RELOAD_SFX)

    def restore_all_weapons_to_initial(self):
        for w in self.weapons:
            w.restore_initial_state()

    def slow_spawn_choice(self):
        self.backend.spawn_interval_multiplier = SLOW_SPAWN_MULTIPLIER
        self.backend.spawn_slow_timer = SLOW_SPAWN_DURATION

    # ---------- 渲染 ----------
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


def main():
    global screen
    backend = Backend(WINDOW_SIZE)
    frontend = Frontend(screen, backend)

    # 背景音乐
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

        # 自动连发
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