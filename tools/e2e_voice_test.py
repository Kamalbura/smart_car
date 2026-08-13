#!/usr/bin/env python3
"""End-to-end voice pipeline test: Wakeword → STT → LLM → TTS.

This script demonstrates the complete voice assistant flow:
1. Listen for wakeword "Hey Robo"
2. Record user speech
3. Transcribe with Faster-Whisper
4. Process with Gemini LLM
5. Speak response with Piper TTS
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Audio settings
DEVICE_RATE = 44100
TARGET_RATE = 16000
AUDIO_DEVICE = 1  # USB Audio Device


def resample(audio_44k: np.ndarray, target_len: int) -> np.ndarray:
    """Resample audio from 44100Hz to target length."""
    indices = np.linspace(0, len(audio_44k) - 1, target_len)
    return np.interp(indices, np.arange(len(audio_44k)), audio_44k).astype(np.int16)


def wait_for_wakeword(timeout: float = 30.0) -> bool:
    """Listen for wakeword 'Hey Robo'."""
    import pvporcupine
    import sounddevice as sd
    
    access_key = os.environ.get("PV_ACCESS_KEY")
    if not access_key:
        print("❌ PV_ACCESS_KEY not set!")
        return False
    
    keyword_path = PROJECT_ROOT / "models/wakeword/hey_robo.ppn"
    if not keyword_path.exists():
        print(f"❌ Keyword file not found: {keyword_path}")
        return False
    
    porcupine = pvporcupine.create(
        access_key=access_key,
        keyword_paths=[str(keyword_path)],
        sensitivities=[0.8],
    )
    
    target_frame = porcupine.frame_length
    device_frame = int(target_frame * DEVICE_RATE / TARGET_RATE) + 1
    
    print("\n🎤 Say 'HEY ROBO' to start...")
    
    detected = False
    try:
        with sd.InputStream(device=AUDIO_DEVICE, samplerate=DEVICE_RATE, channels=1, dtype='int16') as stream:
            start = time.time()
            while time.time() - start < timeout:
                audio, _ = stream.read(device_frame)
                pcm_44k = audio.flatten()
                pcm_16k = resample(pcm_44k, target_frame)
                
                result = porcupine.process(pcm_16k.tolist())
                if result >= 0:
                    print("✅ Wakeword detected!")
                    detected = True
                    break
            if not detected:
                print("⏰ Timeout waiting for wakeword")
    finally:
        porcupine.delete()
    
    return detected


def record_speech(duration: float = 5.0) -> np.ndarray:
    """Record user speech."""
    import sounddevice as sd
    
    print(f"\n🔴 Recording {duration}s... SPEAK NOW!")
    
    audio_44k = sd.rec(
        int(duration * DEVICE_RATE), 
        samplerate=DEVICE_RATE, 
        channels=1, 
        dtype='int16', 
        device=AUDIO_DEVICE
    )
    sd.wait()
    
    print("✅ Recording complete")
    
    # Resample to 16kHz
    audio_44k = audio_44k.flatten()
    target_len = int(len(audio_44k) * TARGET_RATE / DEVICE_RATE)
    audio_16k = resample(audio_44k, target_len)
    
    return audio_16k


def transcribe(audio_16k: np.ndarray) -> str:
    """Transcribe audio with Faster-Whisper."""
    from faster_whisper import WhisperModel
    
    print("\n📝 Transcribing...")
    
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    
    # Save to temp WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    
    try:
        with wave.open(wav_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(TARGET_RATE)
            wav.writeframes(audio_16k.tobytes())
        
        segments, _ = model.transcribe(wav_path, beam_size=1, language="en")
        text = " ".join(seg.text for seg in segments).strip()
    finally:
        os.unlink(wav_path)
    
    print(f"✅ You said: \"{text}\"")
    return text


def get_llm_response(user_text: str) -> str:
    """Get response from Gemini LLM."""
    import google.generativeai as genai
    import warnings
    warnings.filterwarnings('ignore')
    
    print("\n🤖 Thinking...")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "I cannot respond without an API key."
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""You are GENNY, a friendly robot assistant. 
Respond briefly and naturally to the user. Keep responses under 2 sentences.
User said: {user_text}"""
    
    try:
        response = model.generate_content(prompt)
        reply = response.text.strip()
    except Exception as e:
        reply = f"Sorry, I encountered an error: {str(e)[:50]}"
    
    print(f"✅ GENNY: \"{reply}\"")
    return reply


def speak(text: str) -> None:
    """Speak text using Piper TTS."""
    print("\n🔊 Speaking...")
    
    piper_bin = Path("/home/dev/smart_car/.venvs/ttse/bin/piper")
    model_path = Path("/home/dev/smart_car/models/piper/en_US-amy-medium.onnx")
    
    if not piper_bin.exists() or not model_path.exists():
        print(f"❌ Piper not found")
        return
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    
    try:
        # Generate speech
        proc = subprocess.run(
            [str(piper_bin), "--model", str(model_path), "--output_file", wav_path],
            input=text,
            text=True,
            capture_output=True,
        )
        
        if proc.returncode == 0:
            # Play audio
            subprocess.run(["aplay", "-D", "plughw:0,0", wav_path], capture_output=True)
            print("✅ Done speaking")
        else:
            print(f"❌ TTS error: {proc.stderr}")
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


def main():
    print("=" * 60)
    print("  🤖 GENNY Voice Assistant - End-to-End Test")
    print("=" * 60)
    
    # Step 1: Wait for wakeword
    if not wait_for_wakeword(timeout=30):
        print("\n❌ No wakeword detected. Exiting.")
        return 1
    
    # Step 2: Record speech
    audio = record_speech(duration=5.0)
    
    # Step 3: Transcribe
    user_text = transcribe(audio)
    
    if not user_text or len(user_text) < 2:
        print("\n⚠️ No speech detected. Try again.")
        speak("I didn't hear anything. Please try again.")
        return 1
    
    # Step 4: Get LLM response
    response = get_llm_response(user_text)
    
    # Step 5: Speak response
    speak(response)
    
    print("\n" + "=" * 60)
    print("  ✅ Pipeline test complete!")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
