"""Asphalt 8 hand-gesture controller.

Install with the same Python interpreter used to run this file:
    python -m pip install opencv-python mediapipe pynput

The installed MediaPipe version in this environment does not expose the old
mp.solutions API, so this program uses MediaPipe's current Tasks Hand Landmarker
API. It downloads the official hand_landmarker.task model the first time it runs.
"""

import math
import tempfile
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
from pynput.keyboard import Controller, Key, KeyCode


# --------------------------- Easy-to-edit settings ---------------------------
CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
MIN_DETECTION_CONFIDENCE = 0.60
MIN_HAND_PRESENCE_CONFIDENCE = 0.55
MIN_TRACKING_CONFIDENCE = 0.55

CALIBRATION_COUNTDOWN_SECONDS = 3
CALIBRATION_CAPTURE_SECONDS = 2.0
MIN_CALIBRATION_SAMPLES = 10
MIN_FIST_DISTANCE_PIXELS = 45

STEERING_DEAD_ZONE = 5.0       # Degrees from calibrated center before steering.
STEERING_SENSITIVITY = 1.0     # Larger values make a given turn more sensitive.
ANGLE_SMOOTHING = 0.28         # EMA factor: smaller is smoother, larger is faster.
GESTURE_STABLE_FRAMES = 3      # Frames required before a hand gesture changes.
STEERING_STABLE_FRAMES = 2     # Frames required before A/D changes state.
SPACE_COOLDOWN = 0.80          # Seconds between middle-finger Space triggers.
SPACE_DISPLAY_SECONDS = 0.20   # How long SPACE appears ON in the debug window.
INVERT_STEERING = False        # Set True if turning left/right is reversed.

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
MODEL_PATH = Path(tempfile.gettempdir()) / "hand_landmarker.task"
SIDES = ("Left", "Right")

# Standard MediaPipe hand connections for drawing the skeleton with OpenCV.
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]
FINGER_TIPS = {"thumb": 4, "index": 8, "middle": 12, "ring": 16, "pinky": 20}
FINGER_PIPS = {"index": 6, "middle": 10, "ring": 14, "pinky": 18}


def ensure_model():
    """Download the official Tasks model once into the system temp folder."""
    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 0:
        return str(MODEL_PATH)

    print("Downloading the MediaPipe hand model (first run only)...")
    temporary_path = MODEL_PATH.with_suffix(".download")
    try:
        urllib.request.urlretrieve(MODEL_URL, temporary_path)
        temporary_path.replace(MODEL_PATH)
    except Exception as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(
            "Could not download the hand model. Check your internet connection "
            "and run the program again."
        ) from exc
    return str(MODEL_PATH)


def initialize_camera():
    """Open the webcam and request a practical real-time resolution."""
    camera = cv2.VideoCapture(CAMERA_INDEX)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    if not camera.isOpened():
        camera.release()
        raise RuntimeError(
            f"Camera {CAMERA_INDEX} could not be opened. Check CAMERA_INDEX, "
            "camera permissions, and whether another app is using the webcam."
        )
    return camera


def initialize_hands():
    """Create a video-mode MediaPipe Hand Landmarker for two hands."""
    if not hasattr(mp, "tasks"):
        raise RuntimeError(
            "This MediaPipe installation lacks the Tasks API. Run: "
            "python -m pip install --upgrade mediapipe"
        )

    model_path = ensure_model()
    vision = mp.tasks.vision
    options = vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=MIN_DETECTION_CONFIDENCE,
        min_hand_presence_confidence=MIN_HAND_PRESENCE_CONFIDENCE,
        min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
    )
    return vision.HandLandmarker.create_from_options(options)


