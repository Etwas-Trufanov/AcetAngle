"""
AcetAngle Backend API
=====================
FastAPI-сервис для аутентификации пользователей и проксирования сообщений
к внешнему AI-сервису с сохранением истории чатов в MongoDB.

Запуск: uvicorn server:app --reload --port 8000
"""

import hashlib
import json
import os
import secrets
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient

load_dotenv()

# --- Конфигурация из переменных окружения ---
AI_URL = os.getenv("AI_URL")  # URL внешнего AI-сервиса
AI_API_KEY = os.getenv("AI_API_KEY")  # API-ключ для AI-сервиса
MONGO_DB_URL = os.getenv("MONGO_DB")  # URI подключения к MongoDB

app = FastAPI(title="AcetAngle API")

# --- MongoDB ---
client = MongoClient(MONGO_DB_URL)
db = client["acetAngle"]
users_col = db["users"]
tokens_col = db["tokens"]


# ---------------------------------------------------------------------------
# Модели запросов
# ---------------------------------------------------------------------------


class AuthRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str
    surname: str
    isDoctor: bool = False


class SendMessageRequest(BaseModel):
    message_text: str
    chat_id: str
    call_type: int = 0
    filename: Optional[str] = None
    image: Optional[str] = None


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------


@app.post("/register")
def register(request: RegisterRequest):
    if users_col.find_one({"username": request.username}):
        raise HTTPException(status_code=409, detail="Username already taken")

    hashed_password = hashlib.sha256(request.password.encode()).hexdigest()
    new_user = {
        "username": request.username,
        "password_hash": hashed_password,
        "name": request.name,
        "surname": request.surname,
        "isDoctor": request.isDoctor,
        "chats": {},
    }
    users_col.insert_one(new_user)

    token = secrets.token_hex(32)
    tokens_col.insert_one({"token": token, "username": request.username})

    return {
        "token": token,
        "name": request.name,
        "surname": request.surname,
        "isDoctor": request.isDoctor,
    }


@app.post("/auth")
def auth(request: AuthRequest):
    user = users_col.find_one({"username": request.username})
    if user:
        hashed_input = hashlib.sha256(request.password.encode()).hexdigest()
        if hashed_input == user["password_hash"]:
            token = secrets.token_hex(32)
            tokens_col.insert_one({"token": token, "username": request.username})
            return {
                "token": token,
                "name": user["name"],
                "surname": user["surname"],
                "isDoctor": user["isDoctor"],
            }
    raise HTTPException(status_code=401, detail="Invalid username or password")


@app.get("/update")
def update(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = authorization.split(" ")[1]
    token_doc = tokens_col.find_one({"token": token})
    if not token_doc:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = users_col.find_one({"username": token_doc["username"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "name": user["name"],
        "surname": user["surname"],
        "isDoctor": user["isDoctor"],
        "chats": user.get("chats", {}),
    }


@app.post("/message")
def send_message(
    request: SendMessageRequest, authorization: Optional[str] = Header(None)
):
    """
    Отправка сообщения в чат с AI-сервисом.

    Для call_type=0 возвращает структурированные данные анализа
    (landmarks, lines, angles, диагноз) в поле ``analysis_data``.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = authorization.split(" ")[1]
    token_doc = tokens_col.find_one({"token": token})
    if not token_doc:
        raise HTTPException(status_code=401, detail="Invalid token")

    username = token_doc["username"]
    user = users_col.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    chats = user.get("chats", {})
    chat_history = chats.get(request.chat_id, "")

    ai_payload = {
        "api_key": AI_API_KEY,
        "request_id": request.chat_id,
        "call_type": str(request.call_type),
        "question": request.message_text,
        "context": chat_history,
        "filename": request.filename,
        "image": request.image,
    }

    print(f"[AI] URL: {AI_URL}")
    print(f"[AI] call_type={request.call_type}  chat_id={request.chat_id}")

    try:
        ai_response = requests.post(AI_URL, json=ai_payload, timeout=300)
        print(f"[AI] Status: {ai_response.status_code}")
        print(f"[AI] Response (start): {ai_response.text[:500]}")
        ai_response.raise_for_status()
        ai_data = ai_response.json()
    except requests.RequestException as e:
        print(f"[AI] Exception: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

    ai_answer = ai_data.get("answer", "")

    # ---- Различаем структурированный и текстовый ответ ----
    analysis_data = None

    if isinstance(ai_answer, dict):
        # Структурированный ответ (call_type 0)
        analysis_data = ai_answer
        ai_answer_text = ai_answer.get(
            "description", json.dumps(ai_answer, ensure_ascii=False)
        )
    else:
        ai_answer_text = str(ai_answer)

    # Обновляем историю чата
    new_entry = f"User: {request.message_text}\nAssistant: {ai_answer_text}\n\n"
    updated_history = chat_history + new_entry
    users_col.update_one(
        {"username": username},
        {"$set": {f"chats.{request.chat_id}": updated_history}},
    )

    response = {
        "status": "ok",
        "message_text": ai_answer_text,
        "chat_id": request.chat_id,
    }
    if analysis_data is not None:
        response["analysis_data"] = analysis_data

    return response
