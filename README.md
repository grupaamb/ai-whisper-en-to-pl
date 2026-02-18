# AI Whisper EN→PL Meeting Pipeline

Lokalna aplikacja do przetwarzania nagrań spotkań:

MP4 / WAV → Whisper (transkrypcja) → LLM (podsumowanie) → (opcjonalnie)
tłumaczenie PL

Wszystko działa lokalnie: - Whisper (mlx-whisper) - LM Studio (Qwen /
Bielik) - Bez wysyłania danych do chmury

------------------------------------------------------------------------

## 🔧 Wymagania

-   macOS (Apple Silicon zalecany)
-   Python 3.11+
-   ffmpeg
-   LM Studio (Local Server uruchomiony)
-   Modele:
    -   Qwen (podsumowanie)
    -   Bielik (opcjonalnie do tłumaczeń PL)

------------------------------------------------------------------------

## 📦 Instalacja

### 1️⃣ ffmpeg

``` bash
brew install ffmpeg
```

### 2️⃣ Środowisko Python

``` bash
cd ~/asr
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install mlx-whisper tqdm
```

------------------------------------------------------------------------

## 🤖 Konfiguracja LM Studio

1.  Pobierz model (np. Qwen / Bielik)
2.  Kliknij **Load**
3.  Przejdź do zakładki **Local Server**
4.  Kliknij **Start Server**

Sprawdzenie:

``` bash
curl http://localhost:1234/v1/models
```

------------------------------------------------------------------------

## 🚀 Uruchamianie

``` bash
cd ~/asr
source .venv/bin/activate
python3 meeting_app.py
```

Aplikacja:

1.  Wybiera model do podsumowań
2.  Wybiera model do tłumaczeń
3.  Automatycznie wykrywa język (EN/PL)
4.  Tworzy transkrypcję
5.  Generuje podsumowanie
6.  Opcjonalnie tłumaczy na PL

------------------------------------------------------------------------

## 📂 Lokalizacja wyników

Pliki zapisywane są w:

    ~/Downloads/transcripts_app/<nazwa_pliku>/

Znajdziesz tam:

-   audio.wav
-   transcript.txt
-   summary_final_en.txt
-   summary_final_pl.txt (jeśli wykonano tłumaczenie)

------------------------------------------------------------------------

## 🧠 Jak działa pipeline

1.  Wyodrębnienie audio z pliku wideo
2.  Wykrycie języka na 60-sekundowej próbce
3.  Pełna transkrypcja Whisperem
4.  Chunkowanie tekstu
5.  2‑step reduce (map-reduce) dla stabilnego podsumowania
6.  Opcjonalne tłumaczenie

------------------------------------------------------------------------

## ⚡ Optymalna jakość

Najlepsze rezultaty:

1.  Podsumowanie w języku oryginalnym
2.  Następnie osobne tłumaczenie na polski

------------------------------------------------------------------------

## 🛠️ Troubleshooting

### Błąd LM Studio HTTP 400

Najczęściej: - Model nie jest załadowany - Kontekst przekracza limit

### Brak mlx_whisper

Upewnij się, że aktywowałeś `.venv`

``` bash
source .venv/bin/activate
```

------------------------------------------------------------------------

## 📈 Roadmap

-   Profesjonalne CLI (komenda systemowa)
-   Eksport do PDF
-   Speaker diarization
-   Batch processing wielu plików
-   Tryb automatyczny (folder watch)

------------------------------------------------------------------------

Autor: GrupaAMB\
Projekt: ai-whisper-en-to-pl