def next_timestamp_ms(last_timestamp):
    """Return a strictly increasing timestamp required by VIDEO mode."""
    timestamp = max(last_timestamp[0] + 1, time.monotonic_ns() // 1_000_000)
    last_timestamp[0] = timestamp
    return timestamp


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def get_finger_states(landmarks):
    """Return which fingers appear extended, using wrist-relative distances."""
    wrist = landmarks[0]
    palm_scale = distance(wrist, landmarks[9])
    if palm_scale < 1e-5:
        return {"thumb": False, "index": False, "middle": False, "ring": False, "pinky": False}

    fingers = {}
    for name, tip_index in FINGER_TIPS.items():
        if name == "thumb":
            continue
        pip_index = FINGER_PIPS[name]
        tip_from_wrist = distance(wrist, landmarks[tip_index])
        pip_from_wrist = distance(wrist, landmarks[pip_index])
        fingers[name] = tip_from_wrist > pip_from_wrist + 0.12 * palm_scale

    # The thumb must be straight and away from the index knuckle to count as
    # extended. A thumb pointing vertically up is treated as uncertain, not a fist.
    thumb_tip = landmarks[4]
    thumb_ip = landmarks[3]
    thumb_mcp = landmarks[2]
    thumb_straight = (
        distance(thumb_mcp, thumb_tip)
        > distance(thumb_mcp, thumb_ip) + 0.08 * palm_scale
    )
    thumb_separated = distance(thumb_tip, landmarks[5]) > 0.42 * palm_scale
    fingers["thumb"] = thumb_straight and thumb_separated
    fingers["thumb_up"] = (
        thumb_straight
        and thumb_tip.y < thumb_ip.y - 0.12 * palm_scale
        and thumb_tip.y < wrist.y - 0.16 * palm_scale
    )
    return fingers


def detect_fist(fingers):
    """A fist has the four long fingers folded and no thumbs-up pose."""
    long_fingers_folded = not any(
        fingers.get(name, False) for name in ("index", "middle", "ring", "pinky")
    )
    return long_fingers_folded and not fingers.get("thumb_up", False)


def detect_open_palm(fingers):
    """Require all four long fingers and the thumb to be extended."""
    return all(fingers.get(name, False) for name in ("thumb", "index", "middle", "ring", "pinky"))


def detect_middle_finger(fingers):
    """Require only the middle finger to be extended; the thumb is folded."""
    return (
        fingers.get("middle", False)
        and not fingers.get("index", False)
        and not fingers.get("ring", False)
        and not fingers.get("pinky", False)
        and not fingers.get("thumb", False)
        and not fingers.get("thumb_up", False)
    )


def classify_gesture(landmarks):
    """Classify one hand as FIST, OPEN PALM, MIDDLE, or UNKNOWN."""
    fingers = get_finger_states(landmarks)
    # These poses are intentionally strict so uncertain shapes do not steer.
    if detect_open_palm(fingers):
        return "OPEN PALM"
    if detect_middle_finger(fingers):
        return "MIDDLE"
    if detect_fist(fingers):
        return "FIST"
    return "UNKNOWN"


def get_hand_label(result, hand_index, landmarks):
    """Use MediaPipe handedness, with screen position as a fallback."""
    try:
        category = result.handedness[hand_index][0]
        name = getattr(category, "category_name", None)
        if name is None:
            name = getattr(category, "categoryName", None)
        if name and name.lower() in ("left", "right"):
            return name.title()
    except (AttributeError, IndexError, TypeError):
        pass
    # The preview/input is mirrored, so screen-left is the user's left side.
    return "Left" if landmarks[0].x < 0.5 else "Right"


def draw_hand_landmarks(frame, landmarks):
    height, width = frame.shape[:2]
    points = [(int(point.x * width), int(point.y * height)) for point in landmarks]
    for start, end in HAND_CONNECTIONS:
        cv2.line(frame, points[start], points[end], (50, 210, 50), 2)
    for point in points:
        cv2.circle(frame, point, 3, (20, 40, 240), -1)


def detect_hands(frame, landmarker, last_timestamp):
    """Run MediaPipe once and return landmarks and raw gesture per hand."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect_for_video(mp_image, next_timestamp_ms(last_timestamp))

    landmarks_by_side = {}
    gestures_by_side = {}
    for index, landmarks in enumerate(result.hand_landmarks):
        side = get_hand_label(result, index, landmarks)
        landmarks_by_side[side] = landmarks
        gestures_by_side[side] = classify_gesture(landmarks)
        draw_hand_landmarks(frame, landmarks)
    return landmarks_by_side, gestures_by_side


def get_fist_center(landmarks, frame_shape):
    """Estimate fist center from wrist and the four knuckle landmarks."""
    height, width = frame_shape[:2]
    indexes = (0, 5, 9, 13, 17)
    x = sum(landmarks[index].x for index in indexes) / len(indexes) * width
    y = sum(landmarks[index].y for index in indexes) / len(indexes) * height
    return (int(x), int(y))


def calculate_steering_angle(left_center, right_center):
    """Angle from screen-left fist to screen-right fist (image y points down)."""
    left, right = sorted((left_center, right_center), key=lambda point: point[0])
    dx = right[0] - left[0]
    dy = right[1] - left[1]
    if math.hypot(dx, dy) < MIN_FIST_DISTANCE_PIXELS:
        return None
    return math.degrees(math.atan2(dy, dx))


def hand_roll_angle(landmarks):
    """Measure the angle of a single fist's knuckle line for drift fallback."""
    index_mcp = landmarks[5]
    pinky_mcp = landmarks[17]
    return math.degrees(math.atan2(pinky_mcp.y - index_mcp.y, pinky_mcp.x - index_mcp.x))


def wrap_degrees(angle):
    return (angle + 180.0) % 360.0 - 180.0


def circular_mean_degrees(values):
    if not values:
        return 0.0
    sine = sum(math.sin(math.radians(value)) for value in values)
    cosine = sum(math.cos(math.radians(value)) for value in values)
    return math.degrees(math.atan2(sine, cosine))


class GestureStabilizer:
    """Apply per-hand frame debounce so each hand remains independent."""
    def __init__(self):
        self.states = {side: "NOT DETECTED" for side in SIDES}
        self.candidates = {side: None for side in SIDES}
        self.counts = {side: 0 for side in SIDES}

    def reset(self):
        self.__init__()

    def update(self, observed):
        for side in SIDES:
            value = observed.get(side, "NOT DETECTED")
            if value == self.states[side]:
                self.candidates[side] = None
                self.counts[side] = 0
                continue
            if value == self.candidates[side]:
                self.counts[side] += 1
            else:
                self.candidates[side] = value
                self.counts[side] = 1
            if self.counts[side] >= GESTURE_STABLE_FRAMES:
                self.states[side] = value
                self.candidates[side] = None
                self.counts[side] = 0
        return dict(self.states)


class AngleSmoother:
    """Exponential moving average that handles angles around +/-180 degrees."""
    def __init__(self):
        self.value = None

    def reset(self):
        self.value = None

    def update(self, angle):
        if self.value is None:
            self.value = angle
        else:
            difference = wrap_degrees(angle - self.value)
            self.value = wrap_degrees(self.value + ANGLE_SMOOTHING * difference)
        return self.value


class DirectionDebouncer:
    """Avoid rapid A/D changes when the steering angle jitters near a boundary."""
    def __init__(self):
        self.current = None
        self.candidate = None
        self.count = 0

    def reset(self):
        self.current = None
        self.candidate = None
        self.count = 0

    def update(self, direction):
        if direction == self.current:
            self.candidate = None
            self.count = 0
            return self.current
        if direction == self.candidate:
            self.count += 1
        else:
            self.candidate = direction
            self.count = 1
        if self.count >= STEERING_STABLE_FRAMES:
            self.current = direction
            self.candidate = None
            self.count = 0
        return self.current


class KeyboardController:
    """Centralized pynput key-state manager with safe release on shutdown."""
    def __init__(self):
        self.controller = Controller()
        self.key_objects = {
            "a": KeyCode.from_char("a"),
            "d": KeyCode.from_char("d"),
            "s": KeyCode.from_char("s"),
        }
        self.held = set()
        self.previous_middle = False
        self.last_space_time = float("-inf")
        self.space_active_until = 0.0

    def _set_held(self, desired):
        # Remove opposite steering before pressing the new direction.
        if "a" in desired:
            desired = set(desired)
            desired.discard("d")
        if "d" in desired:
            desired = set(desired)
            desired.discard("a")

        for name in self.held - desired:
            self.controller.release(self.key_objects[name])
        self.held.difference_update(self.held - desired)
        for name in desired - self.held:
            self.controller.press(self.key_objects[name])
            self.held.add(name)

    def update(self, direction, brake, middle_active, now):
        desired = set()
        if direction == "A":
            desired.add("a")
        elif direction == "D":
            desired.add("d")
        if brake:
            desired.add("s")
        self._set_held(desired)

        # Space is a one-shot key press on a stable middle-finger gesture edge.
        if (
            middle_active
            and not self.previous_middle
            and now - self.last_space_time >= SPACE_COOLDOWN
        ):
            self.controller.press(Key.space)
            self.controller.release(Key.space)
            self.last_space_time = now
            self.space_active_until = now + SPACE_DISPLAY_SECONDS
        self.previous_middle = middle_active

    def release_all(self):
        for name in tuple(self.held):
            try:
                self.controller.release(self.key_objects[name])
            except Exception:
                pass
            self.held.discard(name)
        self.previous_middle = False


def draw_status_text(frame, text, y, color=(255, 255, 255), scale=0.52):
    cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3)
    cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1)


