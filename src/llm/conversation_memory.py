"""Conversation Memory Manager for Cloud LLM Context.

Cloud LLMs (Gemini, OpenAI) don't maintain session state between API calls.
This module provides a memory buffer that:
1. Stores conversation history (user utterances + assistant responses)
2. Manages context window limits (summarize old turns)
3. Tracks robot state for context injection

MEMORY ARCHITECTURE:
┌─────────────────────────────────────────────────────────────┐
│                    CONTEXT WINDOW                           │
├─────────────────────────────────────────────────────────────┤
│  [System Prompt]     ~300 tokens (robot persona/rules)      │
│  [Robot State]       ~100 tokens (vision, nav, sensors)     │
│  [Summary]           ~200 tokens (compressed old turns)     │
│  [Recent History]    ~500 tokens (last 3-5 exchanges)       │
│  [Current Query]     ~100 tokens (user's new message)       │
├─────────────────────────────────────────────────────────────┤
│  Total Budget: ~1200 tokens (safe for most LLMs)            │
└─────────────────────────────────────────────────────────────┘

USAGE:
    memory = ConversationMemory(max_turns=10)
    memory.add_user_message("What do you see?")
    memory.update_robot_state(vision={"label": "person"})
    
    context = memory.build_context()  # Full prompt for LLM
    
    # After LLM response:
    memory.add_assistant_message("I see a person ahead.")
"""
from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConversationState(Enum):
    """Conversation state machine."""
    IDLE = auto()           # No active conversation
    ACTIVE = auto()         # In conversation (waiting for user or responding)
    FOLLOW_UP = auto()      # Expecting follow-up (within timeout)
    

@dataclass
class Message:
    """Single conversation message."""
    role: str               # "user", "assistant", or "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}
    
    def __str__(self) -> str:
        return f"[{self.role}] {self.content}"


@dataclass
class RobotState:
    """Current state of the robot for context injection."""
    # Navigation
    direction: str = "stopped"          # forward, backward, left, right, stopped
    tracking_target: Optional[str] = None
    
    # Vision
    last_detection: Optional[Dict[str, Any]] = None  # {label, confidence, bbox}
    detection_timestamp: float = 0.0
    
    # Sensors (future)
    battery_level: Optional[float] = None
    obstacle_detected: bool = False
    
    def to_context_string(self) -> str:
        """Format robot state for context injection."""
        lines = []
        
        # Navigation state
        lines.append(f"Navigation: {self.direction}")
        if self.tracking_target:
            lines.append(f"Tracking: {self.tracking_target}")
        
        # Vision state (if recent)
        if self.last_detection:
            age = time.time() - self.detection_timestamp
            if age < 30:  # Only include if <30s old
                det = self.last_detection
                lines.append(
                    f"Vision: {det.get('label', 'unknown')} "
                    f"(confidence: {det.get('confidence', 0):.0%})"
                )
        
        return "\n".join(lines) if lines else "No sensor data"


