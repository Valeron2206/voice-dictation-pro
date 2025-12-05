#!/usr/bin/env python3
"""
Voice Dictation Pro for macOS
Hold Option+Space → speak → release → text appears
Space to confirm, Esc to cancel

Optimized for Apple Silicon (M1/M2/M3/M4)
"""

import os
import sys
import tempfile
import threading
import time
import subprocess
import warnings
from dataclasses import dataclass
from typing import Optional

# Suppress warnings from libraries
warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import numpy as np
import sounddevice as sd
from pynput import keyboard

# PyObjC for native UI and Event Tap
try:
    import objc
    from AppKit import (
        NSApplication, NSWindow, NSView, NSTextField, NSFont,
        NSColor, NSVisualEffectView, NSVisualEffectBlendingModeBehindWindow,
        NSVisualEffectMaterialHUDWindow, NSWindowStyleMaskBorderless,
        NSBackingStoreBuffered, NSFloatingWindowLevel, NSScreen,
        NSMakeRect, NSTextAlignmentCenter, NSLineBreakByWordWrapping,
        NSApplicationActivationPolicyAccessory, NSPanel,
        NSNonactivatingPanelMask, NSUtilityWindowMask, NSEvent,
        NSScrollView, NSTextView, NSBorderlessWindowMask,
        NSViewWidthSizable, NSViewHeightSizable,
    )
    from Foundation import NSPointInRect, NSRange
    from Quartz import (
        CGEventTapCreate, CGEventTapEnable, CGEventMaskBit,
        kCGSessionEventTap, kCGHeadInsertEventTap, kCGEventTapOptionDefault,
        kCGEventKeyDown, kCGEventKeyUp, kCGEventFlagsChanged,
        CGEventGetIntegerValueField, kCGKeyboardEventKeycode,
        CGEventGetFlags, kCGEventFlagMaskAlternate,
        CFMachPortCreateRunLoopSource, CFRunLoopGetCurrent,
        CFRunLoopAddSource, kCFRunLoopCommonModes,
    )
    HAS_PYOBJC = True
except ImportError:
    HAS_PYOBJC = False

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class Config:
    # Hotkey
    hotkey_modifier: str = "alt"  # alt = Option on Mac
    hotkey_key: str = "space"

    # Recognition
    language: str = "ru"  # "ru", "en", "de", None for auto
    model: str = "mlx-community/whisper-medium-mlx"

    # Audio
    sample_rate: int = 16000

    # UX
    play_sounds: bool = True
    min_recording_duration: float = 0.3


config = Config()

# ============================================================================
# GLOBAL STATE
# ============================================================================

class AppState:
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    CONFIRMING = "confirming"

state = AppState.IDLE
audio_data = []
recording_start_time = 0
whisper_transcribe = None
overlay = None
pending_text = None
audio_stream = None

# ============================================================================
# GLASSMORPHISM OVERLAY UI
# ============================================================================

