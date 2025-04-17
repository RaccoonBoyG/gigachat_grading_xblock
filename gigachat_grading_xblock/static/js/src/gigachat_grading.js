function GigaChatGradingXBlock(runtime, element) {
  $('#essay-upload-form', element).submit(function (event) {
    event.preventDefault();
    var formData = new FormData();
    var fileInput = $('#essay-file', element)[0];
    if (fileInput.files.length === 0) {
      alert('Пожалуйста, выберите файл.');
      return;
    }
    formData.append('essay_file', fileInput.files[0]);

    $.ajax({
      url: runtime.handlerUrl(element, 'grade_submission'),
      type: 'POST',
      data: formData,
      processData: false,
      contentType: false,
      success: function (response) {
        $('#score', element).text(response.score);
        $('#comment', element).text(response.comment);
      },
      error: function () {
        alert('Произошла ошибка при отправке файла.');
      },
    });
  });
}
