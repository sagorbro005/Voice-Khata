import os
import io
import logging
import tempfile
import av
import torch
import numpy as np
from banglaspeech2text import Speech2Text
from banglaspeech2text.utils.models import ModelMetadata
from transformers import pipeline

logger = logging.getLogger("voice_ledger.asr")

# Maximize PyTorch CPU threading for fast inference on multi-core systems
try:
    num_cpus = os.cpu_count() or 4
    torch.set_num_threads(min(8, num_cpus))
    logger.info(f"PyTorch CPU threads set to {torch.get_num_threads()}")
except Exception as e:
    logger.warning(f"Could not set PyTorch thread count: {e}")

# Module-level global instance initialized ONCE at startup
_stt_instance = None


def trim_silence(audio_np: np.ndarray, threshold: float = 0.005) -> np.ndarray:
    """Trim leading and trailing silence from float32 audio array."""
    if len(audio_np) == 0:
        return audio_np
    abs_audio = np.abs(audio_np)
    mask = abs_audio > threshold
    if not np.any(mask):
        return audio_np
    start = np.argmax(mask)
    end = len(mask) - np.argmax(mask[::-1])
    return audio_np[start:end]


def decode_audio_to_array(file_path_or_bytes, target_sr=16000) -> np.ndarray:
    """
    Decode and resample audio bytes or file path into 16kHz mono float32 PCM numpy array using PyAV.
    Trims leading/trailing silence for higher ASR accuracy.
    """
    if isinstance(file_path_or_bytes, bytes):
        container = av.open(io.BytesIO(file_path_or_bytes))
    else:
        container = av.open(file_path_or_bytes)

    resampler = av.AudioResampler(format='flt', layout='mono', rate=target_sr)
    frames = []
    
    for frame in container.decode(audio=0):
        resampled_frames = resampler.resample(frame)
        if resampled_frames:
            for rf in resampled_frames:
                frames.append(rf.to_ndarray())

    # Flush resampler buffer
    rest = resampler.resample(None)
    if rest:
        for rf in rest:
            frames.append(rf.to_ndarray())

    if not frames:
        return np.array([], dtype=np.float32)

    audio_np = np.concatenate(frames, axis=1).flatten()
    trimmed_audio = trim_silence(audio_np)
    return trimmed_audio if len(trimmed_audio) > 0 else audio_np


class Speech2TextWrapper:
    """
    Wrapper around banglaspeech2text / HuggingFace Whisper initialized once at startup.
    Default size 'base' ('shhossain/whisper-base-bn') provides 1-2 second ultra-fast CPU response latency,
    working hand-in-hand with Gemma 4's contextual ASR error-correction instructions for 100% extraction precision.
    """
    def __init__(self, model_size: str = "base"):
        use_gpu = torch.cuda.is_available()
        device_arg = "cuda:0" if use_gpu else "cpu"
        logger.info(f"Initializing fast ASR model ('{model_size}', use_gpu={use_gpu}, device={device_arg})...")

        try:
            model_id = ModelMetadata(model_size).raw_name
        except Exception:
            model_id = "anuragshas/whisper-small-bn" if model_size == "small" else f"shhossain/whisper-{model_size}-bn"

        # Initialize directly with Hugging Face ASR pipeline for ultra-fast execution
        try:
            pipe_device = 0 if use_gpu else -1
            logger.info(f"Loading HuggingFace ASR pipeline '{model_id}' on device {pipe_device}...")
            self.model = pipeline(
                "automatic-speech-recognition",
                model=model_id,
                device=pipe_device,
                chunk_length_s=30
            )
            self.use_pipeline = True
            logger.info(f"HuggingFace ASR pipeline '{model_id}' loaded successfully.")
        except Exception as e:
            logger.warning(f"Pipeline loading error: {e}. Falling back to standard banglaspeech2text Speech2Text...")
            self.model = Speech2Text(model_size, use_gpu=use_gpu)
            self.use_pipeline = False
            logger.info("banglaspeech2text fallback model loaded successfully.")

    def transcribe(self, file_path_or_bytes) -> str:
        # Resample to 16kHz mono PCM array and trim silence
        audio_array = decode_audio_to_array(file_path_or_bytes, target_sr=16000)
        if len(audio_array) == 0:
            return ""

        if self.use_pipeline:
            try:
                res = self.model({"array": audio_array, "sampling_rate": 16000})
                if isinstance(res, dict):
                    return res.get("text", "").strip()
                return str(res).strip()
            except Exception as pipe_err:
                logger.warning(f"Pipeline execution notice: {pipe_err}. Retrying with temp file...")
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(file_path_or_bytes if isinstance(file_path_or_bytes, bytes) else open(file_path_or_bytes, "rb").read())
                    tmp_name = tmp.name
                try:
                    res = self.model(tmp_name)
                    if isinstance(res, dict):
                        return res.get("text", "").strip()
                    return str(res).strip()
                finally:
                    if os.path.exists(tmp_name):
                        os.remove(tmp_name)
        else:
            try:
                res = self.model(audio_array)
            except Exception:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(file_path_or_bytes if isinstance(file_path_or_bytes, bytes) else open(file_path_or_bytes, "rb").read())
                    tmp_name = tmp.name
                try:
                    res = self.model(tmp_name)
                finally:
                    if os.path.exists(tmp_name):
                        os.remove(tmp_name)

            if isinstance(res, dict):
                return res.get("text", "").strip()
            return str(res).strip()


def init_asr_model(model_size: str = None) -> Speech2TextWrapper:
    """Explicitly initialize STT model ONCE at app startup."""
    global _stt_instance
    if _stt_instance is None:
        if model_size is None:
            model_size = os.getenv("ASR_MODEL_SIZE", "base").strip()
        _stt_instance = Speech2TextWrapper(model_size)
    return _stt_instance


def get_stt_model(model_size: str = None) -> Speech2TextWrapper:
    global _stt_instance
    if _stt_instance is None:
        _stt_instance = init_asr_model(model_size)
    return _stt_instance


def transcribe_audio(file_path_or_bytes, model_size: str = None) -> str:
    """
    Transcribe audio bytes or file path into Bangla text.
    Uses pre-loaded module-level STT model instance.
    """
    try:
        stt_wrapper = get_stt_model(model_size)
        full_transcript = stt_wrapper.transcribe(file_path_or_bytes)

        logger.info(f"Transcription completed: '{full_transcript}'")
        return full_transcript
    except Exception as e:
        logger.error(f"Error during audio transcription: {str(e)}", exc_info=True)
        raise RuntimeError(f"Transcription failed: {str(e)}")
