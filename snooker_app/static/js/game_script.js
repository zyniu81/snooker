let timerInterval;
let elapsedSeconds = 0;
let activePlayer = null;
let foulPoints = 0;
let nextPlayerId = null;

function resetScores() {
    document.querySelectorAll('.player-score').forEach(input => {
        input.value = 0;
    });
}

function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600).toString().padStart(2, '0');
    const minutes = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${hours}:${minutes}:${secs}`;
}

function startTimer() {
    if (!timerInterval) {
        timerInterval = setInterval(() => {
            elapsedSeconds++;
            document.getElementById("match-timer").textContent = formatTime(elapsedSeconds);
        }, 1000);
    }
}

function pauseTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
}

function stopTimer() {
    pauseTimer();
}

    function resetGame() {
    pauseTimer();
    elapsedSeconds = 0;
    document.getElementById("match-timer").textContent = formatTime(elapsedSeconds);

    resetScores();
    activePlayer = null;
    document.querySelectorAll(".set-active-player").forEach(button => {
        button.classList.remove("active");
    });
}

function setActivePlayer(playerId) {
    activePlayer = playerId;
    updateActivePlayerUI(playerId);
}

function updateActivePlayerUI(playerId) {
    document.querySelectorAll(".set-active-player").forEach(button => {
        button.classList.remove("active");
    });

    const activeButton = document.querySelector(`.set-active-player[data-player="${playerId}"]`);
    if (activeButton) {
        activeButton.classList.add("active");
    }
}

function updateScore(points) {
    if (activePlayer === null) {
        alert("Please select an active player first!");
        return;
    }

    const playerScoreInput = document.querySelector(
        `.set-active-player[data-player="${activePlayer}"]`
    ).closest('.d-flex').querySelector('.player-score');

    const currentScore = parseInt(playerScoreInput.value, 10) || 0;
    playerScoreInput.value = currentScore + points;
}

function miss() {
    if (activePlayer === null) {
        alert("Please select an active player first!");
        return;
    }
    switchActivePlayer();
}

function safetyShot() {
    if (activePlayer === null) {
        alert("Please select an active player first!");
        return;
    }
    switchActivePlayer();
}

function switchActivePlayer() {
    if (activePlayer === null) {
        alert("No active player to switch!");
        return;
    }
    activePlayer = activePlayer === 1 ? 2 : 1;
    updateActivePlayerUI(activePlayer);
}

function showFoulModal() {
    $('#foulModal').modal('show');

    foulPoints = 0;
    nextPlayerId = null;
    document.querySelectorAll('.foul-points').forEach(button => button.classList.remove('active'));
    document.querySelectorAll('.next-player').forEach(button => button.classList.remove('active'));
}

document.querySelectorAll('.foul-points').forEach(button => {
    button.addEventListener('click', () => {
        document.querySelectorAll('.foul-points').forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        foulPoints = parseInt(button.getAttribute('data-points'));
    });
});

document.querySelectorAll('.next-player').forEach(button => {
    button.addEventListener('click', () => {
        document.querySelectorAll('.next-player').forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        nextPlayerId = parseInt(button.getAttribute('data-player'));
    });
});

document.getElementById('confirmFoul').addEventListener('click', () => {
    if (foulPoints > 0 && nextPlayerId !== null) {
        const opponentId = activePlayer === 1 ? 2 : 1;

        const opponentScoreElement = document.querySelector(`.player-score[data-player="${opponentId}"]`);

        opponentScoreElement.value = parseInt(opponentScoreElement.value || '0', 10) + foulPoints;

        setActivePlayer(nextPlayerId);

        $('#foulModal').modal('hide');
    } else {
        alert("Please select foul points and the next player.");
    }
});

document.querySelectorAll('.set-active-player').forEach(button => {
    button.addEventListener('click', () => {
        const playerId = parseInt(button.dataset.player, 10);
        setActivePlayer(playerId);
    });
});