def draw_fist_geometry(frame, centers, raw_angle, center_angle):
    if len(centers) != 2:
        return
    points = sorted(centers.values(), key=lambda point: point[0])
    left, right = points
    midpoint_y = (left[1] + right[1]) // 2
    cv2.line(frame, (0, midpoint_y), (frame.shape[1] - 1, midpoint_y), (180, 180, 80), 1)
    cv2.line(frame, left, right, (255, 180, 0), 3)
    cv2.circle(frame, left, 9, (0, 255, 255), -1)
    cv2.circle(frame, right, 9, (0, 255, 255), -1)
    if raw_angle is not None:
        text = f"Line angle: {raw_angle:+.1f} deg  Center: {center_angle:+.1f} deg"
        draw_status_text(frame, text, 120, (255, 230, 120), 0.48)


def draw_interface(
    frame, landmarks_by_side, raw_gestures, stable_gestures, centers,
    center_angle, relative_angle, direction, keyboard, fps, now, mode,
):
    for row, side in enumerate(SIDES):
        detected = side in landmarks_by_side
        hand_status = "DETECTED" if detected else "NOT DETECTED"
        gesture = stable_gestures[side] if detected else 'NOT DETECTED'
        if detected and gesture == 'NOT DETECTED':
            gesture = raw_gestures.get(side, 'UNKNOWN')
        draw_status_text(
            frame, f"{side} Hand: {hand_status}    {side} Gesture: {gesture}",
            25 + row * 26, (100, 255, 100) if detected else (150, 150, 150), 0.48,
        )

    if relative_angle is None:
        relative_text = "--"
        direction_text = "CENTER / UNAVAILABLE"
    else:
        relative_text = f"{relative_angle:+.1f} deg"
        direction_text = {"A": "LEFT", "D": "RIGHT", None: "CENTER"}[direction]
    draw_status_text(frame, f"Center Angle: {center_angle:+.1f} deg", 80, (180, 240, 255))
    draw_status_text(frame, f"Relative Angle: {relative_text}   Direction: {direction_text}", 101)
    draw_status_text(frame, f"Steering mode: {mode}   FPS: {fps:.1f}", 143, (180, 240, 255), 0.48)

    a_on = "ON" if "a" in keyboard.held else "OFF"
    d_on = "ON" if "d" in keyboard.held else "OFF"
    s_on = "ON" if "s" in keyboard.held else "OFF"
    space_on = "ON" if now < keyboard.space_active_until else "OFF"
    draw_status_text(frame, f"A: {a_on}   D: {d_on}   S: {s_on}   SPACE: {space_on}", 168)
    draw_status_text(frame, "Q: quit   R: recalibrate", frame.shape[0] - 14, (220, 220, 220), 0.45)


