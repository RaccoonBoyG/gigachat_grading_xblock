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
        if (response.approved) {
          $('#score').text(response.score);
          $('#comment').text(response.comment);
          $('.grading-block__status').hide();
        } else {
          $('.grading-block__status').show().text('Работа отправлена на проверку');
          $('#score, #comment').empty();
        }
        $('#result').show();
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
  function loadSubmissions() {
    $.ajax({
      url: runtime.handlerUrl(element, 'get_submissions_data'),
      type: 'GET',
      success: function (data) {
        populateTable(data);
      },
      error: function () {
        alert('Не удалось загрузить работы');
      },
    });
  }

  // Функция заполнения таблицы
  function populateTable(submissions) {
    var tbody = $('#submissions-table tbody', element);
    tbody.empty();

    Object.keys(submissions).forEach(function (studentId, index) {
      var sub = submissions[studentId];
      var row = `
        <tr data-student="${studentId}" style="width: 100%;">
          <td>${index + 1}</td>
          <td>${studentId}</td>
          <td><a href="${sub.file_url}" target="_blank">${sub.file_name}</a></td>
          <td class="score-cell">${sub.score || '—'}</td>
          <td class="comment-cell">${sub.comment || '—'}</td>
          <td>
            <button class="btn btn-success approve-btn" data-student="${studentId}">
              Одобрить
            </button>
            <button class="btn btn-warning edit-btn" data-student="${studentId}">
              <i class="fa fa-pencil-square-o" aria-hidden="true"></i>
            </button>
            <button class="btn btn-danger reset-btn" data-student="${studentId}">
              <i class="fa fa-trash-o" aria-hidden="true"></i>
            </button>
          </td>
        </tr>
      `;
      tbody.append(row);
    });
  }

  // Обработчик кнопки проверки
  $('#check-button', element).on('click', function (e) {
    e.preventDefault();
    $('#staff-table').toggle();
    if ($('#staff-table').is(':visible')) {
      loadSubmissions();
    }
  });

  $('#update-button', element).on('click', function (e) {
    e.preventDefault();
    loadSubmissions();
  });

  // Обработчик одобрения работы
  $(element).on('click', '.approve-btn', function () {
    var studentId = $(this).data('student');
    $.ajax({
      url: runtime.handlerUrl(element, 'approve_submission'),
      type: 'POST',
      data: JSON.stringify({ student_id: studentId }),
      contentType: 'application/json',
      success: function () {
        loadSubmissions(); // Обновляем таблицу
      },
    });
  });

  // Модальное окно для редактирования
  function createEditModal() {
    return `
          <div id="editModal" class="modal fade" tabindex="-1">
            <div class="modal-dialog">
              <div class="modal-content">
                <div class="modal-header">
                  <h5 class="modal-title">Изменить оценку</h5>
                  <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                  <input type="number" class="form-control mb-2" id="new-score" placeholder="Оценка">
                  <textarea class="form-control" id="new-comment" placeholder="Комментарий"></textarea>
                </div>
                <div class="modal-footer">
                  <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                  <button type="button" class="btn btn-primary" id="save-changes">Сохранить</button>
                </div>
              </div>
            </div>
          </div>
        `;
  }

  // Добавляем модальное окно
  $(element).append(createEditModal());

  // Обработчик кнопки "Изменить"
  $(element).on('click', '.edit-btn', function () {
    var studentId = $(this).data('student');
    var sub = self.submissions[studentId];

    // Заполняем модальное окно текущими значениями
    $('#new-score').val(sub.score || '');
    $('#new-comment').val(sub.comment || '');

    // Сохраняем студента в data модального окна
    $('#editModal').data('student', studentId);
    $('#editModal').modal('show');
  });

  // Сохранение изменений из модального окна
  $('#save-changes', element).on('click', function () {
    var studentId = $('#editModal').data('student');
    var newScore = $('#new-score').val();
    var newComment = $('#new-comment').val();

    $.ajax({
      url: runtime.handlerUrl(element, 'update_submission'),
      type: 'POST',
      data: JSON.stringify({
        student_id: studentId,
        score: newScore,
        comment: newComment,
      }),
      contentType: 'application/json',
      success: function () {
        $('#editModal').modal('hide');
        loadSubmissions(); // Обновляем таблицу
      },
    });
  });

  // Обработчик кнопки "Сбросить"
  $(element).on('click', '.reset-btn', function () {
    if (!confirm('Сбросить попытку студента?')) return;

    var studentId = $(this).data('student');

    $.ajax({
      url: runtime.handlerUrl(element, 'reset_submission'),
      type: 'POST',
      data: JSON.stringify({ student_id: studentId }),
      contentType: 'application/json',
      success: function () {
        loadSubmissions(); // Обновляем таблицу
      },
    });
  });
}
