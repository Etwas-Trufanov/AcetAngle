"""
AcetAuth — асинхронный клиент для AcetAngle API
"""

import socket
from os import environ
from typing import Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv()

SERVER_URL = environ.get("SERVER_URL", "")


class AcetAuth:
    def __init__(self) -> None:
        self.token: str = ""
        self.name: str = ""
        self.surname: str = ""
        self.isDoctor: bool = False
        self.isAdmin: bool = False

    # ------------------------------------------------------------------
    # Хелпер: создать сессию с принудительным IPv4
    # ------------------------------------------------------------------

    def _make_session(self) -> aiohttp.ClientSession:
        """
        Возвращает ClientSession с коннектором, привязанным к AF_INET.
        Это исключает попытки подключения через IPv6 (::1),
        которые зависают, если сервер слушает только на 127.0.0.1.
        """
        connector = aiohttp.TCPConnector(family=socket.AF_INET)
        return aiohttp.ClientSession(connector=connector)

    # ------------------------------------------------------------------
    # Аутентификация
    # ------------------------------------------------------------------

    async def register(
        self,
        username: str,
        password: str,
        name: str,
        surname: str,
        is_doctor: bool = False,
    ) -> None:
        url = f"{SERVER_URL}/register"
        payload = {
            "username": username,
            "password": password,
            "name": name,
            "surname": surname,
            "isDoctor": is_doctor,
        }
        try:
            async with self._make_session() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._apply_profile(data)
                    elif response.status == 409:
                        raise Exception("Register error: username already taken")
                    else:
                        raise Exception(f"Register error: {response.status}")
        except aiohttp.ClientError as e:
            raise Exception(f"Register error: {e}")

    async def auth_by_password(self, username: str, password: str) -> None:
        url = f"{SERVER_URL}/auth"
        payload = {"username": username, "password": password}
        try:
            async with self._make_session() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._apply_profile(data)
                    else:
                        raise Exception(f"Auth error: {response.status}")
        except aiohttp.ClientError as e:
            raise Exception(f"Auth error: {e}")

    # ------------------------------------------------------------------
    # Работа с профилем и чатами
    # ------------------------------------------------------------------

    async def update_chats(self) -> dict:
        url = f"{SERVER_URL}/update"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with self._make_session() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        raise Exception(f"Update error: {response.status}")
        except aiohttp.ClientError as e:
            raise Exception(f"Update error: {e}")

    # ------------------------------------------------------------------
    # Чат с AI
    # ------------------------------------------------------------------

    async def send_message(
        self,
        message_text: str,
        chat_id: str,
        call_type: int = 0,
        context: str = "",
        filename: Optional[str] = None,
        image: Optional[str] = None,
    ) -> dict:
        url = f"{SERVER_URL}/message"
        payload = {
            "message_text": message_text,
            "chat_id": chat_id,
            "call_type": call_type,
            "context": context,
            "filename": filename,
            "image": image,
        }
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with self._make_session() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=600),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        raise Exception(f"Send message error: {response.status}")
        except aiohttp.ClientError as e:
            raise Exception(f"Send message error: {e}")

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def _apply_profile(self, data: dict) -> None:
        self.token = data.get("token", "")
        self.name = data.get("name", "")
        self.surname = data.get("surname", "")
        self.isDoctor = data.get("isDoctor", False)
        self.isAdmin = data.get("isAdmin", False)

    @property
    def is_authenticated(self) -> bool:
        return bool(self.token)