class GlassmorphismOverlay:
    """Beautiful overlay with Apple-style glassmorphism"""

    def __init__(self):
        self.window = None
        self.text_field = None
        self.status_field = None
        self.hints_field = None
        self.is_visible = False
        self.recording_indicator = None

    def create_window(self):
        if not HAS_PYOBJC:
            return

        window_width = 600
        window_height = 120

        screen = NSScreen.mainScreen()
        screen_frame = screen.frame()

        x = (screen_frame.size.width - window_width) / 2
        y = screen_frame.size.height / 2 + 100

        window_rect = NSMakeRect(x, y, window_width, window_height)

        style = NSWindowStyleMaskBorderless | NSNonactivatingPanelMask
        self.window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            window_rect, style, NSBackingStoreBuffered, False
        )

        self.window.setLevel_(NSFloatingWindowLevel)
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(NSColor.clearColor())
        self.window.setHasShadow_(True)
        self.window.setFloatingPanel_(True)
        self.window.setBecomesKeyOnlyIfNeeded_(True)
        self.window.setIgnoresMouseEvents_(True)

        content_view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, window_width, window_height))

        visual_effect = NSVisualEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, window_width, window_height)
        )
        visual_effect.setMaterial_(NSVisualEffectMaterialHUDWindow)
        visual_effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        visual_effect.setState_(1)
        visual_effect.setWantsLayer_(True)
        visual_effect.layer().setCornerRadius_(20)
        visual_effect.layer().setMasksToBounds_(True)
        visual_effect.layer().setBorderWidth_(0.5)
        visual_effect.layer().setBorderColor_(
            NSColor.colorWithWhite_alpha_(1.0, 0.2).CGColor()
        )
        content_view.addSubview_(visual_effect)

        # Recording indicator (red dot) and status text on same line
        # Status text: y=50, height=20, font=14 -> text center ~= y + 10 = 60
        # Red dot: height=10, center at 60 -> y = 60 - 5 = 55
        self.recording_indicator = NSView.alloc().initWithFrame_(NSMakeRect(20, 55, 10, 10))
        self.recording_indicator.setWantsLayer_(True)
        self.recording_indicator.layer().setCornerRadius_(5)
        self.recording_indicator.layer().setBackgroundColor_(
            NSColor.colorWithRed_green_blue_alpha_(0.9, 0.2, 0.2, 1.0).CGColor()
        )
        content_view.addSubview_(self.recording_indicator)

        self.status_field = NSTextField.alloc().initWithFrame_(NSMakeRect(38, 50, 200, 20))
        self.status_field.setStringValue_("Recording")
        self.status_field.setBezeled_(False)
        self.status_field.setDrawsBackground_(False)
        self.status_field.setEditable_(False)
        self.status_field.setSelectable_(False)
        self.status_field.setTextColor_(NSColor.whiteColor())
        self.status_field.setFont_(NSFont.boldSystemFontOfSize_(14))
        content_view.addSubview_(self.status_field)

        # Text field for displaying recognized text
        self.text_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(20, 35, window_width - 40, 50)
        )
        self.text_field.setStringValue_("")
        self.text_field.setBezeled_(False)
        self.text_field.setDrawsBackground_(False)
        self.text_field.setEditable_(False)
        self.text_field.setSelectable_(False)
        self.text_field.setTextColor_(NSColor.whiteColor())
        self.text_field.setFont_(NSFont.systemFontOfSize_(15))
        self.text_field.setAlignment_(NSTextAlignmentCenter)
        self.text_field.setLineBreakMode_(NSLineBreakByWordWrapping)
        self.text_field.setHidden_(True)
        content_view.addSubview_(self.text_field)

        self.hints_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(20, 12, window_width - 40, 20)
        )
        self.hints_field.setStringValue_("Release to stop  |  Esc — Cancel")
        self.hints_field.setBezeled_(False)
        self.hints_field.setDrawsBackground_(False)
        self.hints_field.setEditable_(False)
        self.hints_field.setSelectable_(False)
        self.hints_field.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.6))
        self.hints_field.setFont_(NSFont.systemFontOfSize_(12))
        self.hints_field.setAlignment_(NSTextAlignmentCenter)
        content_view.addSubview_(self.hints_field)

        self.window.setContentView_(content_view)

    def _move_to_active_screen(self):
        try:
            mouse_location = NSEvent.mouseLocation()
            target_screen = None
            for screen in NSScreen.screens():
                if NSPointInRect(mouse_location, screen.frame()):
                    target_screen = screen
                    break
            if target_screen is None:
                target_screen = NSScreen.mainScreen()

            screen_frame = target_screen.frame()
            window_frame = self.window.frame()
            x = screen_frame.origin.x + (screen_frame.size.width - window_frame.size.width) / 2
            y = screen_frame.origin.y + screen_frame.size.height / 2 + 100
            self.window.setFrameOrigin_((x, y))
        except:
            pass

    def show_recording(self):
        if not self.window:
            self.create_window()
        if not self.window:
            return

        def update():
            self._move_to_active_screen()
            self.status_field.setStringValue_("Recording")
            self.status_field.setHidden_(False)
            self.recording_indicator.setHidden_(False)
            self.recording_indicator.layer().setBackgroundColor_(
                NSColor.colorWithRed_green_blue_alpha_(0.9, 0.2, 0.2, 1.0).CGColor()
            )
            self.text_field.setHidden_(True)
            self.text_field.setStringValue_("")
            self.hints_field.setStringValue_("Release to stop  |  Esc — Cancel")
            self.window.orderFront_(None)
            self.is_visible = True

        self._run_on_main_thread(update)

    def show_processing(self):
        if not self.window:
            return

        def update():
            self.status_field.setStringValue_("Processing...")
            self.recording_indicator.layer().setBackgroundColor_(
                NSColor.colorWithRed_green_blue_alpha_(1.0, 0.7, 0.0, 1.0).CGColor()
            )
            self.hints_field.setStringValue_("")

        self._run_on_main_thread(update)

    def show_result(self, text: str):
        if not self.window:
            return

        def update():
            self.status_field.setHidden_(True)
            self.recording_indicator.setHidden_(True)
            display_text = text[:150] + "..." if len(text) > 150 else text
            self.text_field.setStringValue_(display_text)
            self.text_field.setHidden_(False)
            self.hints_field.setStringValue_("Space — Insert  |  Esc — Cancel")

        self._run_on_main_thread(update)

    def show_error(self, message: str):
        if not self.window:
            return

        def update():
            self.status_field.setStringValue_(message)
            self.status_field.setHidden_(False)
            self.recording_indicator.layer().setBackgroundColor_(
                NSColor.colorWithRed_green_blue_alpha_(0.9, 0.2, 0.2, 1.0).CGColor()
            )
            self.text_field.setHidden_(True)
            self.hints_field.setStringValue_("Esc — Close")

        self._run_on_main_thread(update)
        threading.Timer(2.0, self.hide).start()

    def hide(self):
        if not self.window:
            return

        def update():
            self.window.orderOut_(None)
            self.is_visible = False

        self._run_on_main_thread(update)

    def _run_on_main_thread(self, func):
        try:
            from PyObjCTools import AppHelper
            AppHelper.callAfter(func)
        except:
            func()


