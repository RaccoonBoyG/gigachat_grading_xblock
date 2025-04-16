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

from gigachat import client # требуется установить библиотеку: pip install openai

# Для чтения PDF и DOCX используются библиотеки, их установка:
# pip install PyPDF2 python-docx

import PyPDF2
import docx

from xblock.core import XBlock
from xblock.fields import Scope, String, Float, Dict
from xblock.fragment import Fragment
from django.conf import settings

log = logging.getLogger(__name__)


class GigaChatAIGradingXBlock(XBlock):
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
        """
        Основной интерфейс для студента: форма загрузки файла.
        """
        html = """
            <div>
                <h3>Проверка работы с помощью OpenAI</h3>
                <p>Загрузите свой файл (PDF или DOCX) для автоматической проверки.</p>
                <form id="upload_form" method="post" enctype="multipart/form-data">
                    <input name="uploaded_file" id="uploaded_file" type="file"/>
                    <br/><br/>
                    <button type="button" onclick="submitFile()">Отправить на проверку</button>
                </form>
                <div id="result"></div>
            </div>

            <script>
                function submitFile(){
                    var formData = new FormData();
                    var fileInput = document.getElementById('uploaded_file');
                    if (fileInput.files.length == 0) {
                        alert("Пожалуйста, выберите файл для загрузки");
                        return;
                    }
                    formData.append("uploaded_file", fileInput.files[0]);

                    var xhr = new XMLHttpRequest();
                    xhr.open("POST", runtime.handlerUrl(element, 'handle_upload'));
                    xhr.onload = function(){
                        if(xhr.status === 200){
                            document.getElementById("result").innerHTML = "<pre>" + xhr.responseText + "</pre>";
                        } else {
                            document.getElementById("result").innerHTML = "Ошибка при обработке файла.";
                        }
                    };
                    xhr.send(formData);
                }
            </script>
        """
        fragment = Fragment(html)
        fragment.add_css("""
            /* Простейшие стили */
            div { font-family: Arial, sans-serif; }
            pre { background: #f8f8f8; padding: 10px; border: 1px solid #ccc; }
        """)
        return fragment

    def studio_view(self, context=None):
        """
        Редактор для преподавателя, в котором можно задать промт и установить/изменить оценку.
        """
        html = """
            <div>
                <h3>Настройки проверки работы</h3>
                <form id="studio_form">
                    <label for="grading_prompt">Промт проверки:</label><br/>
                    <textarea id="grading_prompt" name="grading_prompt" rows="10" cols="80">{grading_prompt}</textarea><br/><br/>
                    
                    <label for="overridden_score">Оценка (0-1):</label><br/>
                    <input type="number" id="overridden_score" name="overridden_score" min="0" max="1" step="0.01" value="{overridden_score}" /><br/><br/>
                    
                    <label for="overridden_comment">Комментарий:</label><br/>
                    <textarea id="overridden_comment" name="overridden_comment" rows="5" cols="80">{overridden_comment}</textarea><br/><br/>
                    
                    <button type="button" onclick="saveStudioSettings()">Сохранить</button>
                </form>
                
                <script>
                    function saveStudioSettings(){
                        var data = {
                            grading_prompt: document.getElementById('grading_prompt').value,
                            overridden_score: document.getElementById('overridden_score').value,
                            overridden_comment: document.getElementById('overridden_comment').value
                        };
                        var xhr = new XMLHttpRequest();
                        xhr.open("POST", runtime.handlerUrl(element, 'studio_submit'));
                        xhr.setRequestHeader("Content-Type", "application/json;charset=UTF-8");
                        xhr.onload = function(){
                            if(xhr.status === 200){
                                alert("Настройки успешно сохранены");
                            } else {
                                alert("Ошибка при сохранении настроек");
                            }
                        };
                        xhr.send(JSON.stringify(data));
                    }
                </script>
            </div>
        """
        # Форматируем шаблон, подставляя текущие значения
        html = html.format(
            grading_prompt=self.grading_prompt,
            overridden_score=self.overridden_score if self.overridden_score is not None else "",
            overridden_comment=self.overridden_comment
        )
        fragment = Fragment(html)
        fragment.add_css("""
            /* Простые стили для интерфейса преподавателя */
            label { font-weight: bold; }
            textarea, input { width: 100%; }
        """)
        return fragment

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

    # def call_openai_api(self, text, prompt):
    #     """
    #     Отправка текста с дополнительным промтом в OpenAI API для получения оценки.
    #     В данном примере используется ChatGPT API. Настройте ключ API и другие параметры.
    #     """
    #     # Объединяем тему проверки и текст файла
    #     full_prompt = prompt + "\n\nТекст работы:\n" + text

    #     try:
    #         response = openai.ChatCompletion.create(
    #             model="gpt-3.5-turbo",  # или другой используемый вариант
    #             messages=[
    #                 {"role": "system", "content": "Вы — помощник для оценки учебных работ."},
    #                 {"role": "user", "content": full_prompt}
    #             ],
    #             temperature=0.2,
    #             max_tokens=500
    #         )
    #         reply = response.choices[0].message.content.strip()
    #         # Попытка распарсить ответ как JSON
    #         result_obj = json.loads(reply)
    #         return result_obj
    #     except Exception as e:
    #         log.error("Ошибка при вызове OpenAI API: %s", e)
    #         return {"score": 0, "comment": "Ошибка при обработке работы: " + str(e)}

    def call_giga_chat_api(self, text, prompt):
        """
        Отправка текста с дополнительным промтом в GigaChat API для получения оценки.
        """
        auth_key = settings.FEATURES.get("GIGACHAT_AUTH_KEY", "")
        clientmy = client(credentials=auth_key,verify_ssl_certs=False, scope="GIGACHAT_API_PERS", model="GigaChat-Lite")

        # Соединение промта и текста работы
        full_prompt = prompt + "\n\nТекст работы:\n" + text
        
        try:
            response = clientmy.chat(
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
    def student_debug_view(self, context=None):
        html = "<div><pre>{}</pre></div>".format(json.dumps({
            "grading_prompt": self.grading_prompt,
            "result": self.result,
            "overridden_score": self.overridden_score,
            "overridden_comment": self.overridden_comment
        }, indent=2))
        frag = Fragment(html)
        return frag

    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("GigaChatAIGradingXBlock",
             """<gigachat_grading_xblock/>
             """),
            ("Multiple GigaChatAIGradingXBlock",
             """<vertical_demo>
                <gigachat_grading_xblock/>
                <gigachat_grading_xblock/>
                <gigachat_grading_xblock/>
                </vertical_demo>
             """),
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
