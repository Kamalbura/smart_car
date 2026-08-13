#!/usr/bin/env python3
"""Audio Diagnostics Tool for Smart Car Voice Assistant.

This script diagnoses common microphone and audio issues on Raspberry Pi:
1. Lists all audio devices
2. Tests if microphone can be opened
3. Checks for resource conflicts
4. Validates ALSA/dsnoop configuration
5. Tests Porcupine wakeword initialization

Usage:
    python -m tools.diagnose_audio
    python tools/diagnose_audio.py --verbose
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Colors for terminal output
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def print_header(title: str) -> None:
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")


def print_pass(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def print_fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def print_warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {msg}")


def print_info(msg: str) -> None:
    print(f"  {BLUE}ℹ{RESET} {msg}")


def check_alsa_devices() -> bool:
    """List ALSA capture devices."""
    print_header("ALSA Capture Devices (arecord -l)")
    
    try:
        result = subprocess.run(
            ["arecord", "-l"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        if result.returncode != 0:
            print_fail(f"arecord -l failed: {result.stderr}")
            return False
        
        output = result.stdout.strip()
        if not output or "no soundcards found" in output.lower():
            print_fail("No ALSA capture devices found!")
            return False
        
        for line in output.splitlines():
            print_info(line)
        
        print_pass("ALSA capture devices found")
        return True
    except FileNotFoundError:
        print_fail("arecord not found - ALSA utils not installed")
        return False
    except Exception as e:
        print_fail(f"Error checking ALSA: {e}")
        return False


def check_asound_conf() -> bool:
    """Check for dsnoop configuration."""
    print_header("ALSA Configuration (/etc/asound.conf)")
    
    asound_path = Path("/etc/asound.conf")
    if not asound_path.exists():
        print_warn("/etc/asound.conf does not exist")
        print_info("Run: sudo python tools/fix_audio_config.py")
        return False
    
    content = asound_path.read_text()
    
    has_dsnoop = "dsnoop" in content.lower()
    has_dmix = "dmix" in content.lower()
    has_default = "pcm.!default" in content or "pcm.default" in content
    
    if has_dsnoop:
        print_pass("dsnoop (shared capture) configured")
    else:
        print_warn("dsnoop not configured - mic sharing will fail!")
    
    if has_dmix:
        print_pass("dmix (shared playback) configured")
    
    if has_default:
        print_pass("Default PCM device configured")
    else:
        print_warn("Default PCM not set to shared device")
    
    return has_dsnoop


def check_pyaudio() -> bool:
    """Test PyAudio initialization."""
    print_header("PyAudio Device Enumeration")
    
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        
        count = pa.get_device_count()
        print_info(f"Found {count} audio devices")
        
        input_devices = []
        for i in range(count):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                input_devices.append((i, info))
        
        if not input_devices:
            print_fail("No input devices found!")
            pa.terminate()
            return False
        
        print_info(f"Input devices ({len(input_devices)}):")
        for idx, info in input_devices:
            name = info.get("name", "Unknown")
            rate = int(info.get("defaultSampleRate", 0))
            print(f"      [{idx}] {name} @ {rate} Hz")
        
        # Try to get default input
        try:
            default = pa.get_default_input_device_info()
            print_pass(f"Default input: [{default['index']}] {default['name']}")
        except Exception as e:
            print_warn(f"No default input device: {e}")
        
        pa.terminate()
        return True
        
    except ImportError:
        print_fail("PyAudio not installed!")
        print_info("Install: pip install pyaudio")
        return False
    except Exception as e:
        print_fail(f"PyAudio error: {e}")
        return False


def check_mic_access() -> bool:
    """Test opening the microphone."""
    print_header("Microphone Access Test")
    
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        
        # Try to open stream
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=512,
        )
        
        # Read a small chunk
        data = stream.read(512, exception_on_overflow=False)
        
        stream.stop_stream()
        stream.close()
        pa.terminate()
        
        if len(data) == 1024:  # 512 samples * 2 bytes
            print_pass("Successfully opened microphone and read audio")
            return True
        else:
            print_warn(f"Unexpected data size: {len(data)}")
            return False
            
    except OSError as e:
        if "Device or resource busy" in str(e):
            print_fail("Microphone is busy (another process has it open)!")
            print_info("Check for running wakeword/STT services")
            print_info("Run: fuser -v /dev/snd/*")
        else:
            print_fail(f"Cannot open microphone: {e}")
        return False
    except Exception as e:
        print_fail(f"Microphone test failed: {e}")
        return False


def check_process_conflicts() -> bool:
    """Check for processes using audio devices."""
    print_header("Process Conflicts (fuser)")
    
    try:
        result = subprocess.run(
            ["fuser", "-v", "/dev/snd/*"],
            capture_output=True,
            text=True,
            shell=False,
            timeout=5
        )
        
        output = result.stderr.strip() or result.stdout.strip()
        if output:
            print_warn("Processes using audio devices:")
            for line in output.splitlines():
                print(f"      {line}")
            return False
        else:
            print_pass("No processes holding audio devices")
            return True
            
    except FileNotFoundError:
        print_info("fuser not available - skipping check")
        return True
    except Exception as e:
        print_warn(f"Cannot check processes: {e}")
        return True


def check_porcupine() -> bool:
    """Test Porcupine wakeword initialization."""
    print_header("Porcupine Wakeword Engine")
    
    access_key = os.environ.get("PV_ACCESS_KEY")
    if not access_key:
        print_warn("PV_ACCESS_KEY not set - cannot test Porcupine")
        print_info("Set: export PV_ACCESS_KEY=your_key")
        return False
    
    try:
        import pvporcupine
        
        # Find keyword file
        keyword_paths = [
            PROJECT_ROOT / "models/wakeword/hey_robo.ppn",
            PROJECT_ROOT / "models/wakeword/hey-genny_en_raspberry-pi_v3_0_0.ppn",
        ]
        
        keyword_path = None
        for kp in keyword_paths:
            if kp.exists():
                keyword_path = kp
                break
        
        if not keyword_path:
            print_warn("No Porcupine keyword file found")
            print_info(f"Expected in: {PROJECT_ROOT / 'models/wakeword/'}")
            return False
        
        porcupine = pvporcupine.create(
            access_key=access_key,
            keyword_paths=[str(keyword_path)],
            sensitivities=[0.6],
        )
        
        print_pass(f"Porcupine initialized successfully")
        print_info(f"  Frame length: {porcupine.frame_length}")
        print_info(f"  Sample rate: {porcupine.sample_rate}")
        print_info(f"  Keyword: {keyword_path.name}")
        
        porcupine.delete()
        return True
        
    except ImportError:
        print_fail("pvporcupine not installed")
        print_info("Install: pip install pvporcupine")
        return False
    except Exception as e:
        print_fail(f"Porcupine error: {e}")
        return False


def check_faster_whisper() -> bool:
    """Test faster-whisper availability."""
    print_header("Faster-Whisper STT Engine")
    
    try:
        from faster_whisper import WhisperModel
        print_pass("faster-whisper is installed")
        
        # Check for downloaded models
        model_dir = PROJECT_ROOT / "third_party/whisper-fast"
        if model_dir.exists():
            models = list(model_dir.glob("*"))
            if models:
                print_info(f"Downloaded models: {[m.name for m in models]}")
        
        return True
    except ImportError:
        print_fail("faster-whisper not installed")
        print_info("Install: pip install faster-whisper")
        return False
    except Exception as e:
        print_warn(f"faster-whisper check: {e}")
        return False


def check_config() -> bool:
    """Validate system.yaml configuration."""
    print_header("Configuration Validation")
    
    sys.path.insert(0, str(PROJECT_ROOT))
    
    try:
        from src.core.config_loader import load_config
        cfg = load_config(PROJECT_ROOT / "config/system.yaml")
        
        # Check audio config
        audio_cfg = cfg.get("audio", {})
        unified = audio_cfg.get("use_unified_pipeline", False)
        
        if unified:
            print_pass("Unified voice pipeline enabled (recommended)")
        else:
            print_warn("Using legacy separate services")
            print_info("Enable unified pipeline: audio.use_unified_pipeline: true")
        
        # Check wakeword config
        ww_cfg = cfg.get("wakeword", {})
        if ww_cfg.get("access_key") or os.environ.get("PV_ACCESS_KEY"):
            print_pass("Porcupine access key configured")
        else:
            print_fail("Porcupine access key missing!")
        
        # Check STT config
        stt_cfg = cfg.get("stt", {})
        engine = stt_cfg.get("engine", "faster_whisper")
        print_info(f"STT engine: {engine}")
        
        return True
        
    except Exception as e:
        print_fail(f"Config validation error: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Audio diagnostics for Smart Car")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    
    print(f"\n{BOLD}Smart Car Audio Diagnostics{RESET}")
    print(f"Project Root: {PROJECT_ROOT}\n")
    
    results = {
        "ALSA Devices": check_alsa_devices(),
        "ALSA Config": check_asound_conf(),
        "Process Conflicts": check_process_conflicts(),
        "PyAudio": check_pyaudio(),
        "Mic Access": check_mic_access(),
        "Porcupine": check_porcupine(),
        "Faster-Whisper": check_faster_whisper(),
        "Configuration": check_config(),
    }
    
    # Summary
    print_header("SUMMARY")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, status in results.items():
        if status:
            print_pass(name)
        else:
            print_fail(name)
    
    print(f"\n{BOLD}Result: {passed}/{total} checks passed{RESET}")
    
    if passed < total:
        print(f"\n{YELLOW}Recommended actions:{RESET}")
        
        if not results["ALSA Config"]:
            print("  1. Run: sudo python tools/fix_audio_config.py")
        
        if not results["Process Conflicts"]:
            print("  2. Stop conflicting services:")
            print("     sudo systemctl stop wakeword stt-wrapper")
        
        if not results["Mic Access"]:
            print("  3. Check hardware connections and permissions")
        
        if not results["Configuration"]:
            print("  4. Enable unified pipeline in config/system.yaml:")
            print("     audio:")
            print("       use_unified_pipeline: true")
    
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
