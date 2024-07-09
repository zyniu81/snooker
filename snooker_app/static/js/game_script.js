let activePlayer = 1;
let scores = [0, 0];
let timerInterval;
let startTime;
let elapsedTime = 0;
let timerRunning = false;
let pointsOnTable = 147;
let maxPossibleBreak = 147;
let actionHistory = [];


function addToHistory(action) {
    actionHistory.push(action);
    console.log('Action added to history:', action);
    console.log('Current history:', actionHistory);
}


function setActivePlayer(player) {
    activePlayer = parseInt(player);
    document.querySelectorAll('.player-score').forEach((el, index) => {
        el.parentElement.classList.remove('active-player');
        if (index + 1 === activePlayer) {
            el.parentElement.classList.add('active-player');
        }
    });
}


function updateScore(points) {
    let previousScore = scores[activePlayer - 1];
    let previousPointsOnTable = pointsOnTable;

    scores[activePlayer - 1] += points;
    document.querySelectorAll('.player-score')[activePlayer - 1].value = scores[activePlayer - 1];

    pointsOnTable = Math.max(0, pointsOnTable - points);
    document.getElementById('points-on-table').textContent = pointsOnTable;

    maxPossibleBreak = pointsOnTable + scores[activePlayer - 1];
    document.getElementById('max-possible-break').textContent = maxPossibleBreak;

    addToHistory({
        type: 'updateScore',
        player: activePlayer,
        points: points,
        previousScore: previousScore,
        previousPointsOnTable: previousPointsOnTable
    });
}


function reverse() {
    console.log('Reverse function called');
    if (actionHistory.length === 0) {
        console.log('No actions to reverse');
        return;
    }

    let lastAction = actionHistory.pop();
    console.log('Reversing action:', lastAction);

    switch (lastAction.type) {
        case 'updateScore':
            scores[lastAction.player - 1] = lastAction.previousScore;
            document.querySelectorAll('.player-score')[lastAction.player - 1].value = lastAction.previousScore;
            pointsOnTable = lastAction.previousPointsOnTable;
            document.getElementById('points-on-table').textContent = pointsOnTable;
            maxPossibleBreak = pointsOnTable + Math.max(...scores);
            document.getElementById('max-possible-break').textContent = maxPossibleBreak;
            break;
        case 'miss':
        case 'safetyShot':
            setActivePlayer(lastAction.previousPlayer);
            maxPossibleBreak = lastAction.previousMaxPossibleBreak;
            document.getElementById('max-possible-break').textContent = maxPossibleBreak;
            break;
        case 'foul':
            scores[lastAction.player - 1] = lastAction.previousScore;
            document.querySelectorAll('.player-score')[lastAction.player - 1].value = lastAction.previousScore;
            scores[lastAction.previousActivePlayer - 1] = lastAction.currentPlayerScore;
            document.querySelectorAll('.player-score')[lastAction.previousActivePlayer - 1].value = lastAction.currentPlayerScore;
            setActivePlayer(lastAction.previousActivePlayer);
            pointsOnTable = lastAction.previousPointsOnTable;
            document.getElementById('points-on-table').textContent = pointsOnTable;
            maxPossibleBreak = pointsOnTable + Math.max(...scores);
            document.getElementById('max-possible-break').textContent = maxPossibleBreak;
            break;
        default:
            console.log('Unknown action type:', lastAction.type);
    }

    console.log('Reverse completed. New state:', {
        scores,
        pointsOnTable,
        maxPossibleBreak,
        activePlayer
    });
}


function miss() {
    let previousPlayer = activePlayer;
    let previousMaxPossibleBreak = maxPossibleBreak;
    setActivePlayer(activePlayer === 1 ? 2 : 1);
    resetMaxPossibleBreak();
    addToHistory({
        type: 'miss',
        previousPlayer: previousPlayer,
        previousMaxPossibleBreak: previousMaxPossibleBreak
    })
}