def init_overlay():
    global overlay
    if HAS_PYOBJC:
        overlay = GlassmorphismOverlay()
        overlay.create_window()

# ============================================================================
# SOUNDS
# ============================================================================

def play_sound(sound_name: str):
    if not config.play_sounds:
        return
    sounds = {
        "start": "/System/Library/Sounds/Pop.aiff",
        "stop": "/System/Library/Sounds/Blow.aiff",
        "error": "/System/Library/Sounds/Basso.aiff",
        "success": "/System/Library/Sounds/Glass.aiff",
    }
    sound_path = sounds.get(sound_name)
    if sound_path and os.path.exists(sound_path):
        subprocess.Popen(['afplay', sound_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)

# ============================================================================
# WHISPER
# ============================================================================

def load_whisper():
    global whisper_transcribe

    print("Loading Whisper model...")

    # Suppress library output
    import logging
    logging.getLogger("mlx_whisper").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

    try:
        # Redirect stdout/stderr during model loading
        import io
        from contextlib import redirect_stdout, redirect_stderr

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            import mlx_whisper

        def transcribe_mlx(audio_path: str) -> str:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = mlx_whisper.transcribe(
                    audio_path,
                    path_or_hf_repo=config.model,
                    language=config.language,
                    verbose=False,
                )
            return result["text"].strip()

        whisper_transcribe = transcribe_mlx

        # Warmup
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            silence = np.zeros(config.sample_rate, dtype=np.int16)
            import scipy.io.wavfile as wav
            wav.write(f.name, config.sample_rate, silence)
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    whisper_transcribe(f.name)
            except:
                pass

        print("Whisper ready!")
        return True

    except ImportError:
        try:
            from faster_whisper import WhisperModel
            fw_model = WhisperModel("large-v3", device="cpu", compute_type="int8")

            def transcribe_fw(audio_path: str) -> str:
                segments, _ = fw_model.transcribe(audio_path, language=config.language)
                return " ".join([seg.text for seg in segments]).strip()

            whisper_transcribe = transcribe_fw
            print("Faster-Whisper ready!")
            return True
        except ImportError:
            print("Error: Install mlx-whisper: pip install mlx-whisper")
            return False


def transcribe_audio(audio_path: str) -> Optional[str]:
    if whisper_transcribe is None:
        return None
    try:
        import io
        from contextlib import redirect_stdout, redirect_stderr
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return whisper_transcribe(audio_path)
    except Exception as e:
        print(f"Transcription error: {e}")
        return None

# ============================================================================
# TEXT INSERTION
# ============================================================================

def copy_to_clipboard(text: str):
    process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
    process.communicate(text.encode('utf-8'))


def paste_from_clipboard():
    try:
        if HAS_PYOBJC:
            from Quartz import (
                CGEventCreateKeyboardEvent, CGEventPost,
                kCGHIDEventTap, CGEventSetFlags, kCGEventFlagMaskCommand,
            )
            V_KEYCODE = 9
            event_down = CGEventCreateKeyboardEvent(None, V_KEYCODE, True)
            CGEventSetFlags(event_down, kCGEventFlagMaskCommand)
            event_up = CGEventCreateKeyboardEvent(None, V_KEYCODE, False)
            CGEventSetFlags(event_up, kCGEventFlagMaskCommand)
            CGEventPost(kCGHIDEventTap, event_down)
            CGEventPost(kCGHIDEventTap, event_up)
            return True
        else:
            script = 'tell application "System Events" to keystroke "v" using command down'
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=2)
            return True
    except:
        return False


