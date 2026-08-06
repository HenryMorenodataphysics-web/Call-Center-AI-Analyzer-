import pandas as pd
import numpy as np
import torch
import transformers
import librosa
import soundfile as sf
import opensmile
from faster_whisper import WhisperModel

print("Setup OK")
print("pandas:", pd.__version__)
print("numpy:", np.__version__)
print("torch:", torch.__version__)
print("transformers:", transformers.__version__)
print("librosa:", librosa.__version__)
print("soundfile:", sf.__version__)
print("opensmile:", opensmile.__version__)