def calibration_overlay(frame, landmarks_by_side, gestures, title, detail):
    centers = {}
    for side, landmarks in landmarks_by_side.items():
        if gestures.get(side) == "FIST":
            centers[side] = get_fist_center(landmarks, frame.shape)
    angle = None
    if len(centers) == 2:
        points = sorted(centers.values(), key=lambda point: point[0])
        angle = calculate_steering_angle(points[0], points[1])
        draw_fist_geometry(frame, centers, angle, 0.0)
    draw_status_text(frame, title, 32, (0, 230, 255), 0.72)
    draw_status_text(frame, detail, 65, (255, 255, 255), 0.5)
    return centers, angle


def calibrate_center(camera, landmarker, last_timestamp, keyboard):
    """Capture a neutral two-fist angle and individual fist roll references."""
    keyboard.release_all()
    print("Calibration: hold both fists in your straight-driving position.")

    while True:
        countdown_end = time.monotonic() + CALIBRATION_COUNTDOWN_SECONDS
        restart = False
        while time.monotonic() < countdown_end:
            ok, frame = camera.read()
            if not ok:
                print('Webcam frame could not be read during calibration.')
                return None
            frame = cv2.flip(frame, 1)
            landmarks, gestures = detect_hands(frame, landmarker, last_timestamp)
            remaining = max(0, math.ceil(countdown_end - time.monotonic()))
            calibration_overlay(
                frame, landmarks, gestures, f"CALIBRATION STARTS IN {remaining}",
                "Place both fists in your normal straight-driving position.",
            )
            cv2.imshow("Asphalt 8 Hand Gesture Controller", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                return None
            if key == ord("r"):
                restart = True
                break
        if restart:
            continue

        capture_started = time.monotonic()
        angles = []
        roll_samples = {side: [] for side in SIDES}
        while True:
            ok, frame = camera.read()
            if not ok:
                print('Webcam frame could not be read during calibration.')
                return None
            frame = cv2.flip(frame, 1)
            landmarks, gestures = detect_hands(frame, landmarker, last_timestamp)
            centers = {
                side: get_fist_center(landmarks[side], frame.shape)
                for side in SIDES
                if side in landmarks and gestures.get(side) == "FIST"
            }
            if len(centers) == 2:
                points = sorted(centers.values(), key=lambda point: point[0])
                angle = calculate_steering_angle(points[0], points[1])
                if angle is not None:
                    angles.append(angle)
                    for side in SIDES:
                        roll_samples[side].append(hand_roll_angle(landmarks[side]))

            elapsed = time.monotonic() - capture_started
            enough_time = elapsed >= CALIBRATION_CAPTURE_SECONDS
            enough_samples = len(angles) >= MIN_CALIBRATION_SAMPLES
            detail = (
                f"Keep both fists steady. Samples: {len(angles)}/{MIN_CALIBRATION_SAMPLES}"
            )
            calibration_overlay(frame, landmarks, gestures, "CALIBRATING CENTER", detail)
            cv2.imshow("Asphalt 8 Hand Gesture Controller", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                return None
            if key == ord("r"):
                restart = True
                break
            if enough_time and enough_samples:
                center_angle = circular_mean_degrees(angles)
                roll_centers = {
                    side: circular_mean_degrees(values)
                    for side, values in roll_samples.items()
                    if values
                }
                return {"center_angle": center_angle, "roll_centers": roll_centers}
        if restart:
            continue


def single_fist_relative_angle(side, landmarks, roll_centers):
    """Use calibrated hand roll only for gesture-plus-fist fallback steering."""
    current = hand_roll_angle(landmarks)
    if side not in roll_centers:
        # This hand was not available during two-hand calibration; center it now.
        roll_centers[side] = current
        return 0.0
    return wrap_degrees(current - roll_centers[side])


def choose_direction(relative_angle):
    if relative_angle is None:
        return None
    angle = relative_angle * STEERING_SENSITIVITY
    if INVERT_STEERING:
        angle = -angle
    if angle < -STEERING_DEAD_ZONE:
        return "A"
    if angle > STEERING_DEAD_ZONE:
        return "D"
    return None


def main():
    cv2.setNumThreads(1)
    camera = initialize_camera()
    keyboard = KeyboardController()
    last_timestamp = [0]
    try:
        with initialize_hands() as landmarker:
            calibration = calibrate_center(camera, landmarker, last_timestamp, keyboard)
            if calibration is None:
                return

            center_angle = calibration["center_angle"]
            roll_centers = calibration["roll_centers"]
            stabilizer = GestureStabilizer()
            smoother = AngleSmoother()
            direction_debouncer = DirectionDebouncer()
            previous_frame_time = time.monotonic()
            fps = 0.0

            while True:
                ok, frame = camera.read()
                if not ok:
                    print("Webcam frame could not be read; releasing all controls.")
                    keyboard.release_all()
                    break
                frame = cv2.flip(frame, 1)
                landmarks, raw_gestures = detect_hands(frame, landmarker, last_timestamp)
                stable = stabilizer.update(raw_gestures)
                now = time.monotonic()

                brake = any(stable[side] == "OPEN PALM" for side in SIDES)
                middle_active = any(stable[side] == "MIDDLE" for side in SIDES)
                fist_centers = {
                    side: get_fist_center(landmarks[side], frame.shape)
                    for side in SIDES
                    if side in landmarks and stable[side] == "FIST"
                }

                relative_angle = None
                mode = "inactive"
                steering_valid = False
                if len(fist_centers) == 2:
                    pair_angle = calculate_steering_angle(
                        fist_centers["Left"], fist_centers["Right"]
                    )
                    if pair_angle is not None:
                        relative_angle = wrap_degrees(pair_angle - center_angle)
                        mode = "two-fist wheel"
                        steering_valid = True
                elif len(fist_centers) == 1:
                    side = next(iter(fist_centers))
                    other_side = "Right" if side == "Left" else "Left"
                    other_gesture = stable[other_side]
                    # Only use the one-fist fallback when the other hand is
                    # deliberately doing an independent gesture, not when it
                    # disappears or becomes uncertain.
                    if (
                        other_side in landmarks
                        and raw_gestures.get(other_side) == other_gesture
                        and other_gesture in ("OPEN PALM", "MIDDLE")
                    ):
                        relative_angle = single_fist_relative_angle(
                            side, landmarks[side], roll_centers
                        )
                        mode = f"one-fist fallback ({other_gesture.lower()})"
                        steering_valid = True

                if steering_valid:
                    relative_angle = smoother.update(relative_angle)
                    wanted_direction = choose_direction(relative_angle)
                    direction = direction_debouncer.update(wanted_direction)
                else:
                    smoother.reset()
                    direction_debouncer.reset()
                    direction = None

                keyboard.update(direction, brake, middle_active, now)

                # Draw the visible steering line and reference only while both
                # stable fist gestures are present.
                raw_pair_angle = None
                if len(fist_centers) == 2:
                    raw_pair_angle = calculate_steering_angle(
                        fist_centers["Left"], fist_centers["Right"]
                    )
                draw_fist_geometry(frame, fist_centers, raw_pair_angle, center_angle)

                elapsed = max(now - previous_frame_time, 1e-5)
                instant_fps = 1.0 / elapsed
                fps = instant_fps if fps == 0 else 0.85 * fps + 0.15 * instant_fps
                previous_frame_time = now
                draw_interface(
                    frame, landmarks, raw_gestures, stable, fist_centers,
                    center_angle, relative_angle, direction, keyboard, fps, now, mode,
                )
                cv2.imshow("Asphalt 8 Hand Gesture Controller", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("r"):
                    keyboard.release_all()
                    new_calibration = calibrate_center(
                        camera, landmarker, last_timestamp, keyboard
                    )
                    if new_calibration is None:
                        break
                    center_angle = new_calibration["center_angle"]
                    roll_centers = new_calibration["roll_centers"]
                    stabilizer.reset()
                    smoother.reset()
                    direction_debouncer.reset()

    finally:
        keyboard.release_all()
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()



