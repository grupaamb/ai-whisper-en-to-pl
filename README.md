# AI Whisper EN→PL Meeting Pipeline

Lokalna aplikacja CLI do przetwarzania nagrań spotkań:

MP4 / WAV → Whisper (transkrypcja) → LLM (podsumowanie) → (opcjonalnie)
tłumaczenie PL

Całość działa **lokalnie**, bez wysyłania danych do chmury.

Wykorzystuje: - mlx-whisper (transkrypcja) - LM Studio Local Server
(LLM: Qwen / Bielik) - map-reduce summarization (2-step reduce) -
automatyczne wykrywanie języka (EN/PL) - cache wyników

------------------------------------------------------------------------

# 📌 Status projektu

Tryb: DEV USE\
Użycie: wewnętrzne (2--3 serwisantów)\
Docelowo: element większego systemu helpdesk

------------------------------------------------------------------------

# 🧠 Jak działa pipeline

1.  Ekstrakcja audio z pliku (ffmpeg)
2.  Wykrycie języka na próbce 60s (EN / PL)
3.  Pełna transkrypcja Whisperem
4.  Chunkowanie tekstu
5.  Map-Reduce summarization (2-step reduce)
6.  (Opcjonalnie) tłumaczenie na polski

Zasada działania: - Spotkanie PL → podsumowanie PL - Spotkanie EN →
podsumowanie EN + opcja tłumaczenia na PL

------------------------------------------------------------------------

# 🔧 Wymagania

-   macOS (Apple Silicon zalecany)
-   Python 3.11+
-   ffmpeg
-   LM Studio (Local Server uruchomiony)
-   Modele:
    -   Qwen (podsumowanie)
    -   Bielik (opcjonalnie tłumaczenia PL)

------------------------------------------------------------------------

# 📦 Instalacja (DEV)

## 1️⃣ ffmpeg

brew install ffmpeg

------------------------------------------------------------------------

## 2️⃣ Python (venv)

cd \~/asr python3 -m venv .venv source .venv/bin/activate pip install -U
pip pip install mlx-whisper tqdm

------------------------------------------------------------------------

## 3️⃣ Instalacja projektu jako CLI

W katalogu projektu:

pip install -e .

Po tym pojawi się komenda:

meeting-app

Sprawdzenie:

meeting-app --help

------------------------------------------------------------------------

# 🤖 Konfiguracja LM Studio

1.  Uruchom LM Studio
2.  Pobierz model (np. Qwen / Bielik)
3.  Kliknij Load
4.  Przejdź do zakładki Local Server
5.  Kliknij Start Server

Sprawdzenie połączenia:

curl http://localhost:1234/v1/models

------------------------------------------------------------------------

# 🚀 Użycie

## Tryb interaktywny

meeting-app

## Tryb z parametrami

meeting-app --file /ścieżka/do/pliku.mp4

Wymuszenie języka:

meeting-app --file plik.mp4 --lang pl meeting-app --file plik.mp4 --lang
en

------------------------------------------------------------------------

# 📂 Lokalizacja wyników

Pliki zapisywane są w:

\~/Downloads/transcripts_app/`<nazwa_pliku>`{=html}/

Znajdziesz tam:

-   audio.wav
-   transcript.txt
-   summary_final_en.txt
-   summary_final_pl.txt (jeśli wykonano tłumaczenie)

------------------------------------------------------------------------

# ⚡ Cache

Aplikacja wykrywa istniejące pliki: - transcript.txt -
summary_final_en.txt - summary_final_pl.txt

i pozwala użyć istniejących wyników bez ponownego liczenia.

------------------------------------------------------------------------

# 🛠️ Troubleshooting

## LM Studio HTTP 400

Najczęściej: - model nie jest załadowany - przekroczony kontekst modelu

Rozwiązanie: - sprawdź /v1/models - użyj modelu o większym kontekście

------------------------------------------------------------------------

## Brak mlx_whisper

Upewnij się, że aktywowałeś venv:

source .venv/bin/activate

------------------------------------------------------------------------

## ffmpeg not found

brew install ffmpeg

------------------------------------------------------------------------

# 📈 Roadmap

-   Profesjonalne CLI (argparse → click/typer)
-   Batch processing (wiele plików)
-   Watch folder
-   Eksport PDF
-   Speaker diarization
-   Tryb serwerowy (REST API)
-   Integracja z helpdesk

------------------------------------------------------------------------

# 👨‍💻 Autor

GrupaAMB\
Projekt: ai-whisper-en-to-pl
