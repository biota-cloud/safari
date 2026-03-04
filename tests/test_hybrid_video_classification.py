"""
Unit tests for Quality-Diverse Top-K Frame Classification helpers.

Tests: crop_quality_score, select_diverse_frames, vote_classifications.
"""

import pytest
from backend.core.hybrid_video_core import (
    crop_quality_score,
    select_diverse_frames,
    vote_classifications,
)


# ──────────────────────────────────────────────────
# crop_quality_score tests
# ──────────────────────────────────────────────────

def test_crop_quality_score_center_better():
    """Center crop should score higher than edge crop."""
    fw, fh = 1920, 1080
    # Center box: 200x200 in the middle
    center_score = crop_quality_score([860, 440, 1060, 640], fw, fh)
    # Edge box: 200x200 touching top-left corner
    edge_score = crop_quality_score([0, 0, 200, 200], fw, fh)
    assert center_score > edge_score, f"Center {center_score:.3f} should > edge {edge_score:.3f}"


def test_crop_quality_score_larger_better():
    """Larger box should score higher than tiny box (both centered)."""
    fw, fh = 1920, 1080
    # Large box: 400x400 centered
    large = crop_quality_score([760, 340, 1160, 740], fw, fh)
    # Tiny box: 20x20 centered
    tiny = crop_quality_score([950, 530, 970, 550], fw, fh)
    assert large > tiny, f"Large {large:.3f} should > tiny {tiny:.3f}"


def test_crop_quality_score_zero_area():
    """Zero or negative area should return 0."""
    assert crop_quality_score([100, 100, 100, 100], 1920, 1080) == 0.0
    assert crop_quality_score([200, 200, 100, 100], 1920, 1080) == 0.0


# ──────────────────────────────────────────────────
# select_diverse_frames tests
# ──────────────────────────────────────────────────

def test_select_diverse_frames_respects_k():
    """Should return exactly K candidates when enough are available."""
    candidates = [
        {"frame": i * 10, "box": [400, 300, 600, 500]}
        for i in range(20)
    ]
    selected = select_diverse_frames(candidates, K=3, frame_width=1920, frame_height=1080)
    assert len(selected) == 3


def test_select_diverse_frames_few_candidates():
    """Should return all candidates when fewer than K available."""
    candidates = [
        {"frame": 10, "box": [400, 300, 600, 500]},
        {"frame": 50, "box": [400, 300, 600, 500]},
    ]
    selected = select_diverse_frames(candidates, K=5, frame_width=1920, frame_height=1080)
    assert len(selected) == 2


def test_select_diverse_frames_temporal_spread():
    """Selected frames should not all be adjacent."""
    candidates = [
        {"frame": i, "box": [400, 300, 600, 500]}
        for i in range(100)
    ]
    selected = select_diverse_frames(candidates, K=3, frame_width=1920, frame_height=1080)
    frames = sorted(s["frame"] for s in selected)
    # At least one pair should be separated by > 10 frames
    max_gap = max(frames[i+1] - frames[i] for i in range(len(frames)-1))
    assert max_gap > 10, f"Max gap {max_gap} too small — not temporally diverse"


# ──────────────────────────────────────────────────
# vote_classifications tests
# ──────────────────────────────────────────────────

def test_vote_classifications_majority():
    """Majority class should win."""
    results = [("Fox", 0.9), ("Fox", 0.85), ("Deer", 0.7)]
    winner, _, avg_conf, agreement = vote_classifications(results, classifier_confidence=0.5)
    assert winner == "Fox"
    assert abs(avg_conf - 0.875) < 0.01  # (0.9 + 0.85) / 2


def test_vote_classifications_agreement():
    """Agreement ratio should be correct."""
    results = [("Fox", 0.9), ("Fox", 0.85), ("Deer", 0.7)]
    _, _, _, agreement = vote_classifications(results, classifier_confidence=0.5)
    assert abs(agreement - 2/3) < 0.01  # 2 out of 3


def test_vote_classifications_single():
    """Should work with a single vote (K=1)."""
    results = [("Hare", 0.92)]
    winner, _, avg_conf, agreement = vote_classifications(results, classifier_confidence=0.5)
    assert winner == "Hare"
    assert abs(avg_conf - 0.92) < 0.01
    assert abs(agreement - 1.0) < 0.01


def test_vote_classifications_all_below_threshold():
    """All below threshold → Unknown."""
    results = [("Fox", 0.3), ("Deer", 0.2)]
    winner, _, avg_conf, _ = vote_classifications(results, classifier_confidence=0.5)
    assert winner == "Unknown"
    assert avg_conf == 0.0


def test_vote_classifications_with_failures():
    """Should handle None (failed) classifications gracefully."""
    results = [(None, 0.0), ("Fox", 0.9), (None, 0.0)]
    winner, _, avg_conf, agreement = vote_classifications(results, classifier_confidence=0.5)
    assert winner == "Fox"
    assert abs(agreement - 1/3) < 0.01  # 1 valid vote out of 3 total
