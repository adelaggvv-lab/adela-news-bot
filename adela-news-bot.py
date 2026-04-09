"""
AdelaBot – Asistente de Noticias con IA
.......................................
Mi asistente de escritorio que obtiene noticias en tiempo real, las resume
con GPT-4o-mini y las lee en voz alta con texto a voz.

Funciones
..............

- Navegación de noticias por tema (Economía, Deporte, Política, Sociedad, Arte)
- Resúmenes con IA, análisis contextual y puntuación de impacto
- Reproducción por voz con control de parada inmediata
- Entrada por comando de voz (speech recognition)
- Resumen diario y análisis multitema
- Modo debate neutral (dos perspectivas equilibradas)
- Memoria de sesión: Adela recuerda lo tratado en la sesión
- Gráfico de tendencias por tema consultado
- Favoritos: guardar y exportar resúmenes a TXT
- Ticker deslizante con titulares destacados del día
- Imágenes opcionales del avatar por tema (PNG)

Requisitos
----------
    pip install openai requests Pillow pygame gtts SpeechRecognition

Variables de entorno
--------------------
    OPENAI_API_KEY
    
    NEWS_API_KEY

Archivo
---
    python adela_bot.py

Mapa del código
---------------
- Utilidades de NewsAPI:
  `_is_spanish`, `_newsapi_error`, `_fetch_everything`,
  `_load_all_headlines`, `_get_articles_for_topic`
- Utilidad de texto:
  `_clean_for_tts`
- Clases de servicio:
  `AudioManager`, `VoiceRecogniser`, `NewsAI`, `AvatarAdela`
- Clase principal:
  `AdelaBot`
    - Construcción de UI
    - Ayudantes de UI
    - Servicios y saludo inicial
    - Ticker y gráfico de tendencias
    - Historial y favoritos
    - Selección de tema y flujo de IA
    - Voz, resumen diario, análisis diario, debate y preguntas
    - Acciones del menú lateral
"""

# Biblioteca 
import json
import os
import pathlib
import re
import tempfile
import threading
import time
from datetime import datetime


from dotenv import load_dotenv

load_dotenv()  # Carga variables desde .env en local.
# Librerías de terceros
import pygame
import requests
import speech_recognition as sr
import tkinter as tk
from tkinter import messagebox
from gtts import gTTS
from openai import OpenAI
from PIL import Image, ImageTk

# Configuración general

MODEL = "gpt-4o-mini"
MAX_HISTORY = 10
FAVOURITES_FILE = "favourites.json"
TICKER_REFRESH_INTERVAL = 7200  # seconds between ticker refreshes (2 hours)
CACHE_TTL = 3600  # seconds each per-topic cache entry is valid

# Temas base. Si meto uno nuevo

TOPICS = {
    "Economía": ["economia", "mercado", "bolsa", "infraion", "empresa", "banco",
                    "finanza", "pib", "deuda", "presupueso", "ibex", "euro",
                    "precio", "impuesto"],
    "Deporte":  ["deporte", "fútbol", "futbol", "baloncesto", "tenis",
                    "atletismo", "liga", "champions", "real madrid", "barcelona",
                    "selección", "gol", "nba", "mundial", "olimp"],
    "Política": ["política", "gobierno", "elecciones", "congreso", "partido",
                    "ministro", "presidente", "senado", "pp ", "psoe", "vox ",
                    "podemos", "parlament", "cortes", "diputad", "ayuso",
                    "sánchez", "feijóo"],
    "Sociedad": ["sociedad", "educacion", "sanidad", "salud", "clima",
                    "medio ambiente", "cultura", "inmigracion", "vivienda", "pensión",
                    "trabajo", "empleo", "accidente", "crimen", "suceso"],
    "Arte":     ["arte", "música", "musica", "cine", "teatro", "exposición",
                    "festival", "concierto", "película", "serie", "libro",
                    "diseño", "moda"],
}


TOPIC_QUERIES = {
    "Economía": "economia OR bolsa OR inflacion OR empresa OR mercado",
    "Deporte":  "futbol OR deporte OR liga OR baloncesto OR tenis",
    "Política": "politica OR gobierno OR congreso OR elecciones OR ministro",
    "Sociedad": "sociedad OR sanidad OR educacion OR vivienda OR empleo",
    "Arte":     "cine OR musica OR arte OR teatro OR cultura",
}

# Avatares por tema por eleccion
AVATAR_IMAGES = {
    "Economía": "avatar_economia.png",
    "Deporte":  "avatar_deporte.png",
    "Política": "avatar_politica.png",
    "Sociedad": "avatar_sociedad.png",
    "Arte":     "avatar_arte.png",
}

# Prompt principal de Adela.

SYSTEM_PROMPT = (
    "Eres Adela, presentadora de noticias española en TV. "
    "Tu tarea: redactar UN resumen periodístico de 2 frases fluidas (máx 70 palabras) "
    "en primera persona, como si lo estuvieras contando en directo. "
    "NEUTRALIDAD ABSOLUTA: "
    "— Nunca uses términos partidistas, apodos políticos ni lenguaje valorativo. "
    "— Sustituye cualquier apodo o término sesgado por el nombre oficial o neutro "
    "  (ej: 'sanchismo'→'el gobierno de Sánchez', 'podemitas'→'Podemos', "
    "  'la derecha extrema'→'la derecha', 'progres'→'la izquierda'). "
    "— Describe los hechos, no los juzgues. "
    "— Si la noticia tiene carga ideológica, usa el lenguaje más neutro posible. "
    "Usa SOLO la información del título y descripción proporcionados. "
    "NO menciones URLs. "
    "Responde SOLO con el resumen, sin etiquetas ni líneas extra."
)

# Sistema de diseño

# Paleta de colores
C_BG_DEEP    ="#020617"
C_BG_PRIMARY ="#0F172A"
C_PANEL      ="#1E293B"
C_PANEL_SEC  ="#334155"
C_BORDER     ="#1E293B"
C_BORDER_VIS ="#334155"
C_WHITE      ="#F1F5F9"
C_GREY_SEC   ="#CBD5E1"
C_GREY_MET   ="#94A3B8"
C_BLUE       ="#3B82F6"
C_BLUE_H     ="#60A5FA"
C_GREEN      ="#22C55E"
C_AMBER      ="#F59E0B"
C_RED_ERR    ="#F87171"

# Semantica para que el código UI se lea mejor.
C_BG        = C_BG_PRIMARY
C_BTN_VOZ   = C_BLUE
C_BTN_VOZ_H = C_BLUE_H
C_HIST_BG   = C_BG_DEEP
C_STATUS_OK = C_GREEN

# Tipografías 
F_LOGO_A   = ("Georgia",   21, "bold")
F_LOGO_B   = ("Segoe UI",  10, "bold")
F_TITLE    = ("Georgia",   18, "bold")
F_SUBTITLE = ("Georgia",   13, "italic")
F_BTN_MAIN = ("Segoe UI",  12, "bold")
F_BTN_NAV  = ("Segoe UI",  10, "bold")
F_BODY     = ("Segoe UI",  12)
F_META     = ("Segoe UI",   9)
F_BUBBLE   = ("Georgia",   13)
F_STATUS   = ("Segoe UI",  10, "bold")
F_HEADLINE = ("Georgia",   11)

# Utilidades de NewsAPI

# Caché compartida entre funciones de noticias.
# Nota: es simple a propósito; para app local va bien.
_cache_by_topic: dict[str, list]  = {}  # {topic: [article, …]}
_cache_ts_topic: dict[str, float] = {}  # {topic: timestamp}
_cache_all: list  = []
_cache_all_ts: float = 0.0

# Lista rápida para detectar español en titulares.
_SPANISH_WORDS = {
    "de", "la", "el", "en", "que", "con", "por", "los", "las", "del",
    "una", "un", "es", "se", "su", "al", "le", "ha", "lo", "no",
    "para", "como", "más", "pero", "sus", "fue", "son",
    "también", "tras", "ante", "sobre", "desde", "hasta", "este", "esta",
}


def _is_spanish(title: str) -> bool:
    """Devuelve True si *title* parece estar escrito en español."""
    words = set(title.lower().split())
    return len(words & _SPANISH_WORDS) >= 2


def _newsapi_error(message: str) -> str:
    """Convierte un error de NewsAPI en un mensaje más claro."""
    msg = message.lower()
    if "ratelimited" in msg or "rate" in msg or "limited" in msg:
        return "Límite de NewsAPI alcanzado. Vuelve en unos minutos."
    if "apikeyinvalid" in msg or "api key" in msg or "invalid" in msg:
        return "NEWS_API_KEY inválida. Comprueba tu clave."
    if "apikeydisabled" in msg or "disabled" in msg:
        return "NEWS_API_KEY desactivada. Revisa tu cuenta."
    if "parameterinvalid" in msg or "parameter" in msg:
        return "Parámetro de búsqueda inválido."
    return f"Error NewsAPI: {message}"
    
    
def limpiar_texto(texto):
    # elimino cosas raras que a veces vienen de la API
    if not texto:
        return ""

    texto = texto.replace("\n", " ").strip()

    # a veces vienen caracteres raros
    texto = texto.replace("’", "'").replace("“", '"')

    return texto

