from __future__ import annotations
import numpy as np
from typing import List, Tuple

def _distribute_segments(total_s: float, beats: List[float], hook_max_s: float = 1.5) -> List[Tuple[float, float]]:
    total_s = float(max(0.2, total_s))
    beats = sorted([b for b in beats if 0 <= b <= total_s])
    if not beats or beats[0] > 0.0:
        beats = [0.0] + beats
    if beats[-1] < total_s:
        beats = beats + [total_s]

    segs: List[Tuple[float, float]] = []
    hook_end = min(hook_max_s, total_s)

    t = 0.0
    while t < hook_end:
        nt = min(hook_end, t + 0.3)
        segs.append((t, nt))
        t = nt

    cur = hook_end
    i = 0
    while cur < total_s and i < len(beats) - 1:
        while i < len(beats) - 1 and beats[i] < cur:
            i += 1
        if i >= len(beats) - 1:
            break
        start = max(cur, beats[i])
        base = beats[min(i + 1, len(beats) - 1)] - start
        jitter = 0.25 + 0.35 * (0.5 - float(np.random.rand()))
        dur = max(0.25, min(0.6, base + jitter))
        end = min(total_s, start + dur)
        if end - start >= 0.2:
            segs.append((start, end))
        cur = end
        i += 1

    while segs and segs[-1][1] < total_s:
        start = segs[-1][1]
        dur = float(np.clip(np.random.uniform(0.3, 0.5), 0.3, 0.5))
        end = min(total_s, start + dur)
        if end - start >= 0.2:
            segs.append((start, end))
        else:
            break

    cleaned: List[Tuple[float, float]] = []
    last_end = 0.0
    for s, e in segs:
        s = max(last_end, s)
        e = max(s, e)
        if e > s:
            cleaned.append((round(s, 3), round(e, 3)))
            last_end = e
        if last_end >= total_s:
            break
    return cleaned

def make_edl(total_s: float, beat_times: List[float]) -> List[Tuple[float, float]]:
    return _distribute_segments(float(total_s), [float(x) for x in beat_times])
