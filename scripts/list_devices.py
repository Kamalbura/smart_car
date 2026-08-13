import pyaudio
pa = pyaudio.PyAudio()
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info.get('maxInputChannels', 0) > 0:
        print(f"{i}: {info.get('name')} ({info.get('defaultSampleRate')}Hz)")
pa.terminate()
