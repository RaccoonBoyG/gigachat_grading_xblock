"""
xblock helpers.
"""
import os
from html.parser import HTMLParser
from django.template import Context, Engine
import os
import tempfile
from gigachat import GigaChat

html_parser = HTMLParser()  # pylint: disable=invalid-name


def render_template(template_name, **context):
    """
    Render static resource using provided context.

    Returns: django.utils.safestring.SafeText
    """
    template_dirs = [os.path.join(os.path.dirname(__file__), "static/html")]
    libraries = {"gigachat_grading_xblock_tags": "gigachat_grading_xblock.templatetags"}
    engine = Engine(dirs=template_dirs, debug=True, libraries=libraries)
    html = engine.get_template(template_name)

    return html_parser.unescape(html.render(Context(context)))

def upload_pdf_to_gigachat(api_key, file_path, prompt):
    client = GigaChat(credentials=api_key, verify_ssl_certs=False, scope="GIGACHAT_API_PERS", model="GigaChat-Lite")
    # upload PDF file
    file_id = client.upload_file(file_path)
    # create a new thread for grading
    req = {
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "attachments": [file_id],
            }
        ],
        "temperature": 0.1
    }
    response = client.chat(req)
    result = response.choices[0].message.content
    return result