# sounds.py
# 生成各类音效（独立于其他模块）

import pygame
import random
import math
import io
import wave
from array import array

# 音量全局（从常量导入可能循环依赖，直接用固定值）
SFX_VOLUME = 0.16
SAMPLE_RATE_GUN = 44100

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

# 预置音效（供外部使用）
HIT_SOUND = make_delta_hit(duration=0.11, volume=0.68)
DESTROY_SOUND = make_tone(420.0, 0.18, 0.8)
MISS_SOUND = make_tone(160.0, 0.06, 0.4)
PISTOL_FIRE_SFX = make_deep_boom_shot(duration=0.12, volume=0.62)
RIFLE_FIRE_SFX = make_deep_boom_shot(duration=0.20, volume=0.70)
EMPTY_CLICK = make_tone(140.0, 0.08, 0.25)
RELOAD_SFX = make_tone(220.0, 0.28, 0.7)