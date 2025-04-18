"""
Пример XBlock, использующего API OpenAI для автоматизированной проверки работ.
Функциональные возможности:
- Загрузка файла (PDF или DOCX) студентом.
- Извлечение текста из загруженного файла.
- Отправка текста вместе с тематическим промтом для получения оценки через API OpenAI.
- Отображение результата в виде JSON с ключами "score" и "comment".
- Возможность для преподавателя изменить оценку и комментарий в режиме Studio.
"""

import json
import tempfile
import os
import logging

from gigachat import GigaChat # требуется установить библиотеку: pip install openai

# Для чтения PDF и DOCX используются библиотеки, их установка:
# pip install PyPDF2 python-docx

import PyPDF2
import docx

from xblock.core import XBlock
from xblock.fields import Scope, String, Float, Dict
from django.conf import settings
from web_fragments.fragment import Fragment
from gigachat_grading_xblock.utils import render_template
from xblockutils.studio_editable import StudioEditableXBlockMixin

log = logging.getLogger(__name__)


class GigaChatAIGradingXBlock(StudioEditableXBlockMixin, XBlock):
    editable_fields = ('overridden_score', 'overridden_comment')
    """
    XBlock для проверки работ с помощью OpenAI API.
    """

    # Настраиваемые поля XBlock
    # Поле для хранения темы проверки (промта)
    grading_prompt = String(
        help="Промт с критериями проверки работы", 
        default="""Требуется провести подробную оценку реферата по истории России. Обрати внимание на следующие аспекты:
1. **Полнота раскрытия темы:** Насколько в реферате охвачены основные события, периоды и личности, связанные с историей России.
2. **Аргументация и анализ:** Насколько аргументированно изложены исторические факты, использованы ли анализ и сравнение источников.
3. **Структура и логика изложения:** Является ли реферат логически построенным, соблюдена ли хронология изложения.
4. **Достоверность информации:** Проверка фактической точности указанных данных и их соответствие проверенным историческим источникам.
5. **Стиль изложения и грамотность:** Оценка языка, стиля, соблюдение орфографических и пунктуационных норм.

После анализа выдай результат в виде JSON-объекта с двумя ключами:
- **score:** число от 0 до 1, где 0 означает крайне низкое качество, а 1 — превосходное качество.
- **comment:** развернутое обоснование выставленной оценки, где подробно описаны сильные и слабые стороны работы, а также рекомендации по улучшению.
""",
        scope=Scope.settings,
        display_name="Промт проверки"
    )

    # Поля для записи результатов (изначально пустые, могут быть изменены преподавателем)
    result = Dict(
        help="Результат автоматической проверки в виде словаря {'score': число, 'comment': текст}",
        default={},
        scope=Scope.user_state
    )

    # Возможность для преподавателя вручную изменить оценку
    overridden_score = Float(
        help="Оценка, установленная преподавателем",
        default=None,
        scope=Scope.content
    )
    overridden_comment = String(
        help="Комментарий, установленный преподавателем",
        default="",
        scope=Scope.content
    )
    
    def student_view(self, context=None):
        html = self.resource_string("static/html/student-view.html")
        frag = Fragment(html.format(self=self))
        frag.add_css(self.resource_string("static/css/student-view.css"))
        frag.add_javascript(self.resource_string("static/js/src/gigachat_grading.js"))
        frag.initialize_js('GigaChatGradingXBlock')
        return frag

    # def student_view(self, context=None):
    #     """
    #     Основной интерфейс для студента: форма загрузки файла.
    #     """
    #     html = self.resource_string("static/html/openai_grading.html")
    #     fragment = Fragment(html)
    #     fragment.add_javascript(self.resource_string("static/js/src/gigachat_grading.js"))
    #     fragment.initialize_js("GigaChatGradingXBlock")
    #     fragment.add_css("""
    #         div { font-family: Arial, sans-serif; }
    #         pre { background: #f8f8f8; padding: 10px; border: 1px solid #ccc; }
    #     """)
    #     return fragment

    # def studio_view(self, context=None):
    #     """
    #     Редактор для преподавателя, в котором можно задать промт и установить/изменить оценку.
    #     """
    #     context = {
    #         "grading_prompt": self.grading_prompt,
    #         "overridden_score": self.overridden_score if self.overridden_score is not None else "",
    #         "overridden_comment": self.overridden_comment
    #     }
    #     html = render_template("studio-view.html", **context)

    #     # Форматируем шаблон, подставляя текущие значения
    #     fragment = Fragment(html)
        # fragment.add_javascript(self.resource_string("static/js/src/gigachat_grading.js"))
        # fragment.initialize_js("GigaChatGradingXBlock")
    #     return fragment

    def extract_text_from_file(self, file_path, file_extension):
        """
        Функция извлекает текст из файла по типу.
        """
        text = ""
        try:
            if file_extension.lower() == '.pdf':
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
            elif file_extension.lower() == '.docx':
                doc = docx.Document(file_path)
                for para in doc.paragraphs:
                    text += para.text + "\n"
            else:
                text = ""
        except Exception as e:
            log.error("Ошибка при извлечении текста: %s", e)
        return text

    def call_giga_chat_api(self, text, prompt):
        """
        Отправка текста с дополнительным промтом в GigaChat API для получения оценки.
        """
        GIGACHAT_AUTH_KEY = getattr(settings,'GIGACHAT_AUTH_KEY', "")
        auth_key = GIGACHAT_AUTH_KEY
        client = GigaChat(credentials=auth_key,verify_ssl_certs=False, scope="GIGACHAT_API_PERS", model="GigaChat-Lite")

        # Соединение промта и текста работы
        full_prompt = prompt + "\n\nТекст работы:\n" + text
        
        try:
            response = client.chat(
                messages=[
                    {"role": "system", "content": "Вы — помощник для оценки учебных работ."},
                    {"role": "user", "content": full_prompt}
                ]
            )
            
            # Ответ модели хранится в content
            reply = response.content.strip()
            
            # Попытка парсинга ответа как JSON
            result_obj = json.loads(reply)
            return result_obj
        except Exception as e:
            log.error("Ошибка при вызове GigaChat API: %s", e)
            return {"score": 0, "comment": "Ошибка при обработке работы: " + str(e)}
        
    @XBlock.json_handler
    def handle_upload(self, data, suffix=""):
        """
        Обработчик загрузки файла от студента.
        Извлекает текст из файла, вызывает OpenAI API и сохраняет/отправляет результат.
        """
        # Получаем загруженный файл через self.request.params (метод зависит от настройки среды)
        uploaded_file = self.request.params.get("uploaded_file")
        if uploaded_file is None:
            return {"error": "Файл не найден"}

        # Определяем расширение файла
        filename = uploaded_file.filename
        _, ext = os.path.splitext(filename)
        ext = ext.lower()
        if ext not in ['.pdf', '.docx']:
            return {"error": "Поддерживаются только файлы PDF и DOCX."}

        # Сохраняем временную копию загруженного файла
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(uploaded_file.file.read())

        # Извлекаем текст из файла
        extracted_text = self.extract_text_from_file(file_path, ext)
        if not extracted_text.strip():
            return {"error": "Не удалось извлечь текст из файла."}

        # Если у преподавателя установлены переопределённые оценка и комментарий – отдаём их
        if self.overridden_score is not None:
            final_result = {"score": self.overridden_score, "comment": self.overridden_comment}
        else:
            # Вызываем API для оценки работы
            final_result = self.call_giga_chat_api(extracted_text, self.grading_prompt)
        
        # Сохраняем результат в состоянии пользователя
        self.result = final_result

        return json.dumps(final_result)

    @XBlock.json_handler
    def studio_submit(self, data, suffix=""):
        """
        Обработчик сохранения настроек в Studio.
        Позволяет задать новый промт и переопределённые оценку/комментарий.
        """
        try:
            self.grading_prompt = data.get("grading_prompt", self.grading_prompt)
            score = data.get("overridden_score")
            if score != "":
                self.overridden_score = float(score)
            else:
                self.overridden_score = None
            self.overridden_comment = data.get("overridden_comment", self.overridden_comment)
            return {"result": "success"}
        except Exception as e:
            log.error("Ошибка при сохранении настроек Studio: %s", e)
            return {"error": str(e)}

    # Функция для отладки, вызываемая при просмотре состояния XBlock
    def resource_string(self, path):
        import pkg_resources
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")
    
    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            (
                "GigaChatAIGradingXBlock",
                """
                <GigaChat/>
                """,
            ),
            (
                "Multiple GigaChatAIGradingXBlock",
                """<vertical_demo>
                    <GigaChat/>
                    <GigaChat/>
                    <GigaChat/>
                </vertical_demo>
             """,
            ),
        ]
# def _test_xblock():
#     """
#     Функция для тестирования XBlock вне платформы edX.
#     """
#     from xblock.test.tools import TestRuntime
#     runtime = TestRuntime(services={'i18n': lambda x: x})
#     block = GigaChatAIGradingXBlock(runtime, None)
#     print("XBlock создан, тестовые данные:")
#     print("Промт проверки:\n", block.grading_prompt)
#     # Здесь можно эмулировать вызов обработчика загрузки файла и других методов.

# if __name__ == "__main__":
#     _test_xblock()