class ConversationMemory:
    """Manages conversation context for stateless cloud LLMs.
    
    This class solves the problem that Cloud APIs (Gemini, GPT) don't remember
    previous turns. We maintain a local buffer and inject it with each request.
    
    Attributes:
        max_turns: Maximum conversation turns to keep in full
        max_tokens_estimate: Soft limit for context size
        conversation_timeout_s: Seconds before conversation "expires"
    """
    
    # System prompt template for the robot assistant
    SYSTEM_PROMPT_TEMPLATE = '''You are ROBO, a smart assistant for a physical robot car with camera and motors.

## YOUR CAPABILITIES:
- Move: forward, backward, left, right, stop
- See: camera with object detection (YOLO)
- Track: follow a detected object visually
- Speak: respond via text-to-speech
- Scan: do a 360° scan to map surroundings

## RESPONSE FORMAT (STRICT JSON):
{{
  "speak": "Your spoken response to the user",
  "direction": "forward" | "backward" | "left" | "right" | "stop" | "scan",
  "track": "" | "person" | "object_label"
}}

## RULES:
1. ALWAYS respond with valid JSON only - no extra text
2. If user asks to see/look, describe what vision reports
3. If user says "follow that" or "track", set track field
4. Keep "speak" under 50 words for natural speech
5. Default direction to "stop" unless user requests movement
6. Be concise and helpful - you're a robot, not a chatbot

## CURRENT ROBOT STATE:
{robot_state}

## CONVERSATION CONTEXT:
{conversation_summary}'''

    def __init__(
        self,
        max_turns: int = 10,
        max_tokens_estimate: int = 1200,
        conversation_timeout_s: float = 120.0,
    ) -> None:
        self.max_turns = max_turns
        self.max_tokens_estimate = max_tokens_estimate
        self.conversation_timeout_s = conversation_timeout_s
        
        # Message buffer (deque for efficient pop from front)
        self._messages: deque[Message] = deque(maxlen=max_turns * 2)
        
        # Summary of older messages (when buffer overflows)
        self._summary: str = ""
        
        # Robot state
        self.robot_state = RobotState()
        
        # Conversation state machine
        self._state = ConversationState.IDLE
        self._last_interaction_ts = 0.0
        
    # ─────────────────────────────────────────────────────────────────
    # Message Management
    # ─────────────────────────────────────────────────────────────────
    
    def add_user_message(self, content: str) -> None:
        """Add a user message and update state."""
        content = content.strip()
        if not content:
            return
            
        self._messages.append(Message(role="user", content=content))
        self._last_interaction_ts = time.time()
        self._state = ConversationState.ACTIVE
        
        # Check if buffer needs summarization
        self._maybe_summarize()
    
    def add_assistant_message(self, content: str) -> None:
        """Add an assistant response."""
        content = content.strip()
        if not content:
            return
            
        self._messages.append(Message(role="assistant", content=content))
        self._last_interaction_ts = time.time()
        
        # After responding, we're in follow-up state
        self._state = ConversationState.FOLLOW_UP
    
    def _maybe_summarize(self) -> None:
        """Summarize older messages if buffer is getting large."""
        # Simple strategy: when at 80% capacity, summarize oldest 50%
        if len(self._messages) >= self.max_turns * 2 * 0.8:
            old_count = len(self._messages) // 2
            old_messages = []
            for _ in range(old_count):
                if self._messages:
                    old_messages.append(self._messages.popleft())
            
            if old_messages:
                # Simple summarization (for a real system, use LLM)
                summary_parts = []
                for msg in old_messages:
                    if msg.role == "user":
                        summary_parts.append(f"User asked about: {msg.content[:50]}...")
                    else:
                        summary_parts.append(f"Assistant responded: {msg.content[:50]}...")
                
                new_summary = " ".join(summary_parts)
                if self._summary:
                    self._summary = f"{self._summary} {new_summary}"
                else:
                    self._summary = new_summary
                
                # Truncate summary if too long
                if len(self._summary) > 500:
                    self._summary = self._summary[-500:]
    
    # ─────────────────────────────────────────────────────────────────
    # Robot State
    # ─────────────────────────────────────────────────────────────────
    
    def update_robot_state(
        self,
        direction: Optional[str] = None,
        tracking_target: Optional[str] = None,
        vision: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update robot state from orchestrator events."""
        if direction is not None:
            self.robot_state.direction = direction
        if tracking_target is not None:
            self.robot_state.tracking_target = tracking_target
        if vision is not None:
            self.robot_state.last_detection = vision
            self.robot_state.detection_timestamp = time.time()
    
    # ─────────────────────────────────────────────────────────────────
    # Context Building
    # ─────────────────────────────────────────────────────────────────
    
    def build_context(self, current_query: Optional[str] = None) -> str:
        """Build the full context string for the LLM.
        
        This combines:
        1. System prompt with robot capabilities
        2. Current robot state
        3. Conversation summary (if any)
        4. Recent message history
        5. Current user query
        
        Returns:
            Complete prompt string for the LLM
        """
        # Check if conversation has expired
        if self._is_expired():
            self._clear_conversation()
        
        # Build conversation context
        conversation_parts = []
        
        # Add summary if exists
        if self._summary:
            conversation_parts.append(f"[Earlier context: {self._summary}]")
        
        # Add recent messages
        for msg in self._messages:
            prefix = "User" if msg.role == "user" else "ROBO"
            conversation_parts.append(f"{prefix}: {msg.content}")
        
        conversation_summary = "\n".join(conversation_parts) if conversation_parts else "This is the start of the conversation."
        
        # Build full prompt
        prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
            robot_state=self.robot_state.to_context_string(),
            conversation_summary=conversation_summary,
        )
        
        # Add current query if provided
        if current_query:
            prompt += f"\n\nUser's current message: {current_query}"
        
        return prompt
    
    def build_messages_format(self, current_query: str) -> List[Dict[str, str]]:
        """Build context in messages format (for chat APIs).
        
        Some APIs (OpenAI, Gemini chat) prefer a list of messages
        rather than a single prompt string.
        
        Returns:
            List of message dicts: [{"role": "...", "content": "..."}]
        """
        # Expiry is checked here for the same reason build_context() checks it:
        # someone speaking to the robot after a long silence is starting a new
        # exchange, not continuing one from an hour ago. Only build_context()
        # used to do this, so the chat-format path -- the one the deployed
        # Azure runner actually calls -- ignored conversation_timeout_s
        # entirely and replayed arbitrarily old turns.
        if self._is_expired():
            self._clear_conversation()

        messages = []

        # System message with robot state
        system_content = self.SYSTEM_PROMPT_TEMPLATE.format(
            robot_state=self.robot_state.to_context_string(),
            conversation_summary="See message history below.",
        )
        messages.append({"role": "system", "content": system_content})
        
        # Historical messages
        for msg in self._messages:
            messages.append(msg.to_dict())
        
        # Current query
        messages.append({"role": "user", "content": current_query})
        
        return messages
    
    # ─────────────────────────────────────────────────────────────────
    # State Management
    # ─────────────────────────────────────────────────────────────────
    
    def _is_expired(self) -> bool:
        """Check if conversation has timed out."""
        if self._state == ConversationState.IDLE:
            return False
        elapsed = time.time() - self._last_interaction_ts
        return elapsed > self.conversation_timeout_s
    
    def _clear_conversation(self) -> None:
        """Reset conversation state."""
        self._messages.clear()
        self._summary = ""
        self._state = ConversationState.IDLE
    
    def is_follow_up_expected(self) -> bool:
        """Check if we're expecting a follow-up from user.
        
        This helps the orchestrator decide whether to be more
        responsive to speech (lower thresholds, shorter timeout).
        """
        if self._state != ConversationState.FOLLOW_UP:
            return False
        return not self._is_expired()
    
    def get_state(self) -> ConversationState:
        """Get current conversation state."""
        if self._is_expired():
            self._clear_conversation()
        return self._state
    
    # ─────────────────────────────────────────────────────────────────
    # Persistence (optional)
    # ─────────────────────────────────────────────────────────────────
    
    def save_to_file(self, path: Path) -> None:
        """Save conversation state to JSON file."""
        data = {
            "messages": [
                {"role": m.role, "content": m.content, "timestamp": m.timestamp}
                for m in self._messages
            ],
            "summary": self._summary,
            "robot_state": {
                "direction": self.robot_state.direction,
                "tracking_target": self.robot_state.tracking_target,
            },
            "last_interaction_ts": self._last_interaction_ts,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
    
    def load_from_file(self, path: Path) -> bool:
        """Load conversation state from JSON file."""
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text())
            self._messages.clear()
            for m in data.get("messages", []):
                self._messages.append(Message(
                    role=m["role"],
                    content=m["content"],
                    timestamp=m.get("timestamp", 0),
                ))
            self._summary = data.get("summary", "")
            rs = data.get("robot_state", {})
            self.robot_state.direction = rs.get("direction", "stopped")
            self.robot_state.tracking_target = rs.get("tracking_target")
            self._last_interaction_ts = data.get("last_interaction_ts", 0)
            return True
        except Exception:
            return False
    
    # ─────────────────────────────────────────────────────────────────
    # Debug
    # ─────────────────────────────────────────────────────────────────
    
    def debug_dump(self) -> str:
        """Dump current state for debugging."""
        lines = [
            f"State: {self._state.name}",
            f"Messages: {len(self._messages)}",
            f"Summary length: {len(self._summary)}",
            f"Last interaction: {time.time() - self._last_interaction_ts:.1f}s ago",
            "---",
        ]
        for msg in self._messages:
            lines.append(str(msg))
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Quick test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    memory = ConversationMemory()
    
    # Simulate conversation
    memory.update_robot_state(direction="stopped", vision={"label": "person", "confidence": 0.92})
    memory.add_user_message("What do you see?")
    
    print("=== Context for LLM ===")
    print(memory.build_context())
    print("\n=== Debug ===")
    print(memory.debug_dump())
