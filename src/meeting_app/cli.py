#!/usr/bin/env python3
import os
import sys
import json
import time
import argparse
import subprocess
import re
from pathlib import Path
import urllib.request
import urllib.error

from tqdm import tqdm

# =========================
# KONFIGURACJA
# =========================
LMSTUDIO_BASE = os.environ.get("LMSTUDIO_BASE", "http://localhost:1234")

DEFAULT_SUMMARY_MODEL = os.environ.get("LMSTUDIO_SUMMARY_MODEL", "qwen/qwen3-vl-8b")
DEFAULT_TRANSLATE_MODEL = os.environ.get("LMSTUDIO_TRANSLATE_MODEL", "bielik-1.5b-v3.0-instruct")

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")

DEFAULT_OUT_DIR = Path(os.environ.get("OUT_DIR", str(Path.home() / "Downloads" / "transcripts_app")))

DEFAULT_CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "4000"))

PART_MAX = int(os.environ.get("PART_MAX", "500"))
FINAL_MAX = int(os.environ.get("FINAL_MAX", "900"))
TRANSLATE_MAX = int(os.environ.get("TRANSLATE_MAX", "900"))

TEMP_SUMMARY = float(os.environ.get("TEMP_SUMMARY", "0.2"))
TEMP_TRANSLATE = float(os.environ.get("TEMP_TRANSLATE", "0.1"))

TIMEOUT_SEC = int(os.environ.get("TIMEOUT_SEC", "600"))

# Retry/backoff dla LM Studio
RETRIES = int(os.environ.get("RETRIES", "4"))
BACKOFF_BASE = float(os.environ.get("BACKOFF_BASE", "1.5"))

SUPPORTED_AUDIO = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
SUPPORTED_VIDEO = {".mp4", ".mov", ".mkv", ".webm"}

PL_CHARS = set("ąćęłńóśżźĄĆĘŁŃÓŚŻŹ")


# =========================
# NARZĘDZIA
# =========================
def die(msg, code=1):
    print(f"\n[BŁĄD] {msg}")
    sys.exit(code)


