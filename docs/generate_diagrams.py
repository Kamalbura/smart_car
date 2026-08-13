#!/usr/bin/env python3
"""Architecture Diagram Generation for Smart Car Technical Book.

Generates visual diagrams using matplotlib and graphviz.
Run: python docs/generate_diagrams.py
Output: docs/images/
"""
from __future__ import annotations

import os
from pathlib import Path

# Create output directory
OUTPUT_DIR = Path(__file__).parent / "images"
OUTPUT_DIR.mkdir(exist_ok=True)

def generate_system_architecture():
    """Generate the main system architecture diagram."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
        from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    except ImportError:
        print("matplotlib not installed. Run: pip install matplotlib")
        return
    
    fig, ax = plt.subplots(1, 1, figsize=(16, 10))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('Smart Car System Architecture', fontsize=16, fontweight='bold')
    
    # Raspberry Pi Box
    pi_box = FancyBboxPatch((0.5, 3), 7, 6.5, boxstyle="round,pad=0.1",
                            facecolor='#E3F2FD', edgecolor='#1976D2', linewidth=2)
    ax.add_patch(pi_box)
    ax.text(4, 9.2, 'Raspberry Pi 4B (The Cortex)', ha='center', fontsize=12, fontweight='bold')
    
    # Pi Components
    components_pi = [
        (1, 7.5, 'Orchestrator\n(FSM)', '#BBDEFB'),
        (3.5, 7.5, 'Voice\nPipeline', '#C8E6C9'),
        (6, 7.5, 'Vision\nPipeline', '#FFF9C4'),
        (1, 5.5, 'Gemini\nLLM', '#F8BBD9'),
        (3.5, 5.5, 'Piper\nTTS', '#FFCCBC'),
        (6, 5.5, 'Display\nRunner', '#D1C4E9'),
        (2.25, 3.5, 'LED\nRing', '#B2EBF2'),
        (4.75, 3.5, 'UART\nBridge', '#DCEDC8'),
    ]
    
    for x, y, label, color in components_pi:
        box = FancyBboxPatch((x, y), 2, 1.5, boxstyle="round,pad=0.05",
                             facecolor=color, edgecolor='black', linewidth=1)
        ax.add_patch(box)
        ax.text(x + 1, y + 0.75, label, ha='center', va='center', fontsize=8)
    
    # ESP32 Box
    esp_box = FancyBboxPatch((8.5, 3), 7, 4, boxstyle="round,pad=0.1",
                             facecolor='#FFF3E0', edgecolor='#E65100', linewidth=2)
    ax.add_patch(esp_box)
    ax.text(12, 6.7, 'ESP32 (The Brainstem)', ha='center', fontsize=12, fontweight='bold')
    
    # ESP32 Components
    components_esp = [
        (9, 5, 'Motor\nControl', '#FFCC80'),
        (11.5, 5, 'Sensor\nArray', '#A5D6A7'),
        (14, 5, 'Collision\nAvoidance', '#EF9A9A'),
        (10.25, 3.5, 'L298N\nH-Bridge', '#FFE0B2'),
        (12.75, 3.5, 'HC-SR04\nx3', '#C5E1A5'),
    ]
    
    for x, y, label, color in components_esp:
        box = FancyBboxPatch((x, y), 2, 1.3, boxstyle="round,pad=0.05",
                             facecolor=color, edgecolor='black', linewidth=1)
        ax.add_patch(box)
        ax.text(x + 1, y + 0.65, label, ha='center', va='center', fontsize=8)
    
    # UART Connection
    ax.annotate('', xy=(8.5, 4.5), xytext=(7.5, 4.5),
                arrowprops=dict(arrowstyle='<->', color='#D32F2F', lw=2))
    ax.text(8, 5, 'UART\n115200\nbaud', ha='center', fontsize=8, color='#D32F2F')
    
    # ZMQ Bus
    ax.plot([1, 7], [9.1, 9.1], 'b-', linewidth=3)
    ax.text(4, 9.3, 'ZMQ Bus (tcp://127.0.0.1:6010-6011)', ha='center', fontsize=9, color='blue')
    
    # Hardware below
    hardware = [
        (1, 0.5, 'USB\nSoundcard', '#E1BEE7'),
        (3.5, 0.5, '5MP\nCamera', '#B2DFDB'),
        (6, 0.5, 'SPI\nDisplay', '#F0F4C3'),
        (9, 0.5, 'NeoPixel\nRing', '#B3E5FC'),
        (12, 0.5, 'DC\nMotors', '#FFCDD2'),
    ]
    
    ax.text(7, 1.8, 'Hardware Layer', ha='center', fontsize=10, fontweight='bold')
    
    for x, y, label, color in hardware:
        box = FancyBboxPatch((x, y), 2.5, 1, boxstyle="round,pad=0.05",
                             facecolor=color, edgecolor='black', linewidth=1)
        ax.add_patch(box)
        ax.text(x + 1.25, y + 0.5, label, ha='center', va='center', fontsize=8)
    
    plt.tight_layout()
    output_path = OUTPUT_DIR / "system_architecture.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"Saved: {output_path}")
    plt.close()


def generate_state_machine():
    """Generate FSM diagram for the Orchestrator."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
        from matplotlib.patches import Circle, FancyArrowPatch
        import matplotlib.patheffects as pe
    except ImportError:
        print("matplotlib not installed")
        return
    
    fig, ax = plt.subplots(1, 1, figsize=(14, 8))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('Orchestrator Phase State Machine (17 Transitions)', fontsize=14, fontweight='bold')
    
    # States
    states = [
        (2, 4, 'IDLE', '#81C784'),      # Green
        (5, 6, 'LISTENING', '#64B5F6'), # Blue
        (9, 6, 'THINKING', '#FFB74D'),  # Orange
        (12, 4, 'SPEAKING', '#BA68C8'), # Purple
        (7, 1.5, 'ERROR', '#E57373'),   # Red
    ]
    
    for x, y, label, color in states:
        circle = Circle((x, y), 1, facecolor=color, edgecolor='black', linewidth=2)
        ax.add_patch(circle)
        ax.text(x, y, label, ha='center', va='center', fontsize=10, fontweight='bold')
    
    # Transitions (simplified arrows)
    transitions = [
        (2, 4, 5, 6, 'wakeword'),           # IDLE -> LISTENING
        (5, 6, 9, 6, 'stt_valid'),          # LISTENING -> THINKING
        (9, 6, 12, 4, 'llm_with_speech'),   # THINKING -> SPEAKING
        (12, 4, 2, 4, 'tts_done'),          # SPEAKING -> IDLE
        (5, 6, 2, 4, 'stt_timeout'),        # LISTENING -> IDLE
        (9, 6, 2, 4, 'llm_no_speech'),      # THINKING -> IDLE
        (2, 4, 7, 1.5, 'health_error'),     # IDLE -> ERROR
        (7, 1.5, 2, 4, 'health_ok'),        # ERROR -> IDLE
    ]
    
    for x1, y1, x2, y2, label in transitions:
        dx = x2 - x1
        dy = y2 - y1
        # Shorten arrows to not overlap circles
        scale = 0.7
        ax.annotate('', xy=(x1 + dx*scale, y1 + dy*scale), 
                   xytext=(x1 + dx*0.3, y1 + dy*0.3),
                   arrowprops=dict(arrowstyle='->', color='#424242', lw=1.5))
        ax.text((x1 + x2)/2, (y1 + y2)/2 + 0.3, label, fontsize=8, ha='center',
               path_effects=[pe.withStroke(linewidth=3, foreground='white')])
    
    plt.tight_layout()
    output_path = OUTPUT_DIR / "state_machine.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"Saved: {output_path}")
    plt.close()


