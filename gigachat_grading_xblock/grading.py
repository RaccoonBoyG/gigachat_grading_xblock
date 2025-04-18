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
from .utils import upload_pdf_to_gigachat
from webob import Response

log = logging.getLogger(__name__)

@XBlock.needs('user')
class GigaChatAIGradingXBlock(StudioEditableXBlockMixin, XBlock):
    editable_fields = ('display_name', 'grade_weight', 'auth_key')
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
    display_name = String(display_name="Оценивание преподавателем", default="Оценивание преподавателем", scope=Scope.settings)
    submissions = Dict(help="Все ответы студентов", default={}, scope=Scope.settings)
    grade_weight = Float(help="Weight of this component (0-1)", default=1.0, scope=Scope.content)
    auth_key = String(help="Ключ от нейросети", default="", scope=Scope.settings)

    def student_view(self, context=None):
        # проверка по Runtime API
        is_staff = getattr(self.runtime, 'user_is_staff', False)
        # if not is_staff:
            # обычный студент — загрузка файла
        html = self.resource_string("static/html/student-view.html")
        # else:
            # преподаватель — интерфейс проверки
            # html = self.resource_string("static/html/staff-view.html")
        frag = Fragment(html.format(self=self))
        frag.add_css(self.resource_string("static/css/student-view.css"))
        frag.add_javascript(self.resource_string("static/js/src/gigachat_grading.js"))
        frag.initialize_js('GigaChatAIGradingXBlock')
        return frag

    @XBlock.handler
    def handle_upload(self, request, suffix=''):
        user = self.get_real_user()
        student = user.username
        uploaded = request.params.get('file')
        if not uploaded:
            return Response(json_body={'error': 'No file uploaded.'}, status=400)
        # save to temp
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
        tmp.file.write(uploaded.file.read())
        tmp.close()
        # grade via GigaChat
        log.warning(self.auth_key)
        log.warning(tmp.name)
        log.warning("!!!!!!!!!!!!!!!!!!!!!")
        raw = upload_pdf_to_gigachat(self.auth_key, tmp.name, self.grading_prompt)
        try:
            result = json.loads(raw)
        except:
            result = {'score': 0, 'comment': 'Invalid response'}
        # store submission
        self.submissions[student] = {
            'file_name': uploaded.filename,
            'file_url': uploaded.url,
            'graded': True,
            'approved': False,
            'score': result['score'],
            'comment': result['comment']
        }
        return Response(json_body={'status':'submitted'})

    @XBlock.json_handler
    def handle_override(self, data, suffix=''):
        # process instructor changes
        for user_id in self.submissions.keys():
            score = data.get(f'score_{user_id}')
            comment = data.get(f'comment_{user_id}')
            approve = data.get(f'approve_{user_id}')
            if score is not None:
                self.submissions[user_id]['score'] = float(score)
            if comment is not None:
                self.submissions[user_id]['comment'] = comment
            self.submissions[user_id]['approved'] = bool(approve)
        # allow prompt/weight override
        self.grading_prompt = data.get('grading_prompt', self.grading_prompt)
        self.grade_weight = float(data.get('grade_weight', self.grade_weight))
        return {'result':'success'}

    def resource_string(self, path):
        import pkg_resources
        data = pkg_resources.resource_string(__name__, path)
        return data.decode('utf8')

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

    def get_real_user(self):
        """returns session user"""
        if user_service := self.runtime.service(self, 'user'):
            return user_service.get_user_by_anonymous_id()
        return None
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
    # def call_giga_chat_api(self, text, prompt):
    #     """
    #     Отправка текста с дополнительным промтом в GigaChat API для получения оценки.
    #     """
    #     GIGACHAT_AUTH_KEY = getattr(settings,'GIGACHAT_AUTH_KEY', "")
    #     auth_key = GIGACHAT_AUTH_KEY
    #     client = GigaChat(credentials=auth_key,verify_ssl_certs=False, scope="GIGACHAT_API_PERS", model="GigaChat-Lite")

    #     # Соединение промта и текста работы
    #     full_prompt = prompt + "\n\nТекст работы:\n" + text
        
    #     try:
    #         response = client.chat(
    #             messages=[
    #                 {"role": "system", "content": "Вы — помощник для оценки учебных работ."},
    #                 {"role": "user", "content": full_prompt}
    #             ]
    #         )
            
    #         # Ответ модели хранится в content
    #         reply = response.content.strip()
            
    #         # Попытка парсинга ответа как JSON
    #         result_obj = json.loads(reply)
    #         return result_obj
    #     except Exception as e:
    #         log.error("Ошибка при вызове GigaChat API: %s", e)
    #         return {"score": 0, "comment": "Ошибка при обработке работы: " + str(e)}