# weapons.py
# 武器模型（视觉）及武器逻辑

import pygame
import math
import random
from typing import List

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
        self.slide_back = max(0.0, min(1.0, self.slide_back))

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
        return muzzle_world, rect


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
        self.bolt = max(0.0, min(1.0, self.bolt))
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
        ang_rad = math.radians(-(total_angle))
        rx = relx * math.cos(ang_rad) - rely * math.sin(ang_rad)
        ry = relx * math.sin(ang_rad) + rely * math.cos(ang_rad)
        muzzle_world = (rect.left + center_local[0] + rx, rect.top + center_local[1] + ry)
        return muzzle_world, rect


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
        bar_x = int(w * 0.72)
        bar_y = int(h * 0.22)
        pygame.draw.rect(gun_surf, (60, 60, 60), (bar_x, bar_y, int(w * 0.24), int(h * 0.12)))
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
        return muzzle_world, rect


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

    def do_fire(self, muzzle_world, muzzle_angle_deg, fire_sound, empty_sound):
        if self.ammo <= 0:
            try:
                empty_sound.play()
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
            fire_sound.play()
        except Exception:
            pass
        return True

    def start_reload(self, reload_sound):
        if self.reloading or self.ammo == self.mag_size or self.reserve <= 0:
            return False
        self.reloading = True
        self.reload_timer = self.reload_time
        try:
            reload_sound.play()
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
            pass