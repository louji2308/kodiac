import cv2
import numpy as np
import pytest

from Kodiac_robotics.judge.crops import OUTLINE_BGR, make_crop
from Kodiac_robotics.segment.rle import mask_to_rle


def _scene(h=240, w=320, box=(100, 80, 140, 110)):
    frame = np.full((h, w, 3), 120, np.uint8)
    x0, y0, x1, y1 = box
    mask = np.zeros((h, w), np.uint8)
    mask[y0:y1, x0:x1] = 1
    frame[y0:y1, x0:x1] = (200, 50, 50)
    return frame, mask_to_rle(mask), (h, w)


def _decode(png):
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    assert img is not None
    return img


def test_crop_is_png_and_upscaled_to_min_px():
    frame, rle, size = _scene()
    png = make_crop(frame, rle, size)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    img = _decode(png)
    assert min(img.shape[:2]) >= 512


def test_crop_contains_outline_pixels():
    frame, rle, size = _scene()
    img = _decode(make_crop(frame, rle, size))
    outline = np.all(img == np.array(OUTLINE_BGR, np.uint8), axis=2)
    assert outline.sum() > 500
    assert not np.all(frame == frame[0, 0])
    # outline pixels exist on all four sides of the object
    ys, xs = np.nonzero(outline)
    assert xs.min() < img.shape[1] * 0.4 and xs.max() > img.shape[1] * 0.6
    assert ys.min() < img.shape[0] * 0.4 and ys.max() > img.shape[0] * 0.6


def test_crop_padding_extends_beyond_bbox():
    frame, rle, size = _scene()
    img = _decode(make_crop(frame, rle, size, pad=0.25))
    # 40x30 bbox + 25% pad -> 60x45 region => aspect ~1.33
    assert abs(img.shape[1] / img.shape[0] - 60 / 45) < 0.05


def test_crop_is_deterministic():
    frame, rle, size = _scene()
    assert make_crop(frame, rle, size) == make_crop(frame, rle, size)


def test_crop_clamps_at_frame_edge():
    frame, rle, size = _scene(box=(0, 0, 40, 30))
    img = _decode(make_crop(frame, rle, size))
    assert min(img.shape[:2]) >= 512


def test_rle_size_zero_means_frame_size():
    frame, rle, _ = _scene()
    assert _decode(make_crop(frame, rle, (0, 0))).shape == _decode(make_crop(frame, rle, (240, 320))).shape


def test_mask_resized_to_frame_when_sizes_differ():
    frame, rle, _ = _scene()
    big = cv2.resize(frame, (640, 480))
    img = _decode(make_crop(big, rle, (240, 320)))
    assert min(img.shape[:2]) >= 512


def test_empty_mask_raises():
    frame, _, size = _scene()
    with pytest.raises(ValueError):
        make_crop(frame, mask_to_rle(np.zeros(size, np.uint8)), size)


def test_extreme_aspect_is_capped():
    frame, rle, size = _scene(h=240, w=1200, box=(10, 100, 1190, 106))
    img = _decode(make_crop(frame, rle, size))
    assert max(img.shape[:2]) <= 2048
