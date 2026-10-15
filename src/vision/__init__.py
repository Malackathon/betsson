"""Vision inspection package — Gemini + OpenCV for slot game validation."""

from src.vision.image_utils import (
    BBox,
    Frame,
    RGBColor,
    annotate_bbox,
    annotate_multiple,
    bgr_to_rgb,
    crop_reels_region,
    crop_region,
    frame_to_pil,
    image_to_base64,
    image_to_bytes,
    load_frame,
    load_image,
    mask_personal_data,
    mask_region,
    pil_to_frame,
    resize_for_api,
    rgb_to_bgr,
    save_image,
)
from src.vision.motion_detector import (
    FrameCapture,
    MotionBaseline,
    MotionConfig,
    SpinLifecycle,
    capture_baseline,
    monitor_spin_lifecycle,
    motion_level,
    motion_level_region,
    wait_until_motion,
    wait_until_stable,
)
from src.vision.gemini_inspector import (
    GeminiBalanceReading,
    GeminiHudReading,
    GeminiInspector,
    GeminiMessageReading,
    RateLimiter,
    SpinButtonLocation,
)

__all__ = [
    # image_utils
    "BBox", "Frame", "RGBColor",
    "load_image", "load_frame", "save_image",
    "bgr_to_rgb", "rgb_to_bgr",
    "crop_region", "crop_reels_region",
    "annotate_bbox", "annotate_multiple",
    "mask_region", "mask_personal_data",
    "image_to_bytes", "image_to_base64",
    "frame_to_pil", "pil_to_frame",
    "resize_for_api",
    # motion_detector
    "FrameCapture", "MotionConfig", "MotionBaseline", "SpinLifecycle",
    "motion_level", "motion_level_region",
    "capture_baseline", "wait_until_motion", "wait_until_stable",
    "monitor_spin_lifecycle",
    # gemini_inspector
    "GeminiInspector", "RateLimiter",
    "GeminiBalanceReading", "GeminiHudReading",
    "GeminiMessageReading", "SpinButtonLocation",
]