def generate_message_flow():
    """Generate message sequence diagram."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed")
        return
    
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis('off')
    ax.set_title('Message Flow: Voice Command to Motor Action', fontsize=14, fontweight='bold')
    
    # Actors (vertical lines)
    actors = [
        (1, 'User'),
        (3, 'Voice\nPipeline'),
        (5, 'Orchestrator'),
        (7, 'LLM\nRunner'),
        (9, 'UART\nBridge'),
        (11, 'ESP32'),
        (13, 'Motors'),
    ]
    
    for x, name in actors:
        ax.plot([x, x], [1, 8.5], 'k--', alpha=0.3)
        ax.text(x, 9, name, ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    # Messages
    messages = [
        (1, 3, 8, '"Hey Robo"', 'red'),
        (3, 5, 7.5, 'ww.detected', 'blue'),
        (1, 3, 7, '"Move forward"', 'red'),
        (3, 5, 6.5, 'stt.transcription', 'blue'),
        (5, 7, 6, 'llm.request', 'blue'),
        (7, 5, 5.5, 'llm.response', 'green'),
        (5, 9, 5, 'nav.command', 'blue'),
        (9, 11, 4.5, 'FORWARD\\n', 'orange'),
        (11, 9, 4, 'ACK:OK', 'green'),
        (11, 13, 3.5, 'PWM signals', 'purple'),
    ]
    
    for x1, x2, y, label, color in messages:
        ax.annotate('', xy=(x2, y), xytext=(x1, y),
                   arrowprops=dict(arrowstyle='->', color=color, lw=1.5))
        ax.text((x1+x2)/2, y+0.15, label, ha='center', fontsize=8, color=color)
    
    # Timing annotations
    ax.text(0.5, 8, 'T+0ms', fontsize=8, va='center')
    ax.text(0.5, 6.5, 'T+1.8s', fontsize=8, va='center')
    ax.text(0.5, 5.5, 'T+2.8s', fontsize=8, va='center')
    ax.text(0.5, 3.5, 'T+2.82s', fontsize=8, va='center')
    
    plt.tight_layout()
    output_path = OUTPUT_DIR / "message_flow.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"Saved: {output_path}")
    plt.close()


def generate_module_dependency():
    """Generate module dependency graph."""
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch
    except ImportError:
        print("matplotlib not installed")
        return
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis('off')
    ax.set_title('Python Module Dependencies', fontsize=14, fontweight='bold')
    
    # Modules at different layers
    layers = [
        # (y, [(x, name, color), ...])
        (6.5, [(2, 'orchestrator.py', '#BBDEFB'),
               (5.5, 'unified_voice_pipeline.py', '#C8E6C9'),
               (9, 'vision_runner.py', '#FFF9C4')]),
        (4.5, [(2, 'gemini_runner.py', '#F8BBD9'),
               (5.5, 'motor_bridge.py', '#DCEDC8'),
               (9, 'display_runner.py', '#D1C4E9')]),
        (2.5, [(4, 'ipc.py', '#B2EBF2'),
               (7, 'config_loader.py', '#FFCCBC')]),
        (0.5, [(5.5, 'logging_setup.py', '#E1BEE7')]),
    ]
    
    for y, modules in layers:
        for x, name, color in modules:
            box = FancyBboxPatch((x-1.3, y-0.4), 2.6, 0.8, 
                                boxstyle="round,pad=0.05",
                                facecolor=color, edgecolor='black', linewidth=1)
            ax.add_patch(box)
            ax.text(x, y, name.replace('.py', ''), ha='center', va='center', fontsize=8)
    
    # Layer labels
    ax.text(0.5, 6.5, 'L1: Runners', fontsize=9, fontweight='bold', va='center')
    ax.text(0.5, 4.5, 'L2: Services', fontsize=9, fontweight='bold', va='center')
    ax.text(0.5, 2.5, 'L3: Core', fontsize=9, fontweight='bold', va='center')
    ax.text(0.5, 0.5, 'L4: Utils', fontsize=9, fontweight='bold', va='center')
    
    plt.tight_layout()
    output_path = OUTPUT_DIR / "module_dependency.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"Saved: {output_path}")
    plt.close()


if __name__ == "__main__":
    print("Generating Smart Car architecture diagrams...")
    generate_system_architecture()
    generate_state_machine()
    generate_message_flow()
    generate_module_dependency()
    print(f"\nAll diagrams saved to: {OUTPUT_DIR}")
