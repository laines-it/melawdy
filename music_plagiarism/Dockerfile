FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 \
    MPLCONFIGDIR=/tmp/matplotlib TORCH_HOME=/data/.cache/torch \
    NUMBA_CACHE_DIR=/tmp/numba
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/music-plagiarism
COPY requirements*.txt ./
RUN pip install --no-cache-dir setuptools==75.6.0 wheel==0.45.1 Cython==3.0.11 numpy==1.26.4 \
    && pip install --no-cache-dir torch==2.5.1+cpu torchaudio==2.5.1+cpu torchvision==0.20.1+cpu \
       --extra-index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --no-build-isolation -r requirements-audio.txt
COPY install_madmom_metadata.py ./
COPY vendor/madmom_models ./vendor/madmom_models
RUN python install_madmom_metadata.py --allow-system
COPY . .
WORKDIR /data
ENTRYPOINT ["python", "/opt/music-plagiarism/run.py"]
CMD ["--help"]
