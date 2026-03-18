"""
AcetAngle Inference Server
===========================
HTTP-сервер, проксирующий запросы к LMStudio для анализа рентгеновских снимков.

Запуск: python inferenceServer.py
"""

import base64
import io
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from schema_answer import json_schema
from schema_render import render_schema

load_dotenv()
LMSTUDIO_URL = os.getenv("LMSTUDIO_URL")
MODEL_NAME = os.getenv("MODEL_NAME")
EXPECTED_API_KEY = os.getenv("EXPECTED_API_KEY")


# ======================================================================
# Рисование разметки на изображении (для отладки и второго шага)
# ======================================================================


def draw_landmarks_and_lines(image_b64, landmarks, lines, angles):
    """Рисует landmarks / lines / angles на изображении, возвращает base64."""
    image_data = base64.b64decode(image_b64)
    image = Image.open(io.BytesIO(image_data)).convert("RGB")
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20
            )
        except IOError:
            font = ImageFont.load_default()

    # Линии
    for line in lines:
        start = tuple(line["start"])
        end = tuple(line["end"])
        label = line.get("label", "")
        draw.line([start, end], fill="red", width=3)
        mid = ((start[0] + end[0]) // 2, (start[1] + end[1]) // 2)
        draw.text(mid, label, fill="yellow", font=font)

    # Контрольные точки
    for lm in landmarks:
        x, y = lm["x"], lm["y"]
        radius = lm.get("radius", 5)
        label = lm.get("label", "")
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill="blue",
            outline="white",
            width=2,
        )
        draw.text((x + 10, y - 10), label, fill="white", font=font)

    # Углы
    for angle in angles:
        v = tuple(angle["vertex"])
        a1 = tuple(angle["arm1"])
        a2 = tuple(angle["arm2"])
        label = angle.get("label", "")
        draw.line([v, a1], fill="green", width=3)
        draw.line([v, a2], fill="green", width=3)
        draw.text((v[0] + 10, v[1] + 10), label, fill="green", font=font)

    output = io.BytesIO()
    image.save(output, format="JPEG")
    output.seek(0)
    return base64.b64encode(output.read()).decode("utf-8")


# ======================================================================
# Вызов LMStudio
# ======================================================================


def call_lmstudio(messages, schema=None):
    """Отправляет запрос к LMStudio и возвращает JSON-ответ."""
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.7,
        "reasoning_effort": "low",
    }

    if schema:
        payload["response_format"] = {"type": "json_schema", "json_schema": schema}
    else:
        payload["response_format"] = {"type": "text"}

    response = requests.post(LMSTUDIO_URL, json=payload, timeout=180)
    response.raise_for_status()
    return response.json()


# ======================================================================
# HTTP-обработчик
# ======================================================================


class RequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        start_time = time.time()
        print(
            f"[{start_time:.2f}] POST от {self.client_address[0]}:{self.client_address[1]}"
        )

        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length)

        try:
            request_data = json.loads(post_data.decode("utf-8"))

            # Проверка API-ключа
            if EXPECTED_API_KEY and request_data.get("api_key") != EXPECTED_API_KEY:
                self.send_error(403, "Invalid API key")
                return

            request_id = request_data.get("request_id", "unknown")
            call_type = request_data.get("call_type", "0")
            question = request_data.get("question", "")
            filename = request_data.get("filename", "image.jpg")
            image_b64 = request_data.get("image", "")

            if not question:
                raise ValueError("Missing 'question' in request")

            # Единая переменная для тела ответа
            response_body = None

            # ==============================================================
            # call_type '0' — двухшаговый анализ снимка
            # ==============================================================
            if call_type == "0":
                if not image_b64 or filename == "null":
                    raise ValueError(
                        "Для call_type '0' требуется изображение и filename"
                    )

                # ---- Шаг 1: получаем контрольные точки / линии / углы ----
                first_messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": question},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                },
                            },
                        ],
                    }
                ]
                first_response = call_lmstudio(first_messages, schema=render_schema)
                first_answer_text = first_response["choices"][0]["message"]["content"]
                first_answer_json = json.loads(first_answer_text)

                landmarks = first_answer_json.get("landmarks", [])
                lines = first_answer_json.get("lines", [])
                angles = first_answer_json.get("angles", [])

                if not landmarks and not lines:
                    raise ValueError(
                        "Модель не вернула контрольные точки или линии на первом шаге"
                    )

                # ---- Рисуем поверх изображения ----
                new_image_b64 = draw_landmarks_and_lines(
                    image_b64, landmarks, lines, angles
                )

                # ---- Шаг 2: повторный запрос с дорисованным изображением ----
                second_question = (
                    question + " Отвечай на русском языке! На основе отмеченных линий "
                    "определи диагноз, опиши патологию и причины. "
                    "accurate_diagnosis — число от 0 до 1, насколько ты уверена "
                    "в диагнозе. Ответ должен быть на РУССКОМ языке!"
                )
                second_messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": second_question},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{new_image_b64}"
                                },
                            },
                        ],
                    }
                ]
                second_response = call_lmstudio(second_messages, schema=json_schema)
                second_answer_text = second_response["choices"][0]["message"]["content"]
                second_answer_json = json.loads(second_answer_text)

                # Собираем финальный ответ
                final_answer = second_answer_json.copy()
                final_answer["landmarks"] = landmarks
                final_answer["lines"] = lines
                final_answer["angles"] = angles
                final_answer["request_id"] = request_id

                response_body = {
                    "status": "ok",
                    "request_id": request_id,
                    "answer": final_answer,
                }

            # ==============================================================
            # call_type '1' — простой чат-бот (без строгой схемы)
            # ==============================================================
            elif call_type == "1":
                messages = []
                context = request_data.get("context", "")
                if context:
                    messages.append({"role": "assistant", "content": context})

                user_content = [{"type": "text", "text": question}]
                if image_b64 and filename != "null":
                    user_content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        }
                    )
                messages.append({"role": "user", "content": user_content})

                lm_response = call_lmstudio(
                    messages
                )  # <-- ИСПРАВЛЕНО: было use_json_schema=False
                answer_text = lm_response["choices"][0]["message"]["content"]

                response_body = {
                    "status": "ok",
                    "request_id": request_id,
                    "answer": answer_text,
                }

            else:
                raise ValueError(f"Unsupported call_type: {call_type}")

            # ---- Отправляем ответ клиенту ----
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps(response_body, ensure_ascii=False).encode("utf-8")
            )

            total_time = time.time() - start_time
            print(f"[{time.time():.2f}] Ответ отправлен (время: {total_time:.2f}s)")

        except (BrokenPipeError, ConnectionResetError):
            print(f"[{time.time():.2f}] Соединение разорвано клиентом")

        except Exception as e:
            print(f"[{time.time():.2f}] Ошибка: {e}")
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"status": "error", "message": str(e)}, ensure_ascii=False
                    ).encode("utf-8")
                )
            except (BrokenPipeError, ConnectionResetError):
                pass

    def log_message(self, format, *args):  # noqa: A002
        pass


# ======================================================================
# Точка входа
# ======================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("Проверка конфигурации...")
    print(f"LMSTUDIO_URL:    {LMSTUDIO_URL}")
    print(f"MODEL_NAME:      {MODEL_NAME}")
    print(f"EXPECTED_API_KEY: {'установлен' if EXPECTED_API_KEY else 'не установлен'}")

    print("\nПроверка доступности LMStudio...")
    try:
        test_url = LMSTUDIO_URL.replace("/v1/chat/completions", "/v1/models")
        test_response = requests.get(test_url, timeout=5)
        print("✓ LMStudio доступна")
        if test_response.status_code == 200:
            models = test_response.json().get("data", [])
            print(f"✓ Моделей: {len(models)}")
    except requests.exceptions.ConnectionError:
        print(f"✗ Не удалось подключиться к LMStudio на {LMSTUDIO_URL}")
        print("  Убедись, что LMStudio запущена!")
        exit(1)
    except Exception as e:
        print(f"⚠ Предупреждение: {e}")

    print("=" * 50)
    print("Сервер запущен на порту 25555")
    print("=" * 50)

    server = ThreadingHTTPServer(("0.0.0.0", 25555), RequestHandler)
    server.serve_forever()
