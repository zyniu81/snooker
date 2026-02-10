document.addEventListener('DOMContentLoaded', function () {
    const gptBtn = document.getElementById('gptAnalysisBtn');
    const gptModal = new bootstrap.Modal(document.getElementById('gptModal'));
    const gptResponse = document.getElementById('gptResponse');

    gptBtn.addEventListener('click', function () {
        gptModal.show();
        fetch('/gpt-analysis/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        })
            .then(response => response.json())
            .then(data => {
                if (data.analysis) {
                    gptResponse.textContent = data.analysis;
                } else {
                    gptResponse.textContent = 'An error occurred during analysis.';
                }
            })
            .catch(error => {
                console.error('Error:', error);
                gptResponse.textContent = 'An error occurred while communicating with the server.';
            });
    });

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
});
