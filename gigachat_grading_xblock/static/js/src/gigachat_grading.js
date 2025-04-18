function GigaChatAIGradingXBlock(runtime, element) {
  // Клик по кастомной кнопке отправки
  $('#submit-button', element).on('click', function (event) {
    event.preventDefault();

    var fileInput = $('#file-input', element)[0];
    if (!fileInput || fileInput.files.length === 0) {
      alert('Выберите файл для загрузки.');
      return;
    }

    var formData = new FormData();
    formData.append('file', fileInput.files[0]);

    $.ajax({
      url: runtime.handlerUrl(element, 'handle_upload'),
      type: 'POST',
      data: formData,
      processData: false,
      contentType: false,
      success: function (response) {
        $('#score', element).text(response.score);
        $('#comment', element).text(response.comment);
        $('#result', element).show();
      },
      error: function () {
        alert('Ошибка при отправке файла.');
      },
    });
  });

  // Сохранение изменений в режиме Studio
  $('#save-button', element).on('click', function (event) {
    event.preventDefault();
    var data = {
      prompt: $('#prompt', element).val(),
      weight: $('#weight', element).val(),
      // поля оценки/комментария и approve собираются внутри handle_override
    };
    $.ajax({
      url: runtime.handlerUrl(element, 'handle_override'),
      type: 'POST',
      data: JSON.stringify(data),
      contentType: 'application/json',
      success: function () {
        alert('Настройки сохранены');
      },
      error: function () {
        alert('Ошибка при сохранении настроек.');
      },
    });
  });
}