function safetyShot() {
    let previousPlayer = activePlayer;
    let previousMaxPossibleBreak = maxPossibleBreak;
    setActivePlayer(activePlayer === 1 ? 2 : 1);
    resetMaxPossibleBreak();
    addToHistory({
        type: 'safetyShot',
        previousPlayer: previousPlayer,
        previousMaxPossibleBreak: previousMaxPossibleBreak
    })
}


function resetMaxPossibleBreak() {
    maxPossibleBreak = pointsOnTable;
    document.getElementById('max-possible-break').textContent = maxPossibleBreak;
}


function resetGame() {
    pointsOnTable = 147;
    maxPossibleBreak = 147;
    scores = [0, 0];
    document.getElementById('points-on-table').textContent = pointsOnTable;
    document.getElementById('max-possible-break').textContent = maxPossibleBreak;
    document.querySelectorAll('.player-score').forEach(el => el.value = 0);
    setActivePlayer(1);
    resetTimer();
    actionHistory = [];
}


function showFoulModal() {
    $('#foulModal').modal('show');
}


function foul(points) {
    let opponent = activePlayer === 1 ? 2 : 1;
    let previousScore = scores[opponent - 1];
    let previousActivePlayer = activePlayer;
    let previousPointsOnTable = pointsOnTable;
    let currentPlayerScore = scores[activePlayer - 1];

    scores[opponent - 1] += points;
    document.querySelectorAll('.player-score')[opponent - 1].value = scores[opponent - 1];

    pointsOnTable = Math.max(0, pointsOnTable - points);
    document.getElementById('points-on-table').textContent = pointsOnTable;

    setActivePlayer(opponent)

    $('#foulModal').modal('hide');

    addToHistory({
        type: 'foul',
        points: points,
        previousScore: previousScore,
        previousActivePlayer: previousActivePlayer,
        previousPointsOnTable: previousPointsOnTable,
        player: opponent,
        currentPlayerScore: currentPlayerScore
    });
}


function updateTimer() {
    if (timerRunning) {
        let currentTime = new Date().getTime();
        let totalElapsedTime = new Date(currentTime - startTime + elapsedTime);
        let hours = totalElapsedTime.getUTCHours().toString().padStart(2, '0');
        let minutes = totalElapsedTime.getUTCMinutes().toString().padStart(2, '0');
        let seconds = totalElapsedTime.getUTCSeconds().toString().padStart(2, '0');
        document.getElementById('match-timer').textContent = `${hours}:${minutes}:${seconds}`;
    }
}

function startTimer() {
    if (!timerRunning) {
        startTime = new Date().getTime();
        timerInterval = setInterval(updateTimer, 1000);
        timerRunning = true;
    }
}

function pauseTimer() {
    if (timerRunning) {
        clearInterval(timerInterval);
        elapsedTime += new Date().getTime() - startTime;
        timerRunning = false;
    }
}

function stopTimer() {
    if (timerRunning) {
        clearInterval(timerInterval);
        elapsedTime += new Date().getTime() - startTime;
        timerRunning = false;
    }
}

function resetTimer() {
    clearInterval(timerInterval);
    elapsedTime = 0;
    timerRunning = false;
    document.getElementById('match-timer').textContent = '00:00:00';
}



document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.set-active-player').forEach(button => {
        button.addEventListener('click', function () {
            setActivePlayer(this.dataset.player);
        });
    });

    const resetGameButton = document.querySelector('button[onclick="resetGame()"]');
    if (resetGameButton) {
        resetGameButton.addEventListener('click', resetGame);
    } else {
        console.error("Reset Game button not found");
    }

    const reverseButton = document.getElementById('reverseButton');
    if (reverseButton) {
        reverseButton.addEventListener('click', reverse);
    } else {
        console.error("Reverse button not found")
    }
    setActivePlayer(1);
    resetGame();
});