def run_cmd(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        print(p.stdout)
        raise RuntimeError(f"Command failed: {cmd[0]}")
    return p.stdout


def ensure_tool(name):
    try:
        run_cmd([name, "-version"])
    except Exception:
        die(f"Nie widzę narzędzia '{name}'. Zainstaluj je i spróbuj ponownie.")


def ensure_mlx_whisper():
    try:
        run_cmd(["mlx_whisper", "--help"])
    except Exception:
        die("Nie widzę komendy 'mlx_whisper'. Upewnij się, że masz aktywne venv i zainstalowany mlx-whisper.")


def get_models():
    try:
        with urllib.request.urlopen(f"{LMSTUDIO_BASE}/v1/models", timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m["id"] for m in data.get("data", [])]
    except Exception as e:
        die(f"Nie mogę połączyć się z LM Studio Local Server. Szczegóły: {e}")


def require_model_exists(model_id, models):
    if model_id not in models:
        die(
            f"Wybrany model '{model_id}' nie istnieje w LM Studio (/v1/models).\n"
            f"Załaduj go w LM Studio lub wybierz inny."
        )


def choose_from_list(title, options, default=None):
    print(f"\n{title}")
    for i, opt in enumerate(options, 1):
        mark = " (domyślny)" if opt == default else ""
        print(f"{i}) {opt}{mark}")
    raw = input("Wybór (Enter = domyślny): ").strip()
    if raw == "" and default:
        return default
    try:
        idx = int(raw)
        return options[idx - 1]
    except Exception:
        return default or options[0]


def read_text_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text_utf8(path: Path, text: str):
    path.write_text(text, encoding="utf-8")


# =========================
# LLM (LM Studio OpenAI-compatible)
# =========================
def _post_chat(payload):
    url = f"{LMSTUDIO_BASE}/v1/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_llm(model_id, messages, max_tokens=600, temperature=0.2):
    """
    Odporne wywołanie LM Studio:
    - retry + backoff na 429 / 500 / 503 / 504
    - pokazuje body HTTP error (łatwy debug)
    """
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    for attempt in range(1, RETRIES + 1):
        try:
            out = _post_chat(payload)
            return out["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            if e.code in (429, 500, 503, 504) and attempt < RETRIES:
                sleep_s = BACKOFF_BASE ** attempt
                print(f"[LLM] HTTP {e.code}, ponawiam za {sleep_s:.1f}s...")
                time.sleep(sleep_s)
                continue
            raise RuntimeError(f"LM Studio HTTP {e.code}: {body}") from e
        except Exception as e:
            if attempt < RETRIES:
                sleep_s = BACKOFF_BASE ** attempt
                print(f"[LLM] Błąd: {e}. Ponawiam za {sleep_s:.1f}s...")
                time.sleep(sleep_s)
                continue
            raise RuntimeError(f"LM Studio error: {e}") from e


# =========================
# JĘZYK (prosta heurystyka EN/PL)
# =========================
def detect_lang_from_text(sample):
    pl_char_hits = sum(1 for c in sample if c in PL_CHARS)
    pl_words = len(
        re.findall(r"\b(i|że|nie|się|jest|dla|z|na|do|w|oraz|tak|tego|też|czy|jak)\b", sample.lower())
    )
    en_words = len(
        re.findall(r"\b(the|and|to|of|in|is|for|we|you|that|it|with|this|are)\b", sample.lower())
    )
    score_pl = pl_char_hits * 2 + pl_words
    return "pl" if score_pl >= max(2, en_words) else "en"


# =========================
# AUDIO
# =========================
def extract_audio(in_path, out_wav):
    run_cmd([
        "ffmpeg", "-y", "-i", str(in_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(out_wav)
    ])


def extract_audio_sample(in_wav, out_wav, seconds=60):
    run_cmd([
        "ffmpeg", "-y", "-i", str(in_wav),
        "-t", str(seconds),
        "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(out_wav)
    ])


# =========================
# TRANSKRYPCJA (Whisper)
# =========================
def whisper_transcribe(wav_path: Path, out_dir: Path, lang: str | None):
    cmd = [
        "mlx_whisper", "transcribe", str(wav_path),
        "--model", WHISPER_MODEL,
        "--output-dir", str(out_dir),
        "--output-format", "txt",
        "--verbose", "False",
    ]
    if lang:
        cmd += ["--language", lang]
    run_cmd(cmd)


def find_txts(out_dir: Path):
    return list(out_dir.glob("*.txt"))


def find_biggest_txt(out_dir: Path) -> Path:
    txts = find_txts(out_dir)
    if not txts:
        die("Nie znalazłem pliku .txt po transkrypcji.")
    return max(txts, key=lambda p: p.stat().st_size)


def cleanup_sample_files(out_dir: Path):
    # usuń sample.wav
    for p in out_dir.glob("sample.wav"):
        try:
            p.unlink()
        except Exception:
            pass
    # usuń transkrypcje próbki (żeby nie mieszały się z pełną)
    for p in out_dir.glob("*.txt"):
        try:
            p.unlink()
        except Exception:
            pass


# =========================
# PODSUMOWANIE
# =========================
def chunk_text(text, size):
    return [text[i:i + size] for i in range(0, len(text), size)]


def summarize_parts(model_id, text, chunk_size, lang):
    parts = chunk_text(text, chunk_size)
    summaries = []

    if lang == "pl":
        system_msg = "Jesteś precyzyjnym analitykiem spotkań. Odpowiadasz po polsku."
        user_tpl = """Podsumuj poniższy fragment transkrypcji spotkania.

Zwróć:
- Najważniejsze punkty
- Decyzje
- Zadania do wykonania
- Ryzyka

Transkrypcja:
{part}
"""
        bar_label = "Tworzenie podsumowań (części)"
    else:
        system_msg = "You are precise and structured."
        user_tpl = """Summarize this meeting section.

Return:
- Key points
- Decisions
- Action items
- Risks

Transcript:
{part}
"""
        bar_label = "Creating summaries (parts)"

    for part in tqdm(parts, desc=bar_label):
        prompt = user_tpl.format(part=part)
        summaries.append(
            call_llm(
                model_id,
                [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=PART_MAX,
                temperature=TEMP_SUMMARY
            )
        )

    return summaries


def summarize_final_two_step(model_id, partial_summaries, lang):
    """
    2-step reduce:
    - łączymy po kilka części w mniejsze bloki
    - final z tych bloków
    group_size adaptuje się do liczby części (żeby nie przekroczyć kontekstu)
    """
    if lang == "pl":
        print("Tworzenie finalnego podsumowania (2-etapowe łączenie)...")
    else:
        print("Creating final summary (2-step reduce)...")

    n = len(partial_summaries)
    if n <= 6:
        group_size = 3
    elif n <= 12:
        group_size = 4
    else:
        group_size = 3

    reduced = []

    if lang == "pl":
        reduce_system = "Jesteś precyzyjnym analitykiem spotkań. Odpowiadasz po polsku."
        reduce_user_tpl = """Połącz poniższe częściowe podsumowania w JEDNO krótkie podsumowanie.

Zwróć:
- Najważniejsze punkty
- Decyzje
- Zadania do wykonania
- Ryzyka

Podsumowania:
{items}
"""
        final_system = "Jesteś asystentem zarządu. Odpowiadasz po polsku, rzeczowo i klarownie."
        final_user_tpl = """Na podstawie poniższych podsumowań przygotuj JEDNO finalne podsumowanie spotkania.

Struktura:
1) Podsumowanie wykonawcze (5–8 zdań)
2) Decyzje kluczowe
3) Zadania do wykonania
4) Ryzyka

Podsumowania:
{items}
"""
    else:
        reduce_system = "You are a precise meeting analyst."
        reduce_user_tpl = """Combine the following partial summaries into ONE compact summary.

Return:
- Key points
- Decisions
- Action items
- Risks

Summaries:
{items}
"""
        final_system = "You are a precise executive assistant."
        final_user_tpl = """Based on the summaries below, create ONE final executive summary.

Structure:
1) Executive Summary (5–8 sentences)
2) Key decisions
3) Action items
4) Risks

Summaries:
{items}
"""

    for i in range(0, n, group_size):
        group = partial_summaries[i:i + group_size]
        reduced_summary = call_llm(
            model_id,
            [
                {"role": "system", "content": reduce_system},
                {"role": "user", "content": reduce_user_tpl.format(items=chr(10).join(group))},
            ],
            max_tokens=PART_MAX,
            temperature=TEMP_SUMMARY
        )
        reduced.append(reduced_summary)

    final_summary = call_llm(
        model_id,
        [
            {"role": "system", "content": final_system},
            {"role": "user", "content": final_user_tpl.format(items=chr(10).join(reduced))},
        ],
        max_tokens=FINAL_MAX,
        temperature=TEMP_SUMMARY
    )

    return final_summary


def translate_to_pl(model_id, text):
    prompt = f"""Przetłumacz poniższy tekst na język polski.
Zachowaj strukturę i nie dodawaj nowych informacji.

{text}
"""
    return call_llm(
        model_id,
        [
            {"role": "system", "content": "Tłumacz profesjonalnie na język polski."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=TRANSLATE_MAX,
        temperature=TEMP_TRANSLATE
    )


# =========================
# MAIN
# =========================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Ścieżka do pliku mp4/wav/etc.")
    parser.add_argument("--lang", choices=["en", "pl"], help="Wymuś język transkrypcji (inaczej auto-detect).")
    args = parser.parse_args()

    ensure_tool("ffmpeg")
    ensure_mlx_whisper()

    models = get_models()

    summary_model = choose_from_list("Model do podsumowań:", models, DEFAULT_SUMMARY_MODEL)
    translate_model = choose_from_list("Model do tłumaczeń (tylko jeśli EN → PL):", models, DEFAULT_TRANSLATE_MODEL)

    require_model_exists(summary_model, models)
    require_model_exists(translate_model, models)

    file_path = Path(args.file) if args.file else Path(
        input("Podaj ścieżkę pliku (lub przeciągnij tu z Findera): ").strip()
    )

    if not file_path.exists():
        die("Plik nie istnieje.")

    if file_path.suffix.lower() not in (SUPPORTED_AUDIO | SUPPORTED_VIDEO):
        die(f"Nieobsługiwany typ pliku: {file_path.suffix}")

    out_dir = DEFAULT_OUT_DIR / file_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    wav_path = out_dir / "audio.wav"
    sample_wav = out_dir / "sample.wav"
    transcript_file = out_dir / "transcript.txt"

    # ZMIANA: zawsze zapisujemy final w summary_final.txt (język = język spotkania)
    summary_file = out_dir / "summary_final.txt"

    # Tylko jeśli EN i user chce tłumaczenie
    summary_pl_file = out_dir / "summary_final_pl.txt"

    # [1/4] audio
    if not wav_path.exists():
        print("[1/4] Wyodrębniam audio z pliku...")
        extract_audio(file_path, wav_path)
    else:
        print("[1/4] audio.wav istnieje – pomijam wyodrębnianie.")

    # [2/4] język (sample) tylko jeśli nie wymuszono --lang
    if args.lang:
        lang = args.lang
        print(f"[2/4] Język wymuszony: {lang}")
    else:
        print("[2/4] Wykrywam język na podstawie próbki (60s)...")
        extract_audio_sample(wav_path, sample_wav, seconds=60)

        whisper_transcribe(sample_wav, out_dir, lang=None)

        sample_txt = find_biggest_txt(out_dir)
        sample_text = read_text_utf8(sample_txt)
        lang = detect_lang_from_text(sample_text)
        print(f"[OK] Wykryty język: {lang}")

        # kasujemy sample + txt po próbce, żeby nie mieszać z pełną transkrypcją
        cleanup_sample_files(out_dir)

    # [3/4] pełna transkrypcja (cache)
    if transcript_file.exists():
        use_cache = input("[3/4] Wykryto transcript.txt. Użyć istniejącej transkrypcji? [T/n]: ").strip().lower() != "n"
        if use_cache:
            transcript = read_text_utf8(transcript_file)
        else:
            try:
                transcript_file.unlink()
            except Exception:
                pass
            print("[3/4] Tworzę transkrypcję (pełne nagranie)...")
            whisper_transcribe(wav_path, out_dir, lang=lang)
            transcript_txt = find_biggest_txt(out_dir)
            transcript = read_text_utf8(transcript_txt)
            write_text_utf8(transcript_file, transcript)
    else:
        print("[3/4] Tworzę transkrypcję (pełne nagranie)...")
        whisper_transcribe(wav_path, out_dir, lang=lang)
        transcript_txt = find_biggest_txt(out_dir)
        transcript = read_text_utf8(transcript_txt)
        write_text_utf8(transcript_file, transcript)

    # [4/4] podsumowanie (cache)
    if summary_file.exists():
        use_sum_cache = input("[4/4] Wykryto summary_final.txt. Użyć istniejącego podsumowania? [T/n]: ").strip().lower() != "n"
        if use_sum_cache:
            final_summary = read_text_utf8(summary_file)
        else:
            try:
                summary_file.unlink()
            except Exception:
                pass
            print("[4/4] Tworzę podsumowanie...")
            partial = summarize_parts(summary_model, transcript, DEFAULT_CHUNK_SIZE, lang)
            final_summary = summarize_final_two_step(summary_model, partial, lang)
            write_text_utf8(summary_file, final_summary)
    else:
        print("[4/4] Tworzę podsumowanie...")
        partial = summarize_parts(summary_model, transcript, DEFAULT_CHUNK_SIZE, lang)
        final_summary = summarize_final_two_step(summary_model, partial, lang)
        write_text_utf8(summary_file, final_summary)

    # tłumaczenie do PL tylko jeśli EN
    if lang == "en":
        # cache tłumaczenia
        if summary_pl_file.exists():
            use_tr_cache = input("Wykryto summary_final_pl.txt. Użyć istniejącego tłumaczenia? [T/n]: ").strip().lower() != "n"
            if not use_tr_cache:
                try:
                    summary_pl_file.unlink()
                except Exception:
                    pass

        if not summary_pl_file.exists():
            if input("Przetłumaczyć podsumowanie na polski? [T/n]: ").strip().lower() != "n":
                print("Tłumaczę podsumowanie na polski...")
                final_pl = translate_to_pl(translate_model, final_summary)
                write_text_utf8(summary_pl_file, final_pl)

    print("\nGOTOWE ✅")
    print(f"Wyniki w: {out_dir}")
    print(f"- {transcript_file.name}")
    print(f"- {summary_file.name}")
    if summary_pl_file.exists():
        print(f"- {summary_pl_file.name}")


if __name__ == "__main__":
    main()