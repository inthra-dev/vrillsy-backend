import json, random
from typing import List, Dict
import numpy as np
import librosa

def load_cfg(cfg_path: str) -> Dict:
    try:
        with open(cfg_path, "r") as f: return json.load(f)
    except Exception: return {}

def detect_beats_and_onsets(y, sr):
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, units="time", backtrack=True)
    return np.array(beats), np.array(onsets)

def snap_time(t, onsets, snap_ms=60):
    if onsets.size==0: return t
    idx = np.argmin(np.abs(onsets - t))
    if abs(onsets[idx]-t) <= (snap_ms/1000.0):
        return float(onsets[idx])
    return float(t)

def pro_cutplan(beat_times: np.ndarray, onsets: np.ndarray, cfg: Dict, total_duration: float) -> List[float]:
    db_every = int(cfg.get("downbeat_every", 4))
    durs = cfg.get("durations_beats", [0.5,1,1,2,4])
    wts  = cfg.get("durations_weights", [0.10,0.50,0.25,0.10,0.05])
    jitter = float(cfg.get("jitter_ms", 45))
    snap = float(cfg.get("snap_ms", 60))
    longp = float(cfg.get("long_hold_prob", 0.15))
    if sum(wts) <= 0: wts = [1/len(durs)]*len(durs)
    wts = np.array(wts)/sum(wts)

    grid = beat_times if len(beat_times) >= 4 else np.arange(0, total_duration, 0.5)
    cuts=[0.0]; beat_idx=0
    while cuts[-1] < total_duration - 0.2:
        prefer_downbeat = (beat_idx % db_every == 0)
        dur_beats = float(np.random.choice(durs, p=wts))
        if random.random() < longp:
            dur_beats += float(np.random.choice([1,2]))
        if beat_idx+1 < len(grid):
            local_beat_sec = float(np.mean(np.diff(grid[max(0,beat_idx-2):min(len(grid)-1,beat_idx+2)])) or 0.5)
        else:
            local_beat_sec = float(np.mean(np.diff(grid)) if len(grid)>1 else 0.5)
        target = cuts[-1] + dur_beats*local_beat_sec
        target += (random.random()*2-1)*(jitter/1000.0)
        target = snap_time(max(0.0, target), onsets, snap_ms=snap)
        target = max(target, cuts[-1] + 0.15)
        if target >= total_duration: break
        if prefer_downbeat and len(grid):
            idx = int(np.argmin(np.abs(grid - target)))
            if abs(grid[idx]-target) < 0.12:
                target = float(grid[idx])
        cuts.append(float(target))
        while beat_idx < len(grid) and grid[beat_idx] <= target:
            beat_idx += 1
    if cuts[-1] < total_duration: cuts.append(float(total_duration))
    return cuts
