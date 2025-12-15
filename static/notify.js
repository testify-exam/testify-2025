          // Alert Functions
          function showAlert(title, message) {
            document.getElementById('alertTitle').textContent = title;
            document.getElementById('alertMessage').textContent = message;
            document.getElementById('alertOverlay').classList.add('active');
        }

        function closeAlert() {
            document.getElementById('alertOverlay').classList.remove('active');
        }

        // Confirmation Functions
        let confirmCallback = null;

        function showConfirm(title, message, callback) {
            document.getElementById('confirmTitle').textContent = title;
            document.getElementById('confirmMessage').textContent = message;
            document.getElementById('confirmOverlay').classList.add('active');
            confirmCallback = callback;

            // Set up the OK button click handler
            document.getElementById('confirmOkBtn').onclick = function() {
                closeConfirm();
                if (typeof confirmCallback === 'function') {
                    confirmCallback();
                }
            };
        }

        function closeConfirm() {
            document.getElementById('confirmOverlay').classList.remove('active');
        }

        function confirmStartExam() {
            showConfirm(
                'Confirmation',
                'Once you start the exam, you cannot go back. Switching to other apps will auto-submit your exam. Are you sure you want to proceed?',
                function() { showLoading();
                    document.getElementById('examForm').submit(); 
                }
            );
        }