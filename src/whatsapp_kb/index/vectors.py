import numpy as np


def cosine_distance(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 1.0
    first = np.asarray(left, dtype=float)
    second = np.asarray(right, dtype=float)
    left_norm = float(np.linalg.norm(first))
    right_norm = float(np.linalg.norm(second))
    if left_norm == 0 or right_norm == 0:
        return 1.0
    cosine = float(np.dot(first, second) / (left_norm * right_norm))
    cosine = max(-1.0, min(1.0, cosine))
    return 1.0 - cosine
