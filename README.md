# ⚡ MagnoGlove – Gesture Controlled Electromagnetic Glove
### MVP Software Demonstration

---

## Overview

MagnoGlove is an interactive software demonstration that simulates a real
electromagnetic glove controlled by hand gestures.  A webcam detects your
hand in real time; the 3D simulation responds instantly by activating or
releasing a virtual electromagnet that attracts metallic objects.

---

## System Requirements

| Component | Minimum |
|-----------|---------|
| OS        | Windows 10 / macOS 12 / Ubuntu 20.04 |
| Python    | 3.9 – 3.11 |
| RAM       | 4 GB |
| GPU       | Optional (runs on CPU) |
| Webcam    | Any USB or built-in |

---

## Installation

### 1. Clone / copy the project folder

```
magnoglove_demo/
├── main.py
├── gesture_detection.py
├── magnet_logic.py
├── simulation_3d.py
├── utils.py
├── requirements.txt
└── README.md
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** MediaPipe requires Python ≤ 3.11.  Use `python --version` to check.

---

## How to Run

```bash
python main.py
```

Two windows will open:
- **Webcam window** — shows your hand with landmark skeleton overlay
- **3D simulation window** — interactive Ursina scene

---

## Gesture Controls

| Gesture | Action | Magnet State |
|---------|--------|-------------|
| ✊ Closed Fist | All fingers curled toward palm | **ON** – full magnetic pull |
| ✋ Open Hand | All 4 fingers extended up | **OFF** – objects drop |
| 👌 Pinch | Thumb tip touches index tip | **PRECISION** – slow gentle pull |

Press **ESC** to exit the 3D window.  
Press **Q** while the webcam window is focused to exit both.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                             │
│   Starts threads, instantiates modules, runs Ursina loop    │
└─────────────────┬───────────────────────┬───────────────────┘
                  │                       │
     Background Thread              Main Thread
                  │                       │
  ┌───────────────▼──────────┐  ┌────────▼──────────────────┐
  │   gesture_detection.py   │  │     simulation_3d.py       │
  │                          │  │                            │
  │  OpenCV  →  MediaPipe    │  │  Ursina Engine             │
  │  Webcam  →  21 Landmarks │  │  3D Scene + Physics        │
  │  Classify Gesture        │  │  Visual Effects            │
  │                          │  │  HUD Overlay               │
  └──────────┬───────────────┘  └────────┬───────────────────┘
             │                           │
             └──── shared_state dict ────┘
                   (threading.Lock)
                   gesture = "CLOSED_FIST"
                             "OPEN_HAND"
                             "PINCH"
                             "UNKNOWN"
```

---

## Module Descriptions

### `gesture_detection.py`
Captures webcam frames via OpenCV, passes them through MediaPipe Hands
to extract 21 3D hand landmarks, and classifies gestures using geometric rules.

**Classification logic:**
1. Compute 2D distance between THUMB_TIP (landmark 4) and INDEX_TIP (8).
   If `dist < 0.07` → **PINCH**
2. For each of the 4 fingers, compare tip Y-coordinate to MCP knuckle Y.
   In image space, Y increases downward — so `tip.y > mcp.y` means curled.
   If ≥ 3 fingers curled → **CLOSED_FIST**
3. Otherwise → **OPEN_HAND**

### `magnet_logic.py`
Pure Python state machine.  Maps gesture → magnet preset → physics parameters.

| State     | strength | radius | pull_speed |
|-----------|----------|--------|------------|
| OFF       | 0.00     | 0.0    | 0.00       |
| ON        | 1.00     | 9.0    | 7.00       |
| PRECISION | 0.35     | 3.8    | 2.20       |

Force model: `speed = pull_speed / (distance × 0.4 + 0.6)`

### `simulation_3d.py`
Ursina Engine scene.  `SimController` is a custom `Entity` subclass whose
`update()` is called every frame by Ursina's render loop.

- **Magnetic rings:** 5 overlapping `circle` quads expand outward with phase offset
- **Glow sphere:** pulsing `sphere` entity around glove when active
- **Object physics:** velocity accumulates toward glove, decelerates with damping
- **Attachment snap:** when distance < 0.55 units, object locks near glove

### `utils.py`
`create_shared_state()` factory and small math helpers (`clamp`, `remap`,
`smooth_lerp`).

---

## Visual Effect Reference

```
Magnet ON (Fist)
  Glove color    →  Electric blue  (0, 145, 255)
  Ring color     →  Cyan-blue expanding rings
  Ring speed     →  Fast (2.1 cycles/sec)
  Glow alpha     →  55 / 255
  Object color   →  Shifts to light blue as they approach

Magnet PRECISION (Pinch)
  Glove color    →  Amber  (220, 170, 0)
  Ring color     →  Golden rings, smaller radius
  Ring speed     →  Slower (1.3 cycles/sec)
  Glow alpha     →  35 / 255

Magnet OFF (Open Hand)
  Glove color    →  Dark blue  (40, 80, 175)
  All effects    →  Hidden
  Objects        →  Gravity → table → slide to rest position
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `RuntimeError: Cannot open camera` | Check webcam is connected; try `camera_index=1` in main.py |
| MediaPipe install fails | Ensure Python ≤ 3.11: `python --version` |
| Poor gesture recognition | Ensure good lighting; keep hand 30–60 cm from camera |
| Low FPS | Close other applications; check GPU drivers |
| Ursina window black | Update GPU drivers or disable fullscreen |

---

## Demo Script (for presentations)

1. Start: `python main.py`
2. Show **open hand** → objects sit idle on table
3. Make **closed fist** → objects fly up and cluster around glove
4. Open hand → objects drop back down with gravity
5. Make **pinch** → objects float up slowly
6. Explain how this mirrors the real hardware: MCU reads sensor,
   drives MOSFET gate, energises electromagnet coil

---

*MagnoGlove — AI/ML Engineering Department Demo*
