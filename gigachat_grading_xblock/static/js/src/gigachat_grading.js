function GigaChatGradingXBlock(runtime, element) {
  // Обработчик клика по кнопке отправки
  $('.submit-button', element).on('click', function (event) {
    event.preventDefault();

    var fileInput = $('#essay-file', element)[0];
    if (!fileInput || fileInput.files.length === 0) {
      alert('Пожалуйста, выберите файл.');
      return;
    }

    var formData = new FormData();
    formData.append('essay_file', fileInput.files[0]);

    $.ajax({
      url: runtime.handlerUrl(element, 'grade_submission'),
      type: 'POST',
      data: formData,
      processData: false, // Не преобразовывать данные в строку запроса
      contentType: false, // Не устанавливать заголовок Content-Type
      success: function (response) {
        $('#score', element).text(response.score);
        $('#comment', element).text(response.comment);
        $('#grading-result', element).show();
      },
      error: function () {
        alert('Произошла ошибка при отправке файла.');
      },
    });
  });
}