def insert_text(text: str):
    if not text:
        return False
    copy_to_clipboard(text)
    time.sleep(0.05)
    if paste_from_clipboard():
        play_sound("success")
        return True
    else:
        play_sound("error")
        return False

# ============================================================================
# AUDIO RECORDING
# ============================================================================

def audio_callback(indata, frames, time_info, status):
    global audio_data
    if state == AppState.RECORDING:
        audio_data.append(indata.copy())


def start_microphone():
    global audio_stream
    if audio_stream is None:
        audio_stream = sd.InputStream(
            samplerate=config.sample_rate,
            channels=1,
            dtype='float32',
            callback=audio_callback,
            blocksize=1024
        )
        audio_stream.start()


def stop_microphone():
    global audio_stream
    if audio_stream is not None:
        audio_stream.stop()
        audio_stream.close()
        audio_stream = None


def start_recording():
    global state, audio_data, recording_start_time

    if state != AppState.IDLE:
        return

    audio_data = []
    recording_start_time = time.time()
    start_microphone()
    state = AppState.RECORDING
    play_sound("start")

    if overlay:
        overlay.show_recording()


def stop_recording():
    global state, pending_text

    if state != AppState.RECORDING:
        return

    duration = time.time() - recording_start_time
    stop_microphone()
    play_sound("stop")

    if duration < config.min_recording_duration:
        if overlay:
            overlay.show_error("Too short")
        state = AppState.IDLE
        return

    if not audio_data:
        if overlay:
            overlay.show_error("No audio")
        state = AppState.IDLE
        return

    state = AppState.PROCESSING

    if overlay:
        overlay.show_processing()

    threading.Thread(target=process_audio, daemon=True).start()


def process_audio():
    global state, pending_text

    audio_np = np.concatenate(audio_data, axis=0)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name
        import scipy.io.wavfile as wav
        wav.write(temp_path, config.sample_rate, (audio_np * 32767).astype(np.int16))

    try:
        text = transcribe_audio(temp_path)

        if text:
            pending_text = text
            state = AppState.CONFIRMING
            if overlay:
                overlay.show_result(text)
        else:
            play_sound("error")
            if overlay:
                overlay.show_error("Recognition failed")
            state = AppState.IDLE
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass


def confirm_insert():
    global pending_text, state

    if state != AppState.CONFIRMING or not pending_text:
        return

    text_to_insert = pending_text
    pending_text = None
    state = AppState.IDLE

    if overlay:
        overlay.hide()

    copy_to_clipboard(text_to_insert)
    time.sleep(0.1)

    if paste_from_clipboard():
        play_sound("success")
    else:
        play_sound("error")


def cancel_action():
    global pending_text, state

    if state == AppState.RECORDING:
        stop_microphone()

    pending_text = None
    state = AppState.IDLE

    if overlay:
        overlay.hide()

# ============================================================================
# KEYBOARD HANDLING (Quartz Event Tap)
# ============================================================================

KEYCODE_SPACE = 49
KEYCODE_ESCAPE = 53

space_pressed = False
option_was_pressed = False


def keyboard_event_callback(proxy, event_type, event, refcon):
    global space_pressed, option_was_pressed

    flags = CGEventGetFlags(event)
    option_pressed = bool(flags & kCGEventFlagMaskAlternate)

    if event_type == kCGEventKeyDown:
        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

        if keycode == KEYCODE_ESCAPE:
            if state != AppState.IDLE:
                cancel_action()
                return None

        if keycode == KEYCODE_SPACE:
            if state == AppState.CONFIRMING:
                threading.Thread(target=confirm_insert, daemon=True).start()
                return None

            if state == AppState.IDLE and option_pressed:
                space_pressed = True
                option_was_pressed = True
                start_recording()
                return None

            if state == AppState.RECORDING:
                return None

    elif event_type == kCGEventKeyUp:
        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

        if keycode == KEYCODE_SPACE:
            space_pressed = False
            if state == AppState.RECORDING:
                stop_recording()
                return None

    elif event_type == kCGEventFlagsChanged:
        if option_was_pressed and not option_pressed:
            option_was_pressed = False
            if state == AppState.RECORDING:
                stop_recording()

    return event


def setup_event_tap():
    if not HAS_PYOBJC:
        return None

    mask = (CGEventMaskBit(kCGEventKeyDown) |
            CGEventMaskBit(kCGEventKeyUp) |
            CGEventMaskBit(kCGEventFlagsChanged))

    tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionDefault,
        mask,
        keyboard_event_callback,
        None
    )

    if tap is None:
        return None

    source = CFMachPortCreateRunLoopSource(None, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes)
    CGEventTapEnable(tap, True)

    return tap


# Fallback handlers for pynput
modifier_pressed_fallback = False

def on_press(key):
    global modifier_pressed_fallback
    if key == keyboard.Key.alt or key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
        modifier_pressed_fallback = True
        return
    if key == keyboard.Key.esc:
        if state != AppState.IDLE:
            cancel_action()
        return
    if key == keyboard.Key.space:
        if state == AppState.IDLE and modifier_pressed_fallback:
            start_recording()
        elif state == AppState.CONFIRMING:
            threading.Thread(target=confirm_insert, daemon=True).start()

def on_release(key):
    global modifier_pressed_fallback
    if state == AppState.RECORDING:
        if key == keyboard.Key.space or key == keyboard.Key.alt or key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
            stop_recording()
    if key == keyboard.Key.alt or key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
        modifier_pressed_fallback = False

# ============================================================================
# CHECKS
# ============================================================================

def check_accessibility():
    try:
        result = subprocess.run(
            ['osascript', '-e', 'tell application "System Events" to return true'],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except:
        return False


def check_microphone():
    try:
        sd.rec(int(0.1 * config.sample_rate),
               samplerate=config.sample_rate, channels=1, dtype='float32')
        sd.wait()
        return True
    except:
        return False


def check_ffmpeg():
    try:
        result = subprocess.run(['which', 'ffmpeg'], capture_output=True)
        return result.returncode == 0
    except:
        return False

# ============================================================================
# MAIN
# ============================================================================

def print_banner():
    print("""
╔══════════════════════════════════════════════════════════╗
║           🎤 Voice Dictation Pro for macOS               ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║   Hold ⌥Option+Space  →  speak  →  release               ║
║   Space — confirm insert                                 ║
║   Esc — cancel                                           ║
║                                                          ║
║   Ctrl+C to exit                                         ║
╚══════════════════════════════════════════════════════════╝
    """)


def main():
    print_banner()

    print("Checking permissions...")

    if not check_accessibility():
        print("""
⚠️  Accessibility permission required!

   1. System Settings → Privacy & Security → Accessibility
   2. Click + and add your terminal app
   3. Restart the script
        """)
    else:
        print("✓ Accessibility: OK")

    if not check_microphone():
        print("""
⚠️  Microphone permission required!

   1. System Settings → Privacy & Security → Microphone
   2. Enable for your terminal app
   3. Restart the script
        """)
        sys.exit(1)
    else:
        print("✓ Microphone: OK")

    if not check_ffmpeg():
        print("""
⚠️  ffmpeg not found! Install with:
   brew install ffmpeg
        """)
        sys.exit(1)
    else:
        print("✓ ffmpeg: OK")

    if HAS_PYOBJC:
        print("✓ PyObjC: OK")
        init_overlay()
    else:
        print("⚠️ PyObjC not installed, UI unavailable")

    if not load_whisper():
        sys.exit(1)

    print("\n✓ Ready! Hold ⌥Option+Space and speak...")

    try:
        if HAS_PYOBJC:
            tap = setup_event_tap()
            if not tap:
                listener = keyboard.Listener(on_press=on_press, on_release=on_release)
                listener.start()

            from PyObjCTools import AppHelper
            NSApplication.sharedApplication().setActivationPolicy_(
                NSApplicationActivationPolicyAccessory
            )
            AppHelper.runConsoleEventLoop()
        else:
            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.start()
            listener.join()

    except KeyboardInterrupt:
        print("\n\nGoodbye!")
        stop_microphone()


if __name__ == "__main__":
    main()
