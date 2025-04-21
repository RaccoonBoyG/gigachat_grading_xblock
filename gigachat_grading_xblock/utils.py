"""
xblock helpers.
"""
import os
import json
import logging
import pkg_resources

from html.parser import HTMLParser
from django.template import Context, Template

from gigachat import GigaChat


html_parser = HTMLParser()  # pylint: disable=invalid-name
log = logging.getLogger(__name__)

def load_resource(resource_path):  # pragma: NO COVER
    """
    Gets the content of a resource
    """
    resource_content = pkg_resources.resource_string(__name__, resource_path)
    return str(resource_content.decode("utf8"))

def render_template(template_path, context=None):  # pragma: NO COVER
    """
    Evaluate a template by resource path, applying the provided context.
    """
    if context is None:
        context = {}

    template_str = load_resource(template_path)
    template = Template(template_str)
    return template.render(Context(context))

def upload_pdf_to_gigachat(auth_key: str, file_path: str, prompt: str) -> dict:
    """
    Загружает PDF или DOCX-файл в GigaChat, запускает чат с прикреплённым файлом и возвращает
    распарсенный JSON-результат с ключами 'score' и 'comment'.
    """
    # 1. Инициализируем клиент GigaChat
    client = GigaChat(
        credentials=auth_key,
        verify_ssl_certs=False,
        scope="GIGACHAT_API_PERS",
        model="GigaChat"
    )

    # 2. Открываем файл в бинарном режиме — SDK сам проставит нужный MIME‑тип
    with open(file_path, "rb") as f:
        file = client.upload_file(f)  # возвращает объект с атрибутом .id :contentReference[oaicite:2]{index=2}
    log.warning(file)

    # 3. Формируем запрос к chat с вложением
    request_payload = {
        "model": "GigaChat",
        "messages": [
            {
                "role": "assistant",
                "content": prompt,
                "attachments": [file.id_],
            }
        ],
        "temperature": 0.7
    }

    # 4. Отправляем запрос и получаем ответ
    response = client.chat(request_payload)
    raw_content = response.choices[0].message.content

    # 5. Пытаемся распарсить JSON из текста ответа
    log.warning(raw_content)
    log.warning("raw_content !!!!!!!!!!!!!")
    try:
        result = json.loads(raw_content)
    except ValueError:
        # Если не удалось распарсить — возвращаем стандартную ошибочную структуру
        result = {
            "score": 0,
            "comment": "Invalid response format from GigaChat"
        }

    return result