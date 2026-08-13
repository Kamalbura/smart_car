from src.core.ipc import TOPIC_WW_DETECTED, TOPIC_STT


def test_topic_constants():
    assert TOPIC_WW_DETECTED == b"ww.detected"
    assert TOPIC_STT == b"stt.transcription"
