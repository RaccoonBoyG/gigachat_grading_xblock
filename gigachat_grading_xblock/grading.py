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
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .utils import upload_pdf_to_gigachat
from webob import Response
from submissions import api as submissions_api
from lms.djangoapps.courseware.models import StudentModule

log = logging.getLogger(__name__)

ITEM_TYPE = "ai_grading"
ATTR_KEY_ANONYMOUS_USER_ID = 'edx-platform.anonymous_user_id'

def reify(meth):
    """
    Decorator which caches value so it is only computed once.
    Keyword arguments:
    inst
    """

    def getter(inst):
        """
        Set value to meth name in dict and returns value.
        """
        value = meth(inst)
        inst.__dict__[meth.__name__] = value
        return value

    return property(getter)

@XBlock.needs('user')
class GigaChatAIGradingXBlock(StudioEditableXBlockMixin, XBlock):
    editable_fields = ('display_name', 'grading_prompt', 'grade_weight', 'auth_key')
    """
    XBlock для проверки работ с помощью OpenAI API.
    """

    # Настраиваемые поля XBlock
    # Поле для хранения темы проверки (промта)
    grading_prompt = String(
        help="Тема для промта. например: История России", 
        default="",
        scope=Scope.settings,
        display_name="Тема для проверки"
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
    submissions = Dict(help="Все ответы студентов", default={}, scope=Scope.user_state)
    grade_weight = Float(help="Weight of this component (0-1)", default=1.0, scope=Scope.content)
    auth_key = String(help="Ключ от нейросети", default="", scope=Scope.settings)

    @reify
    def block_id(self):
        """
        Return the usage_id of the block.
        """
        return str(self.scope_ids.usage_id)

    @reify
    def block_course_id(self):
        """
        Return the course_id of the block.

        Note: if this block is used in a Content Library, the returned ID will be the library's ID.
        """
        return str(self.context_key)

    def student_view(self, context=None):
        user = self.get_real_user()
        is_staff = user.is_staff if user else False

        try:
            html = self.resource_string(
                f"static/html/{'staff' if is_staff else 'student'}-view.html"
            )
        except Exception as e:
            return Fragment(f"<div>Ошибка загрузки шаблона: {str(e)}</div>")

        # try:
        frag = Fragment()
        log.warning(self.submissions)
        submission = self.get_submission(self.get_student_id())
        log.warning(submission)
        log.warning("self.submissions[self.get_student_id()]self.submissions[self.get_student_id()]")
        if submission is None:
            context = {
                "approved": False
            }
        else:
            context = {
                "approved": submission['approved']
            }
        frag.add_content(render_template(f"static/html/{'staff' if is_staff else 'student'}-view.html", context=context))
        # except Exception as e:
            # frag = Fragment(f"<div>Ошибка рендеринга: {str(e)}</div>")

        frag.add_css(self.resource_string("static/css/student-view.css"))
        frag.add_javascript(self.resource_string("static/js/src/gigachat_grading.js"))
        frag.initialize_js('GigaChatAIGradingXBlock')
        return frag

    def get_student_item_dict(self, student_id=None):
        """
        Returns dict required by the submissions app for creating and
        retrieving submissions for a particular student.
        """
        if student_id is None and (user_service := self.runtime.service(self, 'user')):
            student_id = user_service.get_current_user().opt_attrs.get(ATTR_KEY_ANONYMOUS_USER_ID)
            assert student_id != ("MOCK", "Forgot to call 'personalize' in test.")
        return {
            "student_id": student_id,
            "course_id": self.block_course_id,
            "item_id": self.block_id,
            "item_type": ITEM_TYPE,
        }

    def get_submission(self, student_id=None):
        """
        Get student's most recent submission.
        """
        submissions = submissions_api.get_submissions(
            self.get_student_item_dict(student_id)
        )
        if submissions:
            # If I understand docs correctly, most recent submission should
            # be first
            return submissions[0]

        return None
    
    @XBlock.handler
    def handle_upload(self, request, suffix=''):
        user = self.get_real_user()
        student = user.username

        uploaded = request.params.get('file')
        if not uploaded:
            return Response(json_body={'error': 'No file uploaded.'}, status=400)

        self.get_or_create_student_module(user)
        # Сохраняем файл в MEDIA/submissions/<student>/
        filename = uploaded.filename
        content = uploaded.file.read()
        path = f'submissions/{student}/{filename}'
        storage_path = default_storage.save(path, ContentFile(content))
        file_url = default_storage.url(storage_path)

        # 3. Дальше ваша логика: grade via GigaChat и т.п.
        promt = self.gen_promt()
        result = upload_pdf_to_gigachat(self.auth_key, default_storage.path(storage_path), promt)
        answer = {
            'file_name': filename,
            'file_url': file_url,
            'approved': False,
            'score': result['score'],
            'comment': result['comment']
        }
        # 4. Сохраняем в submissions
        student_item_dict = self.get_student_item_dict()
        submissions_api.create_submission(student_item_dict, answer)

        return Response(json_body={'status': 'submitted'})
    
    @XBlock.handler
    def get_submissions_data(self, request, suffix=''):
        if not self.runtime.user_is_staff:
            return Response(json_body={'error': 'Доступ запрещен'}, status=403)
        
        # Возвращаем все работы студентов
        return Response(json_body=self.submissions)

    @XBlock.handler
    def approve_submission(self, request, suffix=''):
        if not self.runtime.user_is_staff:
            return Response(status=403)
        
        data = json.loads(request.body.decode('utf-8'))
        student_id = data.get('student_id')
        
        if student_id in self.submissions:
            self.submissions[student_id]['approved'] = True
            # Сохраняем изменения
            submissions = self.submissions
            self.submissions = submissions
        
        return Response(json_body={'status': 'success'})

    @XBlock.handler
    def update_submission(self, request, suffix=''):
        if not self.runtime.user_is_staff:
            return Response(status=403)
        
        data = json.loads(request.body.decode('utf-8'))
        student_id = data.get('student_id')
        
        if student_id in self.submissions:
            # Обновляем оценку и комментарий
            self.submissions[student_id]['score'] = data.get('score')
            self.submissions[student_id]['comment'] = data.get('comment')
            
            # Сохраняем изменения через XBlock API
            submissions = self.submissions
            self.submissions = submissions
        
        return Response(json_body={'status': 'success'})

    @XBlock.handler
    def reset_submission(self, request, suffix=''):
        if not self.runtime.user_is_staff:
            return Response(status=403)
        
        data = json.loads(request.body.decode('utf-8'))
        student_id = data.get('student_id')
        
        if student_id in self.submissions:
            # Удаляем файл из хранилища
            file_path = self.submissions[student_id].get('file_url', '')
            if file_path:
                # Извлекаем путь из URL (зависит от реализации storage)
                path = file_path.replace(default_storage.url(''), '', 1)
                default_storage.delete(path)
            
            # Удаляем запись о работе
            del self.submissions[student_id]
            
            # Сохраняем изменения
            submissions = self.submissions
            self.submissions = submissions
        
        return Response(json_body={'status': 'success'})

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
    
    def get_or_create_student_module(self, user):
        """
        Gets or creates a StudentModule for the given user for this block

        Returns:
            StudentModule: A StudentModule object
        """
        student_module, created = StudentModule.objects.get_or_create(
            course_id=self.course_id,
            module_state_key=self.location,
            student=user,
            defaults={
                "state": "{}",
                "module_type": self.category,
            },
        )
        if created:
            log.info(
                "Created student module %s [course: %s] [student: %s]",
                student_module.module_state_key,
                student_module.course_id,
                student_module.student.username,
            )
        return student_module
    
    def get_student_username(self):
        user = self.runtime.get_real_user()
        return user.username if user else None
    
    def get_student_id(self):
        user = self.runtime.get_real_user()
        return user.id if user else None

    def get_submissions(self):
        if not hasattr(self, 'submissions'):
            self.submissions = {}
        return self.submissions

    def gen_promt(self) -> str:
        prompt = """Ты — эксперт по проверке академических работ. Твоя задача состоит в объективной оценке реферата, эссе или доклада по заданной теме - {}. Сначала внимательно прочти предоставленный текст, а затем выполни следующее пошагово:

1. **Определение темы**: Четко пойми и сформулируй основную тему текста («{}»).
   
2. **Оценка полноты**:
   - Определены ли ключевые аспекты и важные элементы данной темы?
   - Отмечены ли наиболее значимые события, концепции или данные?

3. **Анализ структуры**:
   - Есть ли чёткое введение, основное содержание и заключение?
   - Логична ли последовательность изложенных мыслей и аргументов?
   - Хорошо ли организован материал?

4. **Проверка языка и фактов**:
   - Ясны ли формулировки и понятны ли читателю?
   - Имеются ли фактические ошибки или несоответствия действительности?

5. **Подведение итогов**:
   - Оцени каждый критерий по шкале от 0 до 1 (с точностью до двух знаков).
   - Рассчитай среднее арифметическое всех оценок, округлив до двух знаков после запятой.

6. **Напиши комментарий**:
   - Кратко подчеркни сильные стороны работы.
   - Предложи конкретные рекомендации по улучшению.

7. **Формат вывода**:
   - Предоставь результаты исключительно в виде JSON-кода без пояснений:

Пример:
{
  score: XX.XX,
  comment: Краткая оценка качества и рекомендаций...
}
""".format(self.grading_prompt, self.grading_prompt)
        return prompt
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