def _fetch_everything(news_key: str, query: str, page_size: int = 20) -> list:
    """
    Consulta NewsAPI /v2/everything para artículos en español.

    Primero prueba con ``language=es``; si hay pocos resultados, hace una
    búsqueda sin idioma y filtra localmente con :func:`_is_spanish`.
    """
    params_es = {
        "q": query, "language": "es",
        "pageSize": page_size, "sortBy": "publishedAt",
        "apiKey": news_key,
    }
    response = requests.get(
        "https://newsapi.org/v2/everything", params=params_es, timeout=15)
    data = response.json()

    if data.get("status") != "ok":
        raise Exception(_newsapi_error(
            data.get("message", data.get("code", "Error desconocido"))))

    articles = [
        a for a in data.get("articles", [])
        if a.get("title") and a.get("description") and a["title"] != "[Removed]"
    ]

  # Si salen pocos resultados en "es"(España), hacemos una segunda pasada sin idioma
  # y filtramos aquí. Es un mini hack, pero mejora cobertura.
    if len(articles) < 5:
        params_any = {
            "q": query, "pageSize": page_size,
            "sortBy": "publishedAt", "apiKey": news_key,
        }
        r2 = requests.get(
            "https://newsapi.org/v2/everything", params=params_any, timeout=15)
        data2 = r2.json()
        if data2.get("status") == "ok":
            existing_titles = {a["title"] for a in articles}
            extra = [
                a for a in data2.get("articles", [])
                if a.get("title") and a.get("description")
                and a["title"] != "[Removed]"
                and _is_spanish(a["title"])
                and a["title"] not in existing_titles
            ]
            articles.extend(extra)

    return articles


def _load_all_headlines(news_key: str) -> list:
    """
    Carga artículos de todos los temas 

    Los resultados se cachean durante :data:`CACHE_TTL` para evitar llamadas
    redundantes cuando el usuario cambia de tema rápidamente.
    """
    global _cache_all, _cache_all_ts
    now = time.time()

    if _cache_all and now - _cache_all_ts < CACHE_TTL:
        return _cache_all

    articles: list = []
    seen_titles: set = set()

    for topic, query in TOPIC_QUERIES.items():
        try:
            results = _fetch_everything(news_key, query, page_size=20)
            for article in results:
                title = article.get("title", "")
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    article["_topic"] = topic
                    articles.append(article)
        except Exception as exc:
            msg = str(exc)
  # Errores críticos: no se silencian (límite/clave rota).
            if "Límite" in msg or "inválida" in msg or "desactivada" in msg:
                raise
            continue

    if not articles:
        raise Exception("No se pudieron cargar noticias. Comprueba tu conexión.")

    _cache_all    = articles
    _cache_all_ts = now
    return articles


def _get_articles_for_topic(news_key: str, topic: str, page_size: int = 20) -> list:
    """
    Devuelve artículos para Topic usando caché compartida.

    Estrategia de selección (por orden):
    1. Artículos ya etiquetados con el tema durante la carga global.
    2. Filtrado por palabras clave en título + descripción + fuente.
    3. Todos los artículos como último recurso.
    """
    global _cache_by_topic, _cache_ts_topic
    now = time.time()

    if (topic in _cache_by_topic
            and topic in _cache_ts_topic
            and now - _cache_ts_topic[topic] < CACHE_TTL
            and _cache_by_topic[topic]):
        return _cache_by_topic[topic]

    all_articles = _load_all_headlines(news_key)

  # Paso 1: usar artículos ya etiquetados en la carga global.
    matched = [a for a in all_articles if a.get("_topic") == topic]

  # Paso 2: fallback por palabras clave.
    if len(matched) < 2:
        keywords = TOPICS.get(topic, [])
        if keywords:
            def _text(a):
                return (
                    (a.get("title") or "") + " " +
                    (a.get("description") or "") + " " +
                    (a.get("source", {}).get("name") or "")
                ).lower()
            matched = [a for a in all_articles
                       if any(kw in _text(a) for kw in keywords)]

  # Paso 3: plan B -> devolver todo lo disponible.
    if len(matched) < 2:
        matched = all_articles

    matched = matched[:page_size]
    _cache_by_topic[topic]    = matched
    _cache_ts_topic[topic] = now
    return matched

def calcular_relevancia(news):
    texto = noticia.lower()
    score = 0

    palabras_clave = ["crisis", "guerra", "inflación", "elecciones", "conflicto"]

    for palabra in palabras_clave:
        if palabra in texto:
            score += 2

    # si es muy corto, probablemente no aporta mucho
    if len(texto) < 100:
        score -= 1

    # pequeño ajuste si parece titular sensacionalista
    if "última hora" in texto:
        score += 1

    return score
    
    
    
# Utilidades de texto a voz

_EMOJI_PATTERN = re.compile(
    "[\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002300-\U000023FF"
    "\U000025A0-\U000025FF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D]+",
    flags=re.UNICODE,
)


def _clean_for_tts(text: str) -> str:
    """
    Limpia emojis y prefijos de sección antes de enviar texto a gTTS para
    que la voz suene natural y no lea signos innecesarios.
    """
    text = re.sub(r"\U0001F4CA\s*Análisis:\s*", "Análisis: ", text)
    text = re.sub(r"Perspectiva A:\n?",   "Primera perspectiva. ", text)
    text = re.sub(r"Perspectiva B:\n?",   "Segunda perspectiva. ", text)
    text = re.sub(r"DOS PERSPECTIVAS\n?", "", text)
    text = _EMOJI_PATTERN.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# AudioManager

class AudioManager:
    """
    Gestor de reproducción TTS seguro para los hilos.

    Genera un audio MP3 con gTTS y lo reproduce con pygame.mixer.
    La reproducción puede pararse en cualquier momento mediante
    :meth:`stop`, incluso mientras se genera el audio.
    """

    def __init__(self):
        self._stop_event = threading.Event()
        self._generating = False
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
        except Exception as exc:
            print(f"[AudioManager] Initialisation error: {exc}")

    def speak(self, text: str) -> None:
        """
        Convierte *text* en voz y bloquea hasta que termina (o se detiene).
        Es seguro llamarlo desde cualquier hilo.
        """
        self._stop_event.clear()
        tmp = pathlib.Path(tempfile.gettempdir()) / "adela_tts.mp3"

        try:
  # Fase 1: generar MP3 con gTTS.
            if self._stop_event.is_set():
                return
            self._generating = True
            try:
                tts = gTTS(text=text, lang="es", slow=False, tld="es")
            except Exception:
                tts = gTTS(text=text, lang="es", slow=False)
            tts.save(str(tmp))
            self._generating = False

  # Fase 2: si alguien pulsó stop, salimos antes de reproducir.
            if self._stop_event.is_set():
                return

  # Fase 3: cargar y reproducir.
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except Exception:
                pass
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(str(tmp))
            pygame.mixer.music.set_volume(1.0)
            pygame.mixer.music.play()

  # Fase 4: esperar y revisar stop cada 50 ms.
  # TODO: pasar a callback/event loop para evitar polling.
            while pygame.mixer.music.get_busy():
                if self._stop_event.is_set():
                    pygame.mixer.music.stop()
                    return
                time.sleep(0.05)

        except Exception as exc:
            print(f"[AudioManager] Playback error: {exc}")
        finally:
            self._generating = False
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except Exception:
                pass
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass

    def stop(self) -> None:
        """Immediately stop any ongoing generation or playback."""
        self._stop_event.set()
        self._generating = False
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass


# VoiceRecogniser

class VoiceRecogniser:
    """Encapsula SpeechRecognition para capturar un comando en español."""

    def __init__(self):
        self._recogniser = sr.Recognizer()
        self._mic        = sr.Microphone()

    def listen(self) -> str | None:
        """
        Graba hasta 5 segundos y devuelve el texto reconocido en minúsculas,
        o ``None`` si el reconocimiento falla.
        """
        try:
            with self._mic as source:
                self._recogniser.adjust_for_ambient_noise(source, duration=0.5)
                audio = self._recogniser.listen(
                    source, timeout=5, phrase_time_limit=5)
            return self._recogniser.recognize_google(
                audio, language="es-ES").lower()
        except Exception:
            return None


# NewsAI (OpenAI)

class NewsAI:
    """
    Envoltura ligera de OpenAI Chat Completions con las operaciones
    de IA que necesita AdelaBot.
    """

    def __init__(self, api_key: str):
        if not api_key.strip():
            raise ValueError("OPENAI_API_KEY is empty.")
        self._client = OpenAI(api_key=api_key.strip())

  # Helper interno

    def _complete(self, messages: list, max_tokens: int = 200,
                  temperature: float = 0.4) -> str:
        response = self._client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()

  # Métodos públicos

    def summarise(self, news_text: str) -> str:
        """Devuelve un resumen neutral de 2 frases de *news_text*."""
        return self._complete([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Resume esta noticia:\n\n{news_text}"},
        ])

    def analyse(self, summary: str) -> str:
        """Devuelve una frase objetiva de contexto o implicación."""
        prompt = (
            "Eres analista de noticias neutral e imparcial. "
            "Dame SOLO UNA frase de contexto o implicación objetiva (máx 25 palabras) "
            "sobre este resumen. "
            "No uses lenguaje partidista, no tomes partido, no valores si es bueno o malo. "
            "Solo describe el impacto o contexto factual:\n\n" + summary
        )
        return self._complete(
            [{"role": "system", "content": "Analista neutral y objetivo. Sin valoraciones."},
             {"role": "user",   "content": prompt}],
            max_tokens=80,
        )

    def suggest_question(self, summary: str) -> str:
        """Sugiere una pregunta natural para continuar con *summary*."""
        prompt = (
            "Sugiere UNA pregunta natural para seguir hablando "
            "sobre esta noticia (máx 20 palabras):\n\n" + summary
        )
        return self._complete(
            [{"role": "system", "content": "Conversacional."},
             {"role": "user",   "content": prompt}],
            max_tokens=60,
            temperature=0.7,
        )

    def score_impact(self, summary: str) -> int:
        """Devuelve una puntuación de impacto de 1 (muy bajo) a 5 (muy alto)."""
        prompt = (
            "Puntúa el impacto social de esta noticia: "
            "1=muy bajo, 5=muy alto. RESPUESTA SOLO NÚMERO:\n\n" + summary
        )
        raw = self._complete(
            [{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0,
        )
        try:
            return int(raw)
        except ValueError:
            return 3

    def reply_with_context(self, question: str, history: list) -> str:
        """
        Responde *question* teniendo en cuenta el *history* de la sesión.

        *history* es una lista de diccionarios ``{"role": …, "content": …}``.
        """
        messages = [
            {"role": "system", "content": (
                "Eres Adela, presentadora de noticias española, estrictamente neutral. "
                "Recuerdas todo lo que has contado en esta sesión. "
                "Responde de forma natural y concisa (máx 60 palabras), "
                "haciendo referencia a noticias anteriores si es relevante. "
                "Nunca uses lenguaje partidista ni apodos políticos. "
                "Describe los hechos con nombres oficiales y lenguaje neutro."
            )},
        ] + history + [{"role": "user", "content": question}]
        return self._complete(messages, max_tokens=150, temperature=0.6)

    def generate_debate(self, headline: str) -> tuple[str, str]:
        """
        Devuelve dos perspectivas equilibradas sobre *headline* como ``(A, B)``.
        Ninguna se presenta como superior a la otra.
        """
        prompt = (
            "Dado este titular, presenta DOS perspectivas diferentes tal y como "
            "las argumentaría cada parte implicada (ciudadanos, expertos, afectados). "
            "Reglas estrictas: "
            "— Usa el mismo tono y extensión para las dos perspectivas. "
            "— No uses palabras como 'extremista', 'radical', 'populista' ni apodos. "
            "— No indiques cuál perspectiva es más válida. "
            "— Usa nombres oficiales de partidos y cargos, nunca apodos. "
            "— Máx 40 palabras cada perspectiva.\n"
            "Formato EXACTO:\nPERSPECTIVA A: [perspectiva]\nPERSPECTIVA B: [perspectiva]\n\n"
            f"Titular: {headline}"
        )
        text = self._complete(
            [{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7,
        )
        persp_a = persp_b = ""
        for line in text.split("\n"):
            if line.startswith("PERSPECTIVA A:"):
                persp_a = line.replace("PERSPECTIVA A:", "").strip()
            elif line.startswith("PERSPECTIVA B:"):
                persp_b = line.replace("PERSPECTIVA B:", "").strip()
        if not persp_a or not persp_b:
            parts   = text.split("\n", 1)
            persp_a = parts[0].strip() if parts else "Perspectiva no disponible"
            persp_b = parts[1].strip() if len(parts) > 1 else "Perspectiva no disponible"
        return persp_a, persp_b


# Avatar widget

class AvatarAdela:
    """
    Dibuja el avatar de Adela y su burbuja de texto en un Canvas de Tkinter.

    Soporta imágenes PNG opcionales por tema (``avatar_<topic>.png``) y usa
    un marcador de respaldo cuando no se encuentra imagen.
    """

    _BUBBLE_TEXTS = {
        "normal":   "Buenas noticias. Estoy lista.",
        "speaking": "Escuchando tu voz...",
        "thinking": "Déjame pensar en lo que me comentas...",
        "happy":    "¿Qué te interesa saber ahora?",
        "error":    "No he podido procesar eso.",
        "debate":   "Veamos los dos lados de esta noticia... ⚖️",
    }

    def __init__(self, canvas: tk.Canvas, x_center: int, canvas_h: int):
        self._canvas       = canvas
        self._cx           = x_center
        self._ch           = canvas_h
        self._img_ref      = None
        self._img_cache: dict[str, ImageTk.PhotoImage] = {}
        self._current_topic: str | None = None
        self._build()
        self.set_pose("normal")

  # ── Privado ────────────────────────────────────────────────────────────

    def _load_image(self, filename: str) -> ImageTk.PhotoImage | None:
        if filename in self._img_cache:
            return self._img_cache[filename]
        for path in (filename, "mi_avatar.png"):
            try:
                img = Image.open(path).convert("RGBA")
                img.thumbnail((380, 750), Image.LANCZOS)
                tk_img = ImageTk.PhotoImage(img)
                self._img_cache[filename] = tk_img
                return tk_img
            except Exception:
                continue
        return None

    def _build(self) -> None:
        c, cx, ch = self._canvas, self._cx, self._ch
        img = self._load_image("mi_avatar.png")
        if img:
            self._img_ref  = img
            self._avatar   = c.create_image(cx, ch + 20, image=img, anchor="s")
        else:
            self._avatar   = c.create_text(
                cx, ch - 40, text=".", font=("Arial", 110), anchor="s")

  # Burbuja "redondeada" hecha con piezas superpuestas.
        BW, BH, r = 460, 110, 18
        BX1, BY1  = cx - BW // 2, 20
        BX2, BY2  = cx + BW // 2, BY1 + BH

        for shape_args in [
            {"type": "rect", "coords": (BX1 + r, BY1, BX2 - r, BY2)},
            {"type": "rect", "coords": (BX1, BY1 + r, BX2, BY2 - r)},
        ]:
            c.create_rectangle(*shape_args["coords"], fill="white", outline="")

        for ox, oy in [(BX1+r, BY1+r), (BX2-r, BY1+r),
                       (BX1+r, BY2-r), (BX2-r, BY2-r)]:
            c.create_oval(ox-r, oy-r, ox+r, oy+r, fill="white", outline="")

        c.create_polygon(
            cx - 16, BY2, cx, BY2 + 22, cx + 16, BY2,
            fill="white", outline="white")

        self._bubble_text = c.create_text(
            cx, BY1 + BH // 2,
            text=self._BUBBLE_TEXTS["normal"],
            fill="#0F172A", font=F_BUBBLE,
            width=BW - 60, justify="center",
        )

  # ── Público ────────────────────────────────────────────────────────────

    def set_pose(self, pose: str, custom_text: str | None = None) -> None:
        text = custom_text or self._BUBBLE_TEXTS.get(pose, self._BUBBLE_TEXTS["normal"])
        try:
            self._canvas.itemconfig(self._bubble_text, text=text)
        except Exception:
            pass

    def change_topic(self, topic: str) -> None:
        if topic == self._current_topic:
            return
        self._current_topic = topic
        filename = AVATAR_IMAGES.get(topic, "mi_avatar.png")
        new_img  = self._load_image(filename)
        if new_img:
            self._img_ref = new_img
            self._canvas.after(
                0, self._canvas.itemconfig,
                self._avatar, {"image": new_img})


# AdelaBot (La app principal)

class AdelaBot:
    """
    Clase principal de la aplicación.

    Construye la UI completa en Tkinter, conecta los servicios (NewsAI,
    AudioManager y VoiceRecogniser) y orquesta el flujo de obtención de
    noticias, resumen con IA y reproducción TTS.
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AdelaBot – Breaking News")
        self.root.geometry("1440x900")
        self.root.configure(bg=C_BG)
        self.root.resizable(True, True)

  # Servicios
        self._ai: NewsAI | None  = None
        self._news_key: str      = ""
        self._audio              = AudioManager()
        self._voice              = VoiceRecogniser()

  # Estado
        self._history: list                    = []
        self._favourites: list                 = self._load_favourites()
        self._session_memory: list             = []
        self._trends: dict[str, int]           = {t: 0 for t in TOPICS}
        self._ticker_text: str                 = ""
        self._ticker_pos: int                  = 0

        self._build_ui()
        self._init_services()
        self.root.after(800, self._greet)

  # Levantamos un hilo para refrescar titulares en background.
        threading.Thread(target=self._refresh_ticker_loop, daemon=True).start()

  # --- Construcción de UI

    def _build_ui(self) -> None:
        W, H   = 1440, 900
        HDR    = 70
        BODY   = H - HDR
        SB_W   = 200
        RP_W   = 320

        self.root.geometry(f"{W}x{H}")
        self.root.resizable(False, False)
        self.root.configure(bg=C_BG_DEEP)

        self._build_header(W, HDR)
        self._build_ticker(W, HDR)

        BARRA_H = 34
        canvas  = tk.Canvas(
            self.root, width=W, height=BODY - BARRA_H - 2,
            highlightthickness=0, bd=0)
        canvas.place(x=0, y=HDR + BARRA_H + 2)
        self._canvas = canvas

        self._build_background(canvas, W, BODY, SB_W, RP_W)
        self._build_sidebar(canvas, SB_W, BODY)
        self._build_avatar(canvas, W, SB_W, RP_W, BODY)
        self._build_right_panel(canvas, W, RP_W)

        self.root.after(800, self._animate_ticker)

    def _build_header(self, W: int, HDR: int) -> None:
        hdr = tk.Frame(self.root, bg=C_BG_DEEP, height=HDR)
        hdr.place(x=0, y=0, width=W, height=HDR)

  # Logo.
        logo = tk.Frame(hdr, bg=C_BG_DEEP)
        logo.pack(side="left", padx=24)
        tk.Label(logo, text="AdelaBot", font=F_LOGO_A,
                 bg=C_BG_DEEP, fg=C_WHITE).pack(side="left")
        tk.Label(logo, text="NEWS AI", font=F_LOGO_B,
                 bg=C_BG_DEEP, fg=C_BLUE).pack(side="left", pady=8)

  # Navegación por temas.
        nav = tk.Frame(hdr, bg=C_BG_DEEP)
        nav.pack(side="left", expand=True)
        self._topic_var  = tk.StringVar(value=list(TOPICS.keys())[0])
        self._topic_btns = {}
        for topic in TOPICS:
            label = topic.split(" ", 1)[-1]
            btn = tk.Button(
                nav, text=label,
                command=lambda t=topic: self._select_topic(t),
                bg=C_BG_DEEP, fg=C_GREY_SEC, font=F_BTN_NAV,
                relief="flat", cursor="hand2",
                padx=18, pady=10, bd=0,
                activebackground=C_PANEL, activeforeground=C_WHITE)
            btn.pack(side="left")
            self._topic_btns[topic] = btn
            self._hover(btn, C_PANEL, C_BG_DEEP)
        self._topic_btns[list(TOPICS.keys())[0]].config(
            fg=C_WHITE, bg=C_PANEL)

  # Estado + píldora de "última hora".
        right = tk.Frame(hdr, bg=C_BG_DEEP)
        right.pack(side="right", padx=24)
        self._lbl_status = tk.Label(
            right, text="Ready",
            bg=C_BG_DEEP, fg=C_GREEN, font=F_STATUS)
        self._lbl_status.pack(side="right", padx=(12, 0))
        pill = tk.Frame(right, bg="#1E3A5F", padx=12, pady=4)
        pill.pack(side="right")
        tk.Label(pill, text="● BREAKING NEWS",
                 font=("Georgia", 10, "bold"),
                 bg="#1E3A5F", fg=C_WHITE).pack()

        tk.Frame(self.root, bg="#1E293B", height=1).place(
            x=0, y=HDR, width=W)

    def _build_ticker(self, W: int, HDR: int) -> None:
        BARRA_H = 34
        bar = tk.Frame(self.root, bg="#1A1400", height=BARRA_H)
        bar.place(x=0, y=HDR + 1, width=W, height=BARRA_H)

        pill = tk.Frame(bar, bg="#D97706", padx=10)
        pill.pack(side="left", fill="y")
        tk.Label(pill, text="TOP 3 NOTICIAS HOY",
                 bg="#D97706", fg="#000000",
                 font=("Segoe UI", 9, "bold")).pack(expand=True)

        tk.Frame(bar, bg="#F59E0B", width=2).pack(side="left", fill="y")

        self._lbl_ticker = tk.Label(
            bar, text="  Cargando noticias del día...",
            bg="#1A1400", fg="#FCD34D",
            font=("Segoe UI", 10), anchor="w")
        self._lbl_ticker.pack(side="left", fill="both", expand=True, padx=6)

        tk.Frame(self.root, bg="#D97706", height=1).place(
            x=0, y=HDR + BARRA_H + 1, width=W)

    def _build_background(self, canvas: tk.Canvas,
                          W: int, BODY: int, SB_W: int, RP_W: int) -> None:
        try:
            bg_full = Image.open("fondo_estudio.png").resize((W, BODY), Image.LANCZOS)
        except FileNotFoundError:
            bg_full = Image.new("RGB", (W, BODY), "#0F172A")

        self._bg_ref = ImageTk.PhotoImage(bg_full)
        canvas.create_image(0, 0, image=self._bg_ref, anchor="nw")

        def _overlay(region_img, alpha=195):
            rgba = region_img.convert("RGBA")
            overlay = Image.new("RGBA", rgba.size, (5, 10, 25, alpha))
            return Image.alpha_composite(rgba, overlay)

        sb_slice = bg_full.crop((0, 0, SB_W, BODY))
        self._sb_ref = ImageTk.PhotoImage(_overlay(sb_slice))
        canvas.create_image(0, 0, image=self._sb_ref, anchor="nw")

        rp_slice = bg_full.crop((W - RP_W, 0, W, BODY))
        self._rp_ref = ImageTk.PhotoImage(_overlay(rp_slice))
        canvas.create_image(W - RP_W, 0, image=self._rp_ref, anchor="nw")

        canvas.create_line(SB_W,     0, SB_W,     BODY, fill="#334155", width=1)
        canvas.create_line(W - RP_W, 0, W - RP_W, BODY, fill="#334155", width=1)

    def _build_sidebar(self, canvas: tk.Canvas, SB_W: int, BODY: int) -> None:
        SB_BG = "#050A19"
        MENU = [
            ("-", "Inicio"),
            ("-", "Noticias de hoy"),
            ("-", "Breaking News"),
            ("-", "Análisis Diario"),
            ("-", "Tendencias"),
            ("-", "Guardadas"),
            ("", "Ajustes"),
        ]
        y = 24
        for icon, label in MENU:
            row = tk.Frame(canvas, bg=SB_BG, cursor="hand2")
            tk.Label(row, text=icon, font=("Segoe UI", 12),
                     bg=SB_BG, fg=C_GREY_SEC, width=3).pack(side="left", pady=8)
            lbl = tk.Label(row, text=label, font=F_BODY,
                           bg=SB_BG, fg=C_GREY_SEC, anchor="w")
            lbl.pack(side="left")
            canvas.create_window(SB_W // 2, y, window=row,
                                 width=SB_W - 16, anchor="n")
            for widget in (row, lbl):
                widget.bind("<Enter>", lambda e, r=row: [
                    r.config(bg="#1E3A5F"),
                    *[ch.config(bg="#1E3A5F") for ch in r.winfo_children()]])
                widget.bind("<Leave>", lambda e, r=row: [
                    r.config(bg=SB_BG),
                    *[ch.config(bg=SB_BG) for ch in r.winfo_children()]])
                widget.bind("<Button-1>",
                            lambda e, l=label: self._handle_menu(l))
            y += 52

        canvas.create_line(14, y + 4, SB_W - 14, y + 4, fill="#334155", width=1)

  # Labels ocultas para reutilizar el top-3.
        self._lbl_top1 = tk.Label(canvas, text="", bg=SB_BG, fg="#FCD34D",
                                  font=("Segoe UI", 8))
        self._lbl_top2 = tk.Label(canvas, text="", bg=SB_BG, fg="#FCD34D",
                                  font=("Segoe UI", 8))
        self._lbl_top3 = tk.Label(canvas, text="", bg=SB_BG, fg="#FCD34D",
                                  font=("Segoe UI", 8))

        ver = tk.Label(canvas, text="AdelaBot v3.0\nNews AI Assistant",
                       font=("Segoe UI", 8), bg=SB_BG,
                       fg=C_GREY_MET, justify="center")
        canvas.create_window(SB_W // 2, BODY - 20, window=ver, anchor="s")

    def _build_avatar(self, canvas: tk.Canvas,
                      W: int, SB_W: int, RP_W: int, BODY: int) -> None:
        center_x  = SB_W + (W - SB_W - RP_W) // 2
        self.avatar = AvatarAdela(canvas, center_x, BODY)

    def _build_right_panel(self, canvas: tk.Canvas, W: int, RP_W: int) -> None:
        RP_BG = "#050A19"
        RP_X  = W - RP_W
        RP_INN = RP_W - 32

        # Tarjeta de control por voz
        voz_card = tk.Frame(canvas, bg="#0D1E38", bd=0)
        tk.Label(voz_card, text="ACTIVACIÓN POR VOZ",
                 font=("Segoe UI", 8, "bold"),
                 bg="#0D1E38", fg=C_GREY_MET).pack(
            anchor="w", padx=16, pady=(14, 2))
        tk.Label(voz_card, text="Voice Control",
                 font=F_TITLE, bg="#0D1E38", fg=C_WHITE).pack(
            anchor="w", padx=16, pady=(0, 12))

        self._btn_voice = self._make_btn(
            voz_card, "Iniciar escucha", self._voice_mode,
            bg=C_BLUE, hover=C_BLUE_H, pady=13)
        self._btn_voice.pack(fill="x", padx=16, pady=(0, 8))

        self._btn_stop = tk.Button(
            voz_card, text="⏹   Detener",
            command=self._stop,
            bg="#0D1E38", fg=C_GREY_SEC,
            font=F_BTN_MAIN, relief="flat", cursor="hand2",
            pady=10, bd=0, state="disabled",
            activebackground="#7F1D1D", activeforeground=C_WHITE,
            highlightbackground="#334155", highlightthickness=1)
        self._btn_stop.pack(fill="x", padx=16, pady=(0, 8))
        self._hover(self._btn_stop, "#7F1D1D", "#0D1E38")

        btn_row1 = tk.Frame(voz_card, bg="#0D1E38")
        btn_row1.pack(fill="x", padx=16, pady=(0, 4))
        self._make_btn(btn_row1, "Resumen del día", self._daily_briefing,
                       bg="#0F3460", hover="#1A5276", pady=7,
                       font=("Segoe UI", 10, "bold")).pack(
            side="left", fill="x", expand=True, padx=(0, 3))
        self._make_btn(btn_row1, "Debate", self._debate_mode,
                       bg="#3D0C45", hover="#5B1360", pady=7,
                       font=("Segoe UI", 10, "bold")).pack(
            side="left", fill="x", expand=True, padx=(3, 0))

        btn_row2 = tk.Frame(voz_card, bg="#0D1E38")
        btn_row2.pack(fill="x", padx=16, pady=(0, 14))
        self._make_btn(btn_row2, "Preguntar a Adela", self._ask_adela,
                       bg="#0F4C2A", hover="#1A6B3C", pady=7,
                       font=("Segoe UI", 10, "bold")).pack(fill="x")

        canvas.create_window(RP_X + RP_W // 2, 16,
                             window=voz_card, width=RP_INN, anchor="n")

        # Tarjeta de resumen
        res_frame = tk.Frame(canvas, bg=RP_BG, bd=0)
        tk.Label(res_frame, text="ÚLTIMO RESUMEN",
                 font=("Segoe UI", 8, "bold"),
                 bg=RP_BG, fg=C_GREY_MET).pack(anchor="w", pady=(0, 6))
        res_card = tk.Frame(res_frame, bg="#0D1E38")
        res_card.pack(fill="x")
        self._lbl_summary = tk.Label(
            res_card,
            text="Inicia una conversación\npara ver el resumen aquí.",
            bg="#0D1E38", fg=C_GREY_SEC,
            font=("Georgia", 11),
            wraplength=RP_INN - 28, justify="left",
            pady=14, padx=14)
        self._lbl_summary.pack(fill="x")

        fav_row = tk.Frame(res_frame, bg=RP_BG)
        fav_row.pack(fill="x", pady=(6, 0))
        self._make_btn(fav_row, "Guardar", self._save_current_summary,
                       bg="#1A3A1A", hover="#22C55E", pady=6,
                       font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        canvas.create_window(RP_X + RP_W // 2, 300,
                             window=res_frame, width=RP_INN, anchor="n")

        # Indicador de impacto
        impact_frame = tk.Frame(canvas, bg="#0D1E38", bd=0)
        impact_row   = tk.Frame(impact_frame, bg="#0D1E38")
        impact_row.pack(fill="x", padx=10, pady=8)
        tk.Label(impact_row, text="IMPACTO:",
                 font=("Segoe UI", 9, "bold"),
                 bg="#0D1E38", fg=C_GREY_MET).pack(side="left")
        self._lbl_impact = tk.Label(
            impact_row, text="  — sin datos —",
            bg="#0D1E38", fg=C_GREY_MET,
            font=("Segoe UI", 11, "bold"))
        self._lbl_impact.pack(side="left", padx=(8, 0))
        canvas.create_window(RP_X + RP_W // 2, 590,
                             window=impact_frame, width=RP_INN, anchor="n")

        # Historial + gráfico de tendencias
        hist_frame = tk.Frame(canvas, bg=RP_BG, bd=0)
        tk.Label(hist_frame, text="TITULARES RECIENTES",
                 font=("Segoe UI", 8, "bold"),
                 bg=RP_BG, fg=C_GREY_MET).pack(anchor="w", pady=(0, 4))
        self._history_box = tk.Listbox(
            hist_frame, height=5,
            bg="#0D1E38", fg=C_GREY_SEC,
            font=F_HEADLINE,
            selectbackground="#1E3A5F", selectforeground=C_WHITE,
            relief="flat", activestyle="none",
            borderwidth=0, highlightthickness=0)
        self._history_box.pack(fill="x")
        self._history_box.bind("<<ListboxSelect>>", self._view_history_item)

        tk.Label(hist_frame, text="TENDENCIAS SESIÓN",
                 font=("Segoe UI", 8, "bold"),
                 bg=RP_BG, fg=C_GREY_MET).pack(anchor="w", pady=(10, 2))
        self._trends_canvas = tk.Canvas(
            hist_frame, width=260, height=120,
            bg="#0D1E38", highlightthickness=0)
        self._trends_canvas.pack(fill="x")
        self._redraw_trends()

        canvas.create_window(RP_X + RP_W // 2, 630,
                             window=hist_frame, width=RP_INN, anchor="n")

  # --- Ayudantes de widgets UI

    def _ui(self, fn, *args, **kwargs) -> None:
        """Programa *fn* para ejecutarse en el hilo principal de Tk."""
        self.root.after(0, fn, *args, **kwargs)

    def _hover(self, widget: tk.Widget, on_bg: str, off_bg: str) -> None:
        widget.bind("<Enter>", lambda e: widget.config(bg=on_bg))
        widget.bind("<Leave>", lambda e: widget.config(bg=off_bg))

    def _make_btn(self, parent, text: str, cmd,
                  bg: str, fg: str = None, font=None,
                  hover: str = None, pady: int = 12,
                  width: int = None) -> tk.Button:
        kw = dict(
            text=text, command=cmd, bg=bg,
            fg=fg or C_WHITE,
            font=font or F_BTN_MAIN,
            relief="flat", cursor="hand2",
            activebackground=hover or bg,
            activeforeground=C_WHITE,
            pady=pady, bd=0,
        )
        if width:
            kw["width"] = width
        btn = tk.Button(parent, **kw)
        if hover:
            self._hover(btn, hover, bg)
        return btn

    def _set_status(self, text: str, color: str = C_STATUS_OK) -> None:
        self._lbl_status.config(text=text, fg=color)

    def _set_summary(self, text: str) -> None:
        self._lbl_summary.config(text=text)

    def _set_impact(self, score: int) -> None:
        bars  = "■" * score + "□" * (5 - score)
        color = "#EF4444" if score <= 2 else ("#F97316" if score == 3 else "#22C55E")
        level = "Bajo"    if score <= 2 else ("Medio"   if score == 3 else "Alto")
        self._lbl_impact.config(text=f"{bars}  {level} ({score}/5)", fg=color)

  # Aqui se inicia

    def _init_services(self) -> None:
        openai_key = os.getenv("OPENAI_API_KEY", "")
        news_key   = os.getenv("NEWS_API_KEY", "")
        openai_ok = news_ok = False

        if openai_key:
            try:
                self._ai = NewsAI(openai_key)
                openai_ok = True
            except Exception:
                pass

        if news_key:
            self._news_key = news_key
            news_ok = True

        if openai_ok and news_ok:
            self._lbl_status.config(text="TODO LISTO", fg=C_STATUS_OK)
        elif openai_ok:
            self._lbl_status.config(
                text="OpenAI OK · NewsAPI no encontrada", fg=C_STATUS_OK)
        elif news_ok:
            self._lbl_status.config(
                text="OpenAI no encontrada · NewsAPI OK", fg=C_GREY_SEC)
        else:
            self._lbl_status.config(
                text="Faltan claves en variables de entorno", fg=C_RED_ERR)

    def _greet(self) -> None:
        text = "Buenos días. Soy Adela, tu asistente de noticias. ¿Qué quieres saber hoy?"
        self._set_summary(text)
        self.avatar.set_pose("normal", text)
        if self._ai and self._news_key:
            threading.Thread(
                target=self._audio.speak, args=(text,), daemon=True).start()

  # Ticker de titulares

    def _refresh_ticker_loop(self) -> None:
        """Background daemon: reload the top headlines every 2 hours."""
        while True:
            if self._news_key:
                try:
                    articles = _load_all_headlines(self._news_key)
                    titles   = []
                    for a in articles:
                        t = a.get("title", "").strip()
                        if t and len(t) > 10:
                            titles.append(t)
                        if len(titles) == 3:
                            break
                    if titles:
                        self._ticker_text = (
                            "   1. " + titles[0] + "   ·   " +
                            (f"2. {titles[1]}   ·   " if len(titles) > 1 else "") +
                            (f"3. {titles[2]}   ·   " if len(titles) > 2 else "")
                        )
                        self._ticker_pos = 0
                        if hasattr(self, "_lbl_top1"):
                            self._ui(self._update_top3)
                except Exception:
                    pass
            time.sleep(TICKER_REFRESH_INTERVAL)

    def _update_top3(self) -> None:
        titles = []
        for a in _cache_all:
            t = a.get("title", "").strip()
            if t and len(t) > 10:
                titles.append(t[:60] + "..." if len(t) > 60 else t)
            if len(titles) == 3:
                break
        for i, lbl in enumerate((self._lbl_top1, self._lbl_top2, self._lbl_top3)):
            lbl.config(text=f"{i+1}. {titles[i]}" if i < len(titles) else "")

    def _animate_ticker(self) -> None:
        try:
            if self._ticker_text:
                length  = len(self._ticker_text)
                pos     = self._ticker_pos % length
                visible = (self._ticker_text[pos:] + "   " +
                           self._ticker_text[:pos])
                self._lbl_ticker.config(text=visible[:160])
                self._ticker_pos += 1
        except Exception:
            pass
        self.root.after(100, self._animate_ticker)

  # Gráfico de tendencias

    def _redraw_trends(self) -> None:
        """Redraw the session-trend bar chart."""
        canvas = self._trends_canvas
        W, H   = 260, 120
        canvas.delete("bars")

        values  = list(self._trends.values())
        maximum = max(values) if any(v > 0 for v in values) else 1
        n       = len(self._trends)
        bar_w   = (W - 20) // n
        colours = ["#3B82F6", "#22C55E", "#F59E0B", "#A78BFA", "#F472B6"]

        for i, (topic, count) in enumerate(self._trends.items()):
            bar_h = max(4, int((count / maximum) * (H - 24)))
            x1 = 10 + i * bar_w + 4
            x2 = x1 + bar_w - 8
            y2 = H - 16
            y1 = y2 - bar_h
            canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=colours[i % len(colours)], outline="", tags="bars")
            canvas.create_text(
                (x1 + x2) // 2, y2 + 6,
                text=str(count), fill=C_GREY_SEC,
                font=("Segoe UI", 7), tags="bars")
            canvas.create_text(
                (x1 + x2) // 2, H - 4,
                text=topic.split(" ")[0], fill=C_GREY_MET,
                font=("Segoe UI", 8), tags="bars")

  # Historial de noticias

    def _add_to_history(self, summary: str, topic: str = "") -> None:
        hour  = datetime.now().strftime("%H:%M")
        topic = topic or self._topic_var.get()
        self._history.insert(0, {"hour": hour, "summary": summary, "topic": topic})
        if len(self._history) > MAX_HISTORY:
            self._history.pop()
        self._history_box.delete(0, tk.END)
        for item in self._history:
            preview = (item["summary"][:60] + "…") \
                if len(item["summary"]) > 60 else item["summary"]
            self._history_box.insert(tk.END, f"[{item['hour']}] {preview}")

    def _view_history_item(self, event) -> None:
        sel = self._history_box.curselection()
        if not sel:
            return
        item    = self._history[sel[0]]
        summary = item["summary"]
        self._set_summary(summary)
        self._ui(self.avatar.set_pose, "speaking",
                 f"{summary[:90]}{'…' if len(summary) > 90 else ''}")
        self._ui(lambda: self._btn_stop.config(state="normal",  fg=C_GREY_SEC))
        self._ui(lambda: self._btn_voice.config(state="disabled"))

        def _play():
            self._audio.speak(summary)
            self._ui(self.avatar.set_pose, "normal")
            self._ui(lambda: self._btn_stop.config(state="disabled",  fg=C_GREY_SEC))
            self._ui(lambda: self._btn_voice.config(state="normal"))

        threading.Thread(target=_play, daemon=True).start()

  # Favoritos

    def _load_favourites(self) -> list:
        try:
            if os.path.exists(FAVOURITES_FILE):
                with open(FAVOURITES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_favourite(self, summary: str, topic: str) -> None:
        entry = {
            "date":  datetime.now().strftime("%Y-%m-%d %H:%M"),
            "topic": topic,
            "text":  summary,
        }
        self._favourites.insert(0, entry)
        try:
            with open(FAVOURITES_FILE, "w", encoding="utf-8") as f:
                json.dump(self._favourites, f, ensure_ascii=False, indent=2)
            self._ui(self._set_status, "Guardado en favoritos", C_STATUS_OK)
        except Exception as exc:
            self._ui(self._set_status, f". Error guardando: {exc}", C_RED_ERR)

    def _save_current_summary(self) -> None:
        text = self._lbl_summary.cget("text")
        if not text or text.startswith("Inicia una"):
            messagebox.showinfo("Sin contenido", "No hay resumen que guardar.")
            return
        topic = self._topic_var.get()
        threading.Thread(
            target=self._save_favourite,
            args=(text, topic), daemon=True).start()

    def _export_favourites(self) -> None:
        if not self._favourites:
            messagebox.showinfo("Favoritos", "No hay favoritos guardados aún.")
            return
        filename = f"favoritos_{datetime.now().strftime('%Y%m%d')}.txt"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"AdelaBot — Favoritos del "
                        f"{datetime.now().strftime('%d/%m/%Y')}\n")
                f.write("=" * 60 + "\n\n")
                for item in self._favourites:
                    f.write(f"[{item['date']}] {item['topic']}\n")
                    f.write(item["text"] + "\n")
                    f.write("-" * 40 + "\n\n")
            messagebox.showinfo("Exportado",
                                f"Favoritos guardados en:\n{filename}")
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo exportar: {exc}")

    def _show_favourites_window(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Favoritos guardados")
        win.geometry("600x400")
        win.configure(bg=C_BG_DEEP)
        tk.Label(win, text=Favoritos", font=F_TITLE,
                 bg=C_BG_DEEP, fg=C_WHITE).pack(pady=(16, 8))

        if not self._favourites:
            tk.Label(win,
                     text="No hay favoritos guardados aún.\n"
                          "Usa el botón Guardar para añadir.",
                     bg=C_BG_DEEP, fg=C_GREY_SEC, font=F_BODY).pack(pady=20)
        else:
            lb = tk.Listbox(
                win, bg=C_PANEL, fg=C_GREY_SEC,
                font=F_HEADLINE, relief="flat",
                selectbackground="#1E3A5F", selectforeground=C_WHITE,
                borderwidth=0, highlightthickness=0, height=14)
            lb.pack(fill="both", expand=True, padx=16, pady=(0, 8))
            for item in self._favourites:
                preview = item["text"][:70] + "…" if len(item["text"]) > 70 \
                    else item["text"]
                lb.insert(tk.END,
                          f"[{item['date']}] {item['topic']} — {preview}")

        btn_row = tk.Frame(win, bg=C_BG_DEEP)
        btn_row.pack(pady=8)
        tk.Button(btn_row, text="Exportar TXT",
                  command=self._export_favourites,
                  bg=C_BLUE, fg=C_WHITE, font=F_BTN_MAIN,
                  relief="flat", cursor="hand2",
                  padx=16, pady=8).pack(side="left", padx=8)
        tk.Button(btn_row, text="Cerrar", command=win.destroy,
                  bg=C_PANEL_SEC, fg=C_WHITE, font=F_BTN_MAIN,
                  relief="flat", cursor="hand2",
                  padx=16, pady=8).pack(side="left", padx=8)

  # Selección de tema

    def _select_topic(self, topic: str) -> None:
        self._audio.stop()
        self._topic_var.set(topic)
        for t, btn in self._topic_btns.items():
            btn.config(
                fg=C_WHITE    if t == topic else C_GREY_SEC,
                bg=C_PANEL    if t == topic else C_BG_DEEP)
        self.avatar.change_topic(topic)
        self.root.after(200, self._fetch_and_summarise)

  # Búsqueda de noticias + flujo de IA

    def _fetch_and_summarise(self) -> None:
        """Obtiene un artículo aleatorio del tema y arranca el flujo."""
        if not self._news_key:
            self._set_status("NEWS_API_KEY no configurada", C_RED_ERR)
            self.avatar.set_pose("error")
            self._btn_voice.config(state="normal")
            self._btn_stop.config(state="disabled", fg=C_GREY_SEC)
            return
        if not self._ai:
            self._set_status("OPENAI_API_KEY no configurada", C_RED_ERR)
            self.avatar.set_pose("error")
            self._btn_voice.config(state="normal")
            return

        self.avatar.set_pose("thinking", "Déjame pensar en lo que me comentas...")
        self._set_status("Buscando noticias...", C_PANEL_SEC)
        self._btn_voice.config(state="disabled")
        self._btn_stop.config(state="normal", fg=C_GREY_SEC)
        topic = self._topic_var.get()

        def _worker():
            try:
                import random
                articles = _get_articles_for_topic(
                    self._news_key, topic, page_size=20)
                if not articles:
                    raise Exception("Sin artículos para este tema")

                art         = random.choice(articles)
                title       = art.get("title", "").strip()
                description = art.get("description", "").strip()
                content     = art.get("content", "").strip()
                source      = art.get("source", {}).get("name", "")

                description = re.sub(r"\[\+\d+ chars?\].*$", "", description).strip()
                content     = re.sub(r"\[\+\d+ chars?\].*$", "", content).strip()
                body        = content if len(content) > len(description) else description
                if not body:
                    body = title

                news_text = (
                    f"TÍTULO: {title}\n\n"
                    f"DESCRIPCIÓN: {body}\n\n"
                    f"Fuente: {source}"
                )
                self._ui(self._set_status, "Analizando con IA...", C_PANEL_SEC)
                self._run_ai_pipeline(news_text)

            except Exception as exc:
                msg = str(exc)
                self._ui(self._set_status, f"{msg}", C_RED_ERR)
                bubble = (
                    "Límite de NewsAPI alcanzado. Vuelve en unos minutos."
                    if any(k in msg.lower() for k in ("límite", "rate", "limited"))
                    else f"Error al buscar noticias: {msg[:60]}"
                )
                self._ui(self.avatar.set_pose, "error", bubble)
                self._ui(lambda: self._btn_voice.config(state="normal"))
                self._ui(lambda: self._btn_stop.config(state="disabled", fg=C_GREY_SEC))

        threading.Thread(target=_worker, daemon=True).start()

    def _run_ai_pipeline(self, news_text: str) -> None:
        """
        Ejecuta el flujo completo de IA para *news_text*:
        resumir → analizar → sugerir pregunta → puntuar impacto → TTS.
        """
        try:
            self._ui(self.avatar.set_pose, "thinking")
            self._ui(self._set_status, "Preparando la noticia...", C_PANEL_SEC)
            if not self._ai:
                raise Exception("OPENAI_API_KEY no configurada")

            summary  = self._ai.summarise(news_text)
            topic    = self._topic_var.get()
            analysis = self._ai.analyse(summary)
            question = self._ai.suggest_question(summary)
            impact   = self._ai.score_impact(summary)

            full_text = (
                f"{summary}\n\n"
                f"Análisis: {analysis}\n\n"
                f"Pregunta sugerida: {question}"
            )

  # Guardamos contexto de sesión para preguntas posteriores.
            self._session_memory.append({"role": "assistant", "content": full_text})
            if len(self._session_memory) > 10:
                self._session_memory = self._session_memory[-10:]

  # Sumamos tendencia del tema actual.
            if topic in self._trends:
                self._trends[topic] += 1
                self._ui(self._redraw_trends)

            self._ui(self._set_summary, full_text)
            self._ui(self._set_impact,  impact)
            self._ui(self._add_to_history, full_text, topic)
            self._ui(self._set_status, "Leyendo la noticia...", C_PANEL_SEC)

            bubble = (summary[:90].rsplit(" ", 1)[0] + "…"
                      if len(summary) > 90 else summary)
            self._ui(self.avatar.set_pose, "speaking", bubble)

            self._audio.speak(_clean_for_tts(full_text))
            self._ui(self.avatar.set_pose, "happy")
            self._ui(self._set_status, "¡Completado!", C_STATUS_OK)

        except Exception as exc:
            msg = str(exc)
            self._ui(self._set_status, f"{msg}", C_RED_ERR)
            if any(k in msg.lower() for k in ("límite", "rate", "limited")):
                bubble = "Se ha alcanzado el límite de NewsAPI. Vuelve en unos minutos."
            elif "api" in msg.lower() and "key" in msg.lower():
                bubble = "Comprueba tu clave de NewsAPI en variables de entorno."
            elif "openai" in msg.lower():
                bubble = "Error con OpenAI. Comprueba tu clave."
            else:
                bubble = f"Ha ocurrido un error: {msg[:60]}"
            self._ui(self.avatar.set_pose, "error", bubble)
        finally:
            self._ui(lambda: self._btn_voice.config(state="normal"))
            self._ui(lambda: self._btn_stop.config(state="disabled", fg=C_GREY_SEC))

  # VOZ

    _VOICE_TOPIC_MAP = {
        "fútbol":    "Deporte",   "futbol":    "Deporte",
        "deporte":   "Deporte",   "baloncesto":"Deporte",
        "economía":  "Economía",  "economia":  "Economía",
        "bolsa":     "Economía",  "mercados":  "Economía",
        "política":  "Política", "politica":  "Política",
        "gobierno":  "Política", "elecciones":"Política",
        "sociedad":  "Sociedad",  "educación": "Sociedad",
        "educacion": "Sociedad",  "sanidad":   "Sociedad",
        "arte":      "Arte",      "cine":      "Arte",
        "música":    "Arte",      "musica":    "Arte",
    }

    def _voice_mode(self) -> None:
        self._ui(self._set_status,
                 "Escuchando... di 'fútbol', 'economía', etc.", C_BLUE)
        self._ui(self.avatar.set_pose, "speaking")
        self._ui(lambda: self._btn_voice.config(state="disabled"))
        self._ui(lambda: self._btn_stop.config(state="normal", fg=C_GREY_SEC))

        def _worker():
            command = self._voice.listen()
            if not command:
                self._ui(self._set_status,
                         "No entendí. Di 'fútbol', 'noticias', etc.", C_RED_ERR)
                self._ui(self.avatar.set_pose, "error")
                self._ui(lambda: self._btn_voice.config(state="normal"))
                self._ui(lambda: self._btn_stop.config(state="disabled"))
                return

            topic = next(
                (v for k, v in self._VOICE_TOPIC_MAP.items() if k in command),
                None)
            if not topic:
                self._ui(self._set_status,
                         "Usa: fútbol, economía, política, etc.", C_RED_ERR)
                self._ui(self.avatar.set_pose, "normal")
                self._ui(lambda: self._btn_voice.config(state="normal"))
                self._ui(lambda: self._btn_stop.config(state="disabled"))
                return

            self.root.after(0, self._select_topic, topic)
            self._ui(self._set_status,
                     f"Tema: {topic}. Buscando...", C_STATUS_OK)
            self._ui(self._fetch_and_summarise)

        threading.Thread(target=_worker, daemon=True).start()

    def _stop(self) -> None:
        self._audio.stop()
        self._ui(self.avatar.set_pose, "normal", "¿Qué te interesa saber ahora?")
        self._ui(self._set_status, "⏹ Parado", C_GREY_SEC)
        self._ui(lambda: self._btn_stop.config(state="disabled",  fg=C_GREY_SEC))
        self._ui(lambda: self._btn_voice.config(state="normal"))

  # Resumen diario

    def _daily_briefing(self) -> None:
        if not self._news_key or not self._ai:
            self._ui(self._set_status, "Faltan claves API", C_RED_ERR)
            return
        self._ui(self._set_status, "Preparando resumen del día...", C_BLUE)
        self._ui(self.avatar.set_pose, "thinking",
                 "Preparando el resumen del día...")
        self._ui(lambda: self._btn_voice.config(state="disabled"))
        self._ui(lambda: self._btn_stop.config(state="normal", fg=C_GREY_SEC))

        def _worker():
            try:
                news_items = []
                for topic, _ in TOPICS.items():
                    try:
                        arts = _get_articles_for_topic(
                            self._news_key, topic, page_size=5)
                        if arts:
                            art   = arts[0]
                            title = art.get("title", "").strip()
                            desc  = art.get("description", "").strip()
                            if title:
                                news_items.append(f"[{topic}]: {title}. {desc}")
                    except Exception:
                        continue

                if not news_items:
                    self._ui(self._set_status,
                             "Sin noticias disponibles", C_GREY_SEC)
                    return

                prompt = (
                    "Eres Adela, presentadora de informativos españoles. "
                    "Vas a hacer el resumen informativo del día. "
                    "Resume en 5 frases fluidas y naturales, una por tema, "
                    "como si estuvieras en directo. Sin títulos ni listas:\n\n"
                    + "\n".join(news_items)
                )
                briefing = self._ai.summarise(prompt)
                self._ui(self._set_summary, briefing)
                self._ui(self._add_to_history, briefing, "Resumen día")
                self._session_memory.append({"role": "assistant", "content": briefing})

                bubble = (briefing[:90].rsplit(" ", 1)[0] + "…"
                          if len(briefing) > 90 else briefing)
                self._ui(self.avatar.set_pose, "speaking", bubble)
                self._ui(self._set_status, "Leyendo resumen del día...", C_PANEL_SEC)
                self._audio.speak(_clean_for_tts(briefing))
                self._ui(self.avatar.set_pose, "happy")
                self._ui(self._set_status, "Resumen del día completado", C_STATUS_OK)

            except Exception as exc:
                self._ui(self._set_status, f"Error briefing: {exc}", C_RED_ERR)
                self._ui(self.avatar.set_pose, "error")
            finally:
                self._ui(lambda: self._btn_voice.config(state="normal"))
                self._ui(lambda: self._btn_stop.config(state="disabled", fg=C_GREY_SEC))

        threading.Thread(target=_worker, daemon=True).start()

  # Análisis diario (resumen multitema)

    def _daily_analysis(self) -> None:
        try:
            if not self._news_key:
                self._ui(self._set_status,
                         "NEWS_API_KEY no configurada", C_RED_ERR)
                return
            if not self._ai:
                self._ui(self._set_status,
                         "OPENAI_API_KEY no configurada", C_RED_ERR)
                return

            self._ui(self.avatar.set_pose, "thinking",
                     "Recopilando lo más importante del día...")
            news_items = []
            for topic, _ in TOPICS.items():
                try:
                    arts = _get_articles_for_topic(
                        self._news_key, topic, page_size=5)
                    if arts:
                        art   = arts[0]
                        title = art.get("title", "").strip()
                        desc  = art.get("description", "").strip()
                        if title:
                            news_items.append(f"[{topic}] {title}: {desc}")
                except Exception:
                    continue

            if not news_items:
                self._ui(self._set_status,
                         "Sin noticias disponibles hoy", C_GREY_SEC)
                self._ui(self.avatar.set_pose, "normal")
                return

            prompt = (
                "Eres presentadora de informativos española. "
                "Haz un RESUMEN DIARIO en 4 frases fluidas de lo más importante "
                "de estas noticias, cubriendo los distintos temas:\n\n"
                + "\n\n".join(news_items)
            )
            self._ui(self._set_status, "Generando resumen del día...", C_PANEL_SEC)
            daily = self._ai.summarise(prompt)
            self._ui(self._set_summary, daily)
            self._ui(self._add_to_history, daily, "Análisis Diario")
            self._session_memory.append({"role": "assistant", "content": daily})

            bubble = (daily[:90].rsplit(" ", 1)[0] + "…"
                      if len(daily) > 90 else daily)
            self._ui(self.avatar.set_pose, "speaking", bubble)
            self._ui(self._set_status, "Leyendo el resumen del día...", C_PANEL_SEC)
            self._ui(lambda: self._btn_voice.config(state="disabled"))
            self._ui(lambda: self._btn_stop.config(state="normal", fg=C_GREY_SEC))
            self._audio.speak(_clean_for_tts(daily))
            self._ui(self.avatar.set_pose, "happy")
            self._ui(self._set_status, "Análisis diario completado", C_STATUS_OK)

        except Exception as exc:
            self._ui(self._set_status, f"Error análisis diario: {exc}", C_RED_ERR)
            self._ui(self.avatar.set_pose, "error")
        finally:
            self._ui(lambda: self._btn_voice.config(state="normal"))
            self._ui(lambda: self._btn_stop.config(state="disabled", fg=C_GREY_SEC))

  # Modo debate

    def _debate_mode(self) -> None:
        if not self._ai:
            self._ui(self._set_status, "OpenAI no configurada", C_RED_ERR)
            return
        current_text = self._lbl_summary.cget("text")
        if not current_text or current_text.startswith("Inicia una"):
            messagebox.showinfo("Debate",
                                "Primero carga una noticia para debatir.")
            return

        headline = current_text.split("Análisis:")[0].strip()[:200]

        self._ui(self._set_status, "⚖️ Generando debate...", C_BLUE)
        self._ui(self.avatar.set_pose, "debate")
        self._ui(lambda: self._btn_voice.config(state="disabled"))
        self._ui(lambda: self._btn_stop.config(state="normal", fg=C_GREY_SEC))

        def _worker():
            try:
                a, b = self._ai.generate_debate(headline)
                debate_text = (
                    f"⚖️ DOS PERSPECTIVAS\n\n"
                    f"Perspectiva A:\n{a}\n\n"
                    f"Perspectiva B:\n{b}"
                )
                self._ui(self._set_summary, debate_text)
                self._ui(self._add_to_history, debate_text, "Debate")
                self._session_memory.append(
                    {"role": "assistant", "content": debate_text})

                bubble_a = a[:70] + "…" if len(a) > 70 else a
                self._ui(self.avatar.set_pose, "debate", f"{bubble_a}")
                self._ui(self._set_status,
                         "Leyendo primera perspectiva...", C_PANEL_SEC)
                self._audio.speak(_clean_for_tts(f"Primera perspectiva. {a}"))

                if not self._audio._stop_event.is_set():
                    time.sleep(0.8)
                    bubble_b = b[:70] + "…" if len(b) > 70 else b
                    self._ui(self.avatar.set_pose, "debate", f"{bubble_b}")
                    self._ui(self._set_status,
                             "Leyendo segunda perspectiva...", C_PANEL_SEC)
                    self._audio.speak(_clean_for_tts(f"Segunda perspectiva. {b}"))

                self._ui(self.avatar.set_pose, "happy")
                self._ui(self._set_status, "Debate completado", C_STATUS_OK)

            except Exception as exc:
                self._ui(self._set_status, f"Error debate: {exc}", C_RED_ERR)
                self._ui(self.avatar.set_pose, "error")
            finally:
                self._ui(lambda: self._btn_voice.config(state="normal"))
                self._ui(lambda: self._btn_stop.config(state="disabled", fg=C_GREY_SEC))

        threading.Thread(target=_worker, daemon=True).start()

  # Pregunta a Adela (preguntas con memoria de sesión)

    def _ask_adela(self) -> None:
        if not self._ai:
            self._ui(self._set_status, "OpenAI no configurada", C_RED_ERR)
            return
        if not self._session_memory:
            messagebox.showinfo(
                "Sin contexto",
                "Primero carga alguna noticia para que Adela tenga contexto.")
            return

        win = tk.Toplevel(self.root)
        win.title("Pregunta a Adela")
        win.geometry("480x200")
        win.configure(bg=C_BG_DEEP)
        win.grab_set()

        tk.Label(win, text="¿Qué quieres preguntarle a Adela?",
                 bg=C_BG_DEEP, fg=C_WHITE, font=F_BTN_MAIN).pack(pady=(20, 8))
        entry = tk.Entry(win, bg=C_PANEL, fg=C_WHITE, font=F_BODY,
                         insertbackground=C_WHITE, relief="flat", width=50)
        entry.pack(padx=20, ipady=8)
        entry.focus_set()

        def _send(event=None):
            question = entry.get().strip()
            if not question:
                return
            win.destroy()
            self._ui(self._set_status, "Adela está pensando...", C_BLUE)
            self._ui(self.avatar.set_pose, "thinking")

            def _worker():
                try:
                    answer = self._ai.reply_with_context(
                        question, self._session_memory)
                    self._session_memory.append(
                        {"role": "user",      "content": question})
                    self._session_memory.append(
                        {"role": "assistant", "content": answer})
                    if len(self._session_memory) > 10:
                        self._session_memory = self._session_memory[-10:]

                    self._ui(self._set_summary, f"Pregunta: {question}\n\nRespuesta: {answer}")
                    bubble = (answer[:90].rsplit(" ", 1)[0] + "…"
                              if len(answer) > 90 else answer)
                    self._ui(self.avatar.set_pose, "speaking", bubble)
                    self._ui(self._set_status, "Respondiendo...", C_PANEL_SEC)
                    self._audio.speak(_clean_for_tts(answer))
                    self._ui(self.avatar.set_pose, "happy")
                    self._ui(self._set_status, "Respuesta completada", C_STATUS_OK)

                except Exception as exc:
                    self._ui(self._set_status, f"Error: {exc}", C_RED_ERR)
                    self._ui(self.avatar.set_pose, "error")
                finally:
                    self._ui(lambda: self._btn_voice.config(state="normal"))
                    self._ui(lambda: self._btn_stop.config(state="disabled", fg=C_GREY_SEC))

            self._ui(lambda: self._btn_voice.config(state="disabled"))
            self._ui(lambda: self._btn_stop.config(state="normal", fg=C_GREY_SEC))
            threading.Thread(target=_worker, daemon=True).start()

        entry.bind("<Return>", _send)
        tk.Button(win, text="Preguntar", command=_send,
                  bg=C_BLUE, fg=C_WHITE, font=F_BTN_MAIN,
                  relief="flat", cursor="hand2",
                  pady=8, padx=20).pack(pady=14)

  # Menú lateral

    def _handle_menu(self, label: str) -> None:
        actions = {
            "Inicio":          self._go_home,
            "Noticias de hoy": lambda: self._select_topic("Economía"),
            "Breaking News":   self._fetch_and_summarise,
            "Análisis Diario": lambda: threading.Thread(
                target=self._daily_analysis, daemon=True).start(),
            "Tendencias":      self._show_trends,
            "Guardadas":       self._show_favourites_window,
            "Ajustes":         self._show_settings,
        }
        action = actions.get(label)
        if action:
            action()

    def _go_home(self) -> None:
        self._ui(self._set_status, "Inicio · Adela a tu servicio", C_STATUS_OK)
        self._ui(self.avatar.set_pose, "normal")

    def _show_trends(self) -> None:
        self._ui(self._redraw_trends)
        self._ui(self._set_status, "Tendencias de la sesión", C_STATUS_OK)

    def _show_settings(self) -> None:
        messagebox.showinfo(
            "Ajustes",
            "Variables de entorno necesarias:\n\n"
            "OPENAI_API_KEY=sk-...\n"
            "NEWS_API_KEY=tu-clave\n\n"
            "Establécelas y reinicia la app.")


  # Punto de entrada

if __name__ == "__main__":
    root = tk.Tk()
    AdelaBot(root)
    root.mainloop()
