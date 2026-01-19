let timerInterval;
let elapsedSeconds = 0;
let activePlayer = null;
let foulPoints = 0;
let nextPlayerId = null;
let lastPottedRed = false;
let redBallsPottedThisTurn = 0;
let redBallAdjustment = 0;
let undoStack = [];
let redoStack = [];
let gameState = {
    activePlayer: null,
    lastPottedRed: false,
    redBallsPottedThisTurn: 0
};
let currentBreak = 0;
let isFreeBall = false;
let lastShotWasFreeBall = false;
let pendingWinnerId = null; // Tymczasowa zmienna do przechowywania wybranego zwycięzcy
// --- ZMIENNE DO STATYSTYK ---
let p1Fouls = 0;        // Liczba fauli gracza 1
let p2Fouls = 0;        // Liczba fauli gracza 2
let p1FoulPoints = 0;   // Punkty oddane przez gracza 1
let p2FoulPoints = 0;   // Punkty oddane przez gracza 2

let p1Shots = 0;   // Ile razy podszedł do uderzenia (Total Shots)
let p1Misses = 0;  // Ile razy spudłował
let p1Pots = 0;    // Ile bil wbił

let p2Shots = 0;
let p2Misses = 0;
let p2Pots = 0;

let p1Safeties = 0;         // Wszystkie próby odstawnych
let p1SuccessfulSafeties = 0; // Tylko te skuteczne (gdy przeciwnik nie wbił)

let p2Safeties = 0;
let p2SuccessfulSafeties = 0;

// PAMIĘĆ (State)
let pendingSafetyCheck = false; // Czy czekamy na ocenę odstawnej?
let safetyPlayerId = null;      // Kto zagrał tę odstawną (1 lub 2)?

// HISTORIA BREAKÓW (Tablice)
let p1BreaksHistory = [];
let p2BreaksHistory = [];

// --- AST TRACKING ---
let turnStartTime = Date.now();
let currentTurnShots = 0; // Counts shots ONLY for the current visit to the table

let isUnsafeToLeave = true;


function recordAction(action) {

    // --- AST LOGIC: COUNT SHOTS ---
    if (action.type !== 'switchActivePlayer' && action.type !== 'undo' && action.type !== 'redo') {
        currentTurnShots++;
    }

    const actionWithState = {
        ...action,
        ballsVisibility: getBallsVisibilityState(),
        pointsOnTable: parseInt(document.getElementById("points-on-table").textContent, 10),
        redBallCount: parseInt(document.getElementById("red-ball-count").textContent, 10),
        lastPottedRed: gameState.lastPottedRed,
        redBallsPottedThisTurn: gameState.redBallsPottedThisTurn,

        //--- ZAPISUJEMY STATYSTYKI ---
        statsSnapshot: getStatsSnapshot()
    };

    console.log(actionWithState);
    undoStack.push(actionWithState);
    redoStack = [];

    updateActionLogUI();
}

function undo() {
    if (undoStack.length === 0) return;

    const lastAction = undoStack.pop();

    // --- Przygotowanie danych dla REDO ---
    lastAction.redoStatsSnapshot = getStatsSnapshot();

    console.log("Undoing action:", lastAction);
    redoStack.push(lastAction);

    // --- Przywracanie statystyk ---
    if (lastAction.statsSnapshot) {
        restoreStatsSnapshot(lastAction.statsSnapshot);
    }

    if (lastAction.type === "updateScore") {
        currentBreak = lastAction.previousBreak;
        updateBreakDisplay();

        if (lastAction.wasFreeBall) {
            isFreeBall = true;
        }

        if (lastAction.previousLastShotWasFreeBall !== undefined) {
            lastShotWasFreeBall = lastAction.previousLastShotWasFreeBall;
        }
    }

    switch (lastAction.type) {
        case "updateActivePlayer":
            if (lastAction.previousPlayerId !== null) {
                gameState.activePlayer = parseInt(lastAction.previousPlayerId, 10);
                activePlayer = gameState.activePlayer;

                document.querySelectorAll(".set-active-player").forEach(button => {
                    button.classList.remove("active");
                });
                const activeButton = document.querySelector(`.set-active-player[data-player="${gameState.activePlayer}"]`);
                if (activeButton) {
                    activeButton.classList.add("active");
                }

                const playerHeaders = document.querySelectorAll("h4");
                playerHeaders.forEach(header => {
                    header.innerHTML = header.innerHTML.replace(" 🔴", "");
                });
                if (gameState.activePlayer === 1) {
                    playerHeaders[0].innerHTML += " 🔴";
                } else if (gameState.activePlayer === 2) {
                    playerHeaders[1].innerHTML += " 🔴";
                }
            }

            if (lastAction.ballsVisibility) {
                restoreBallsVisibilityState(lastAction.ballsVisibility);
            }

            if (lastAction.pointsOnTable) {
                document.getElementById("points-on-table").textContent = lastAction.pointsOnTable;
            }

            if (lastAction.redBallCount !== undefined) {
                document.getElementById("red-ball-count").textContent = lastAction.redBallCount;
                updateRedBallsUI(lastAction.redBallCount);
            }
            break;

        case "updateScore":
            const playerScoreInput = document.querySelector(
                `.player-score[data-player="${lastAction.playerId}"]`
            );
            if (playerScoreInput) {
                playerScoreInput.value = lastAction.previousScore;
            }

            if (lastAction.redBallsChange) {
                const redBallsElement = document.getElementById("red-ball-count");
                if (redBallsElement) {
                    redBallsElement.textContent = lastAction.previousRedBalls;
                    updateRedBallsUI(lastAction.previousRedBalls);
                }
            }

            const pointsOnTableElement = document.getElementById("points-on-table");
            if (pointsOnTableElement) {
                pointsOnTableElement.textContent = lastAction.previousPointsOnTable;
                hideColorBallBasedOnPoints(lastAction.previousPointsOnTable);
            }

            if (lastAction.ballsVisibility) {
                restoreBallsVisibilityState(lastAction.ballsVisibility);
            }

            gameState.lastPottedRed = lastAction.lastPottedRed || false;
            gameState.redBallsPottedThisTurn = lastAction.redBallsPottedThisTurn || 0;
            break;

        case "foul":
            const opponentScoreElement = document.querySelector(
                `.player-score[data-player="${lastAction.opponentId}"]`
            );
            if (opponentScoreElement) {
                opponentScoreElement.value = lastAction.previousOpponentScore;
            }

            if (lastAction.redBallsChange) {
                const redBallsElement = document.getElementById("red-ball-count");
                if (redBallsElement) {
                    redBallsElement.textContent = lastAction.previousRedBalls;
                    updateRedBallsUI(lastAction.previousRedBalls);
                }

                const pointsOnTableElement = document.getElementById("points-on-table");
                if (pointsOnTableElement) {
                    pointsOnTableElement.textContent = lastAction.previousPointsOnTable;
                    hideColorBallBasedOnPoints(lastAction.previousPointsOnTable);
                }
            }

            if (lastAction.ballsVisibility) {
                restoreBallsVisibilityState(lastAction.ballsVisibility);
            }

            isFreeBall = false;

            if (lastAction.previousBreak !== undefined) {
                currentBreak = lastAction.previousBreak;
                updateBreakDisplay();
            }

            break;
    }

    updateActionLogUI();
}

function redo() {
    if (redoStack.length === 0) return;

    const lastUndone = redoStack.pop();
    console.log("Redoing action:", lastUndone);
    undoStack.push(lastUndone);

    // --- Przywracanie statystyk dla REDO ---
    if (lastUndone.redoStatsSnapshot) {
        restoreStatsSnapshot(lastUndone.redoStatsSnapshot);
    }

    if (lastUndone.type === "updateScore") {
        currentBreak = lastUndone.newBreak;
        updateBreakDisplay();

        if (lastUndone.wasFreeBall) {
            isFreeBall = false;
        }
    }

    switch (lastUndone.type) {
        case "updateActivePlayer":
            gameState.activePlayer = parseInt(lastUndone.playerId, 10);
            activePlayer = gameState.activePlayer;

            document.querySelectorAll(".set-active-player").forEach(button => {
                button.classList.remove("active");
            });
            const activeButton = document.querySelector(`.set-active-player[data-player="${gameState.activePlayer}"]`);
            if (activeButton) {
                activeButton.classList.add("active");
            }

            const playerHeaders = document.querySelectorAll("h4");
            playerHeaders.forEach(header => {
                header.innerHTML = header.innerHTML.replace(" 🔴", "");
            });
            if (gameState.activePlayer === 1) {
                playerHeaders[0].innerHTML += " 🔴";
            } else if (gameState.activePlayer === 2) {
                playerHeaders[1].innerHTML += " 🔴";
            }

            if (lastUndone.ballsVisibility) {
                restoreBallsVisibilityState(lastUndone.ballsVisibility);
            }

            if (lastUndone.pointsOnTable) {
                document.getElementById("points-on-table").textContent = lastUndone.pointsOnTable;
            }
            if (lastUndone.redBallCount !== undefined) {
                document.getElementById("red-ball-count").textContent = lastUndone.redBallCount;
                updateRedBallsUI(lastUndone.redBallCount);
            }
            break;

        case "updateScore":
            const playerScoreInput = document.querySelector(
                `.player-score[data-player="${lastUndone.playerId}"]`
            );
            if (playerScoreInput) {
                playerScoreInput.value = lastUndone.newScore;
            }

            if (lastUndone.redBallsChange) {
                const redBallsElement = document.getElementById("red-ball-count");
                if (redBallsElement) {
                    redBallsElement.textContent = lastUndone.newRedBalls;
                    updateRedBallsUI(lastUndone.newRedBalls);
                }
            }

            const pointsOnTableElement = document.getElementById("points-on-table");
            if (pointsOnTableElement) {
                pointsOnTableElement.textContent = lastUndone.newPointsOnTable;
                hideColorBallBasedOnPoints(lastUndone.newPointsOnTable);
            }

            if (lastUndone.ballsVisibility) {
                restoreBallsVisibilityState(lastUndone.ballsVisibility);
            }

            gameState.lastPottedRed = lastUndone.lastPottedRed || false;
            gameState.redBallsPottedThisTurn = lastUndone.redBallsPottedThisTurn || 0;
            break;

        case "foul":
            const opponentScoreElement = document.querySelector(
                `.player-score[data-player="${lastUndone.opponentId}"]`
            );
            if (opponentScoreElement) {
                opponentScoreElement.value = lastUndone.newOpponentScore;
            }

            if (lastUndone.redBallsChange) {
                const redBallsElement = document.getElementById("red-ball-count");
                if (redBallsElement) {
                    redBallsElement.textContent = lastUndone.newRedBalls;
                    updateRedBallsUI(lastUndone.newRedBalls);
                }

                const pointsOnTableElement = document.getElementById("points-on-table");
                if (pointsOnTableElement) {
                    pointsOnTableElement.textContent = lastUndone.newPointsOnTable;
                    hideColorBallBasedOnPoints(lastUndone.newPointsOnTable);
                }
            }

            if (lastUndone.ballsVisibility) {
                restoreBallsVisibilityState(lastUndone.ballsVisibility);
            }

            if (lastUndone.setFreeBall) {
                isFreeBall = true;
            }
            break;
    }

    updateActionLogUI();
}

// --- ACTION LOG FUNCTIONS (HISTORY UI) ---
function getActionDescription(action) {
    let playerPrefix = "";
    // Check which player performed the action
    if (action.playerId) {
        playerPrefix = `<span class="badge bg-${action.playerId === 1 ? 'primary' : 'warning'} me-2">P${action.playerId}</span>`;
    } else if (action.type === 'switchActivePlayer' && action.previousPlayerId) {
        // Info badge for player switch
        playerPrefix = `<span class="badge bg-secondary me-2">Info</span>`;
    }

    switch (action.type) {
        case 'updateScore':
            const points = action.newScore - action.previousScore;
            let ballName = "Ball";

            // Ustawiamy styl kółka (wielkość 0.9em dopasuje się do czcionki)
            // margin-right: 5px robi mały odstęp od nazwy
            const ballStyle = 'width: 0.9em; height: 0.9em; display: inline-block; vertical-align: middle; border: 1px solid rgba(0,0,0,0.2); margin-right: 5px;';

            // Funkcja pomocnicza do tworzenia HTML-a kółka (tylko tutaj lokalnie)
            const dot = (color) => `<span class="rounded-circle" style="background-color: ${color}; ${ballStyle}"></span>`;

            // Przypisywanie bil
            if (points === 1) ballName = dot('#dc3545') + " Red";      // Czerwona
            else if (points === 2) ballName = dot('#ffc107') + " Yellow"; // Żółta
            else if (points === 3) ballName = dot('#198754') + " Green";  // Zielona
            else if (points === 4) ballName = dot('#795548') + " Brown";  // Brązowa
            else if (points === 5) ballName = dot('#0d6efd') + " Blue";   // Niebieska
            else if (points === 6) ballName = dot('#ff69b4') + " Pink";   // Różowa (HotPink)
            else if (points === 7) ballName = dot('#212529') + " Black";  // Czarna

            // Special case for Free Ball
            if (action.wasFreeBall) ballName += " (Free Ball)";

            return `${playerPrefix} <strong>${ballName}</strong> (+${points})`;

        case 'foul':
            const foulPts = action.newOpponentScore - action.previousOpponentScore;
            // opponentId is the one receiving points, so the other one fouled
            const foulerId = (action.opponentId === 1) ? 2 : 1;
            const foulerBadge = `<span class="badge bg-${foulerId === 1 ? 'primary' : 'warning'} me-2">P${foulerId}</span>`;
            return `${foulerBadge} ⚠️ <strong>FOUL</strong> (Gave ${foulPts} pts)`;

        case 'updateActivePlayer':
            return `${playerPrefix} 🔄 Switch Player`;

        default:
            // Attempt to detect Safety/Miss using stats snapshots (if available)
            if (action.statsSnapshot && action.redoStatsSnapshot) {
                if (action.redoStatsSnapshot.p1Misses > action.statsSnapshot.p1Misses ||
                    action.redoStatsSnapshot.p2Misses > action.statsSnapshot.p2Misses) {
                    return `${playerPrefix} ❌ Miss`;
                }
                if (action.redoStatsSnapshot.p1Safeties > action.statsSnapshot.p1Safeties ||
                    action.redoStatsSnapshot.p2Safeties > action.statsSnapshot.p2Safeties) {
                    return `${playerPrefix} 🛡️ Safety`;
                }
            }
            return `${playerPrefix} Other action`;
    }
}

function updateActionLogUI() {
    const listElement = document.getElementById('actionLogList');
    if (!listElement) return;

    listElement.innerHTML = ''; // Czyścimy listę

    // Bierzemy kopię undoStack
    // slice(-10) bierze 10 ostatnich, reverse() odwraca kolejność (najnowsze na górze)
    const recentActions = undoStack.slice(-10).reverse();

    if (recentActions.length === 0) {
        listElement.innerHTML = '<li class="list-group-item text-muted">Brak akcji w historii.</li>';
        return;
    }

    recentActions.forEach(action => {
        const li = document.createElement('li');
        li.className = 'list-group-item d-flex align-items-center';
        li.innerHTML = getActionDescription(action);
        listElement.appendChild(li);
    });
}

function updateRedBallsUI(redBalls) {
    const redButton = document.querySelector('.btn-danger[aria-label="Red"]');
    const redBallContainer = document.getElementById("red-ball-count").closest('.rounded-circle');

    if (parseInt(redBalls) === 0) {
        if (redButton) redButton.style.display = "none";
        if (redBallContainer) redBallContainer.style.display = "none";
    } else {
        if (redButton) redButton.style.display = "inline-block";
        if (redBallContainer) redBallContainer.style.display = "flex";
    }
}

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

function endFrame() {
    pauseTimer();

    const p1ScoreInput = document.querySelector(`.player-score[data-player="1"]`);
    const p2ScoreInput = document.querySelector(`.player-score[data-player="2"]`);
    const p1Score = parseInt(p1ScoreInput ? p1ScoreInput.value : 0, 10);
    const p2Score = parseInt(p2ScoreInput ? p2ScoreInput.value : 0, 10);

    const btnP1 = document.getElementById('btn-win-p1');
    const btnP2 = document.getElementById('btn-win-p2');

    if (btnP1 && btnP2) {
        btnP1.className = 'btn btn-outline-secondary btn-lg p-4';
        btnP2.className = 'btn btn-outline-secondary btn-lg p-4';

        if (p1Score > p2Score) {
            btnP1.classList.remove('btn-outline-secondary');
            btnP1.classList.add('btn-success');
        } else if (p2Score > p1Score) {
            btnP2.classList.remove('btn-outline-secondary');
            btnP2.classList.add('btn-success');
        }
    }

    // BS5: Otwieranie modala bez jQuery
    const modalEl = document.getElementById('endFrameModal');
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
}

function resetGame() {
    pauseTimer();
    elapsedSeconds = 0;
    document.getElementById("match-timer").textContent = formatTime(elapsedSeconds);

    // --- START NEW CODE ---
    // Reset foul statistics for the new frame
    p1Fouls = 0;
    p2Fouls = 0;
    p1FoulPoints = 0;
    p2FoulPoints = 0;

    p1Shots = 0;
    p1Misses = 0;
    p1Pots = 0;
    p2Shots = 0;
    p2Misses = 0;
    p2Pots = 0;

    p1Safeties = 0;
    p1SuccessfulSafeties = 0;
    p2Safeties = 0;
    p2SuccessfulSafeties = 0;
    pendingSafetyCheck = false;
    safetyPlayerId = null;

    p1BreaksHistory = [];
    p2BreaksHistory = [];

    resetScores();
    activePlayer = null;
    isFreeBall = false;
    lastShotWasFreeBall = false;

    document.querySelectorAll("h4").forEach(header => {
        header.innerHTML = header.innerHTML.replace(" 🔴", "");
    });
    document.querySelectorAll(".set-active-player").forEach(button => {
        button.classList.remove("active");
    });

    resetRedBalls();
    resetPointsOnTable();
    resetBreak();

    document.querySelectorAll('.btn, .rounded-circle').forEach(element => {
        element.style.display = "inline-block";
    });
    updateActionLogUI();
}

function setActivePlayer(playerId) {
    activePlayer = playerId;
    updateActivePlayerUI(playerId);
}

function updateActivePlayerUI(playerId) {
    const previousActivePlayer = document.querySelector('.set-active-player.active')?.dataset.player;

    recordAction({
        type: 'updateActivePlayer',
        playerId: playerId,
        previousPlayerId: previousActivePlayer || null,
    });

    document.querySelectorAll(".set-active-player").forEach(button => {
        button.classList.remove("active");
    });

    const activeButton = document.querySelector(`.set-active-player[data-player="${playerId}"]`);
    if (activeButton) {
        activeButton.classList.add("active");
    }

    const playerHeaders = document.querySelectorAll("h4");

    playerHeaders.forEach(header => {
        header.innerHTML = header.innerHTML.replace(" 🔴", "");
    });

    if (playerId === 1) {
        playerHeaders[0].innerHTML += " 🔴";
    } else if (playerId === 2) {
        playerHeaders[1].innerHTML += " 🔴";
    }
}

function updateScore(points, ballType) {
    if (activePlayer === null) {
        alert("Please select an active player first!");
        return;
    }

    // --- SPRAWDZAMY POPRZEDNIĄ ODSTAWNĄ ---
    // Przekazujemy true, bo nastąpiło wbicie (czyli safety nieudane)
    resolvePendingSafety(true);
    // --------------------------------------

    // --- START NEW CODE (Liczenie Wbić) ---
    // Każde wywołanie updateScore to udane wbicie
    if (activePlayer === 1) {
        p1Shots++; // Oddał strzał
        p1Pots++;  // I trafił
    } else {
        p2Shots++;
        p2Pots++;
    }

    // --- 1. LOGIKA FREE BALL ---
    let actualPoints = points;
    let effectiveBallType = ballType;
    let wasFreeBallShot = false;

    if (isFreeBall && ballType === 'color') {
        actualPoints = 1;
        effectiveBallType = 'red';
        wasFreeBallShot = true;
    }

    // --- 2. BEZPIECZNE POBIERANIE INPUTA WYNIKU (POPRAWKA) ---
    // Zamiast closest(), używamy konkretnego selektora, który na 100% zadziała
    const playerScoreInput = document.querySelector(`.player-score[data-player="${activePlayer}"]`);

    if (!playerScoreInput) {
        console.error("Critical Error: Score input not found for player " + activePlayer);
        return;
    }

    const previousScore = parseInt(playerScoreInput.value, 10) || 0;
    const newScore = previousScore + actualPoints;

    currentBreak += actualPoints;
    updateBreakDisplay();

    const previousRedBalls = parseInt(document.getElementById("red-ball-count").textContent, 10);
    const previousPointsOnTable = parseInt(document.getElementById("points-on-table").textContent, 10);

    // --- 3. LOGIKA HISTORII (UNDO) ---
    let pointsToRemoveFromTable = 0;
    if (effectiveBallType === 'red' && !wasFreeBallShot) {
        pointsToRemoveFromTable = 8;
    }

    // Zabezpieczenie na wypadek, gdyby zmienna nie była zdefiniowana
    const safeLastShotWasFreeBall = (typeof lastShotWasFreeBall !== 'undefined') ? lastShotWasFreeBall : false;

    recordAction({
        type: "updateScore",
        playerId: activePlayer,
        previousScore: previousScore,
        newScore: newScore,
        ballType: ballType,
        redBallsChange: (effectiveBallType === 'red' && !wasFreeBallShot),
        previousRedBalls: previousRedBalls,
        previousPointsOnTable: previousPointsOnTable,
        newPointsOnTable: previousPointsOnTable - pointsToRemoveFromTable,
        previousBreak: currentBreak - actualPoints,
        newBreak: currentBreak,
        wasFreeBall: wasFreeBallShot,
        previousLastShotWasFreeBall: safeLastShotWasFreeBall
    });

    // --- 4. AKTUALIZACJA UI ---
    playerScoreInput.value = newScore;

    // --- 5. LOGIKA STOŁU I CZERWONYCH ---
    if (effectiveBallType === 'red') {
        for (let i = 0; i < actualPoints; i++) {
            redBallsPottedThisTurn++;

            // Jeśli to zwykła czerwona (nie free ball) -> Zdejmujemy ze stołu
            if (!wasFreeBallShot) {
                updateRedBalls(1);
                updatePointsOnTable(1);
            }

            if (redBallsPottedThisTurn > 1 && !wasFreeBallShot) {
                updatePointsOnTable(7);
            }
        }
        lastPottedRed = true;

        // Ustawiamy flagę globalną
        lastShotWasFreeBall = wasFreeBallShot;

    } else if (ballType === 'color') {
        if (lastPottedRed) {
            // Jeśli to kolor po czerwonej (i poprzedni to nie był Free Ball), zdejmujemy 7 pkt
            if (!safeLastShotWasFreeBall) {
                updatePointsOnTable(7);
            }
            lastShotWasFreeBall = false;
        } else {
            // Koniec gry na kolorach
            updatePointsOnTable(points);
        }
        lastPottedRed = false;
        redBallsPottedThisTurn = 0;
    }

    // --- 6. UKRYWANIE BIL ---
    const currentPointsOnTable = parseInt(document.getElementById("points-on-table").textContent, 10);
    hideColorBallBasedOnPoints(currentPointsOnTable);

    if (currentPointsOnTable <= 27) {
        showColorBalls();
        hideColorBallBasedOnPoints(currentPointsOnTable);
    }

    // --- 7. RESET TRYBU FREE BALL ---
    if (isFreeBall) {
        isFreeBall = false;
    }
}

function resolvePendingSafety(opponentPottedBall) {
    if (pendingSafetyCheck && safetyPlayerId !== null) {

        // Logika: Jeśli przeciwnik NIE wbił bili (opponentPottedBall == false),
        // to znaczy, że odstawna była SUKCESEM.

        if (!opponentPottedBall) {
            if (safetyPlayerId === 1) {
                p1SuccessfulSafeties++;
                console.log("Safety Resolution: Player 1 -> SUCCESS");
            } else {
                p2SuccessfulSafeties++;
                console.log("Safety Resolution: Player 2 -> SUCCESS");
            }
        } else {
            console.log("Safety Resolution: Player " + safetyPlayerId + " -> FAILED (Opponent potted)");
        }

        // Resetujemy pamięć
        pendingSafetyCheck = false;
        safetyPlayerId = null;
    }
}

function resetBreak() {
    currentBreak = 0;

    document.querySelectorAll(".break-container").forEach(container => {
        container.style.display = "none";
    });
    document.querySelectorAll(".player-break").forEach(span => span.textContent = "0");
}

function updateBreakDisplay() {

    document.querySelectorAll(".break-container").forEach(container => {
        const player = parseInt(container.getAttribute("data-player"), 10);

        if (player === activePlayer && currentBreak > 0) {
            container.style.display = "inline";
        } else {
            container.style.display = "none";
        }
    });

    const breakSpan = document.querySelector(`.player-break[data-player="${activePlayer}"]`);
    if (breakSpan) {
        breakSpan.textContent = currentBreak;
    }
}

function hideColorBallBasedOnPoints(pointsOnTable) {
    if (pointsOnTable <= 25) {
        hideColorBall('yellow');
    }
    if (pointsOnTable <= 22) {
        hideColorBall('green');
    }
    if (pointsOnTable <= 18) {
        hideColorBall('brown');
    }
    if (pointsOnTable <= 13) {
        hideColorBall('blue');
    }
    if (pointsOnTable <= 7) {
        hideColorBall('pink');
    }
    if (pointsOnTable === 0) {
        hideColorBall('black');
    }

    hideBallIconBasedOnPoints(pointsOnTable);
}

function hideBallIconBasedOnPoints(pointsOnTable) {
    if (pointsOnTable <= 25) {
        hideBallIcon('yellow');
    }
    if (pointsOnTable <= 22) {
        hideBallIcon('green');
    }
    if (pointsOnTable <= 18) {
        hideBallIcon('brown');
    }
    if (pointsOnTable <= 13) {
        hideBallIcon('blue');
    }
    if (pointsOnTable <= 7) {
        hideBallIcon('pink');
    }
    if (pointsOnTable === 0) {
        hideBallIcon('black');
    }
}

function hideBallIcon(color) {
    const iconElement = document.querySelector(`.rounded-circle.color-ball-marker[data-type="${color}"]`);
    if (iconElement) {
        iconElement.style.display = "none";
    }
}

function hideColorBall(color) {
    const ballElement = document.querySelector(`.color-ball[data-type="${color}"]`);
    if (ballElement) {
        ballElement.classList.add('potted');
        ballElement.style.display = "none";
    }
}

function showColorBalls() {
    const colorBalls = document.querySelectorAll('.color-ball');
    colorBalls.forEach(ball => {
        if (!ball.classList.contains('potted')) {
            ball.style.display = "inline-block";
        }
    });
}

function getBallsVisibilityState() {
    const state = {
        colorBalls: {},
        ballIcons: {},
        redBalls: {
            display: document.getElementById("red-ball-count").closest('.rounded-circle').style.display,
            count: document.getElementById("red-ball-count").textContent
        }
    };

    document.querySelectorAll('.color-ball').forEach(ball => {
        const color = ball.dataset.type;
        state.colorBalls[color] = {
            display: ball.style.display,
            isPotted: ball.classList.contains('potted')
        };
    });

    document.querySelectorAll('.rounded-circle.color-ball-marker').forEach(icon => {
        const color = icon.dataset.type;
        state.ballIcons[color] = {
            display: icon.style.display
        };
    });

    return state;
}

function restoreBallsVisibilityState(state) {
    Object.entries(state.colorBalls).forEach(([color, props]) => {
        const ball = document.querySelector(`.color-ball[data-type="${color}"]`);
        if (ball) {
            ball.style.display = props.display;
            if (props.isPotted) {
                ball.classList.add('potted');
            } else {
                ball.classList.remove('potted');
            }
        }
    });

    Object.entries(state.ballIcons).forEach(([color, props]) => {
        const icon = document.querySelector(`.rounded-circle.color-ball-marker[data-type="${color}"]`);
        if (icon) {
            icon.style.display = props.display;
        }
    });

    if (state.redBalls) {
        const redBallsElement = document.getElementById("red-ball-count");
        redBallsElement.textContent = state.redBalls.count;
        const redBallContainer = redBallsElement.closest('.rounded-circle');
        redBallContainer.style.display = state.redBalls.display;

        const redButton = document.querySelector('.btn-danger[aria-label="Red"]');
        if (redButton) {
            redButton.style.display = state.redBalls.count === "0" ? "none" : "inline-block";
        }
    }
}

function miss() {
    if (activePlayer === null) {
        alert("Please select an active player first!");
        return;
    }

    // --- SPRAWDZAMY POPRZEDNIĄ ODSTAWNĄ ---
    // Przekazujemy false, bo nie wbito bili (czyli safety udane)
    resolvePendingSafety(false);
    // --------------------------------------

    // Liczenie Pudeł
    if (activePlayer === 1) {
        p1Shots++;  // Oddał strzał
        p1Misses++; // Ale spudłował
    } else {
        p2Shots++;
        p2Misses++;
    }

    if (lastPottedRed) {
        updatePointsOnTable(7);
    }

    redBallsPottedThisTurn = 0;
    lastPottedRed = false;
    switchActivePlayer();
}

function safetyShot() {
    if (activePlayer === null) {
        alert("Please select an active player first!");
        return;
    }

    // 1. Jeśli poprzednik robił safety, a ja też robię safety,
    // to jego safety było DOBRE (bo nie dał mi wbić).
    resolvePendingSafety(false);

    // 2. Aktualizacja statystyk ogólnych
    if (activePlayer === 1) {
        p1Shots++;
        p1Safeties++;
    } else {
        p2Shots++;
        p2Safeties++;
    }

    // 3. USTAWIAMY FLAGĘ NA PRZYSZŁOŚĆ
    // Teraz to moja odstawna będzie oceniana w następnym ruchu
    pendingSafetyCheck = true;
    safetyPlayerId = activePlayer;
    console.log("Safety set by Player " + activePlayer + ". Waiting for opponent...");

    if (lastPottedRed) {
        updatePointsOnTable(7);
    }

    redBallsPottedThisTurn = 0;
    lastPottedRed = false;
    switchActivePlayer();
}

function switchActivePlayer() {
    if (activePlayer === null) {
        alert("No active player to switch!");
        return;
    }

    // --- 1. AST LOGIC: CALCULATE & SEND DATA ---
    const now = Date.now();
    const timeSpentSeconds = (now - turnStartTime) / 1000;

    // Zapamiętujemy, KTO schodzi ze stołu (to jego statystyki zapisujemy)
    const playerLeaving = activePlayer;

    // Wysyłamy do bazy tylko, jeśli faktycznie coś grał (czas > 1s lub oddał strzał)
    if (timeSpentSeconds > 1 || currentTurnShots > 0) {

        // Pobieramy ID frame'a z HTML (upewnij się, że masz to w HTML-u, jak ustalaliśmy wcześniej)
        const frameContainer = document.querySelector('.container[data-frame-id]');

        if (frameContainer) {
            const frameId = frameContainer.dataset.frameId;

            fetch('/update_player_stats/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    frame_id: frameId,
                    player_id: playerLeaving,
                    added_shots: currentTurnShots,
                    added_time_seconds: timeSpentSeconds
                })
            })
            .then(response => response.json())
            .then(data => console.log('AST Stats saved:', data))
            .catch(error => console.error('Error saving stats:', error));
        } else {
            console.warn("Frame ID not found via data-frame-id attribute");
        }
    }

    // --- 2. AST LOGIC: RESET FOR NEXT PLAYER ---
    turnStartTime = Date.now(); // Resetujemy stoper dla nowego gracza
    currentTurnShots = 0;       // Resetujemy licznik uderzeń dla nowego gracza


    // --- 3. EXISTING LOGIC (BREAKS HISTORY) ---
    // Jeśli break był znaczący (>= 10), zapisujemy go do historii gracza
    if (currentBreak >= 10) {
        if (activePlayer === 1) {
            p1BreaksHistory.push(currentBreak);
        } else {
            p2BreaksHistory.push(currentBreak);
        }
        console.log(`Break saved for Player ${activePlayer}: ${currentBreak}`);
    }

    // --- 4. EXISTING LOGIC (RESET TURN FLAGS) ---
    lastPottedRed = false;
    redBallsPottedThisTurn = 0;
    lastShowWasFreeBall = false;
    resetBreak();

    // --- 5. SWITCH PLAYER ---
    activePlayer = activePlayer === 1 ? 2 : 1;
    updateActivePlayerUI(activePlayer);
}

function showFoulModal() {
    // BS5: Otwieranie modala faulu
    const foulModal = new bootstrap.Modal(document.getElementById('foulModal'));
    foulModal.show();

    foulPoints = 0;
    nextPlayerId = null;
    redBallAdjustment = 0;

    document.getElementById('freeBallCheckbox').checked = false;
    document.querySelectorAll('.foul-points').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.next-player').forEach(btn => btn.classList.remove('active'));
    document.getElementById('redBallAdjustment').value = 0;
}

// Helper function for CSRF token (if you don't have it already)
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

document.getElementById('redBallAdjustment').addEventListener('input', (e) => {
    const value = parseInt(e.target.value, 10);
    redBallAdjustment = isNaN(value) ? 0 : Math.max(0, Math.min(value, 15));
});

document.getElementById('decreaseRedBalls').addEventListener('click', () => {
    const input = document.getElementById('redBallAdjustment');
    redBallAdjustment = Math.max((parseInt(input.value, 10) || 0) -1, 0);
    input.value = redBallAdjustment;
});

document.getElementById('increaseRedBalls').addEventListener('click', () => {
    const input = document.getElementById('redBallAdjustment');
    redBallAdjustment = Math.min((parseInt(input.value, 10) || 0) + 1, 15);
    input.value = redBallAdjustment;
});

document.getElementById('confirmFoul').addEventListener('click', () => {
    if (foulPoints > 0 && nextPlayerId !== null) {

        // --- SPRAWDZAMY POPRZEDNIĄ ODSTAWNĄ ---
        // Faul przeciwnika to sukces odstawnej (wymuszenie błędu)
        resolvePendingSafety(false);
        // --------------------------------------

        // --- START NEW CODE ---
        // Update Foul Statistics
        if (activePlayer === 1) {
            p1Fouls++;
            p1FoulPoints += foulPoints;
        } else {
            p2Fouls++;
            p2FoulPoints += foulPoints;
        }
        // --- END NEW CODE ---

        const opponentId = activePlayer === 1 ? 2 : 1;
        const opponentScoreElement = document.querySelector(`.player-score[data-player="${opponentId}"]`);
        const previousOpponentScore = parseInt(opponentScoreElement.value || '0', 10);
        const previousRedBalls = parseInt(document.getElementById("red-ball-count").textContent, 10);
        const previousPointsOnTable = parseInt(document.getElementById("points-on-table").textContent, 10);

        // Pobieramy stan checkboxa
        const isFreeBallSelected = document.getElementById('freeBallCheckbox').checked;

        // Zapisujemy obecny break ZANIM go wyzerujemy
        const breakBeforeFoul = currentBreak;

        recordAction({
            type: "foul",
            opponentId: opponentId,
            previousOpponentScore: previousOpponentScore,
            newOpponentScore: previousOpponentScore + foulPoints,
            redBallsChange: redBallAdjustment > 0,
            previousRedBalls: previousRedBalls,
            newRedBalls: previousRedBalls - redBallAdjustment,
            previousPointsOnTable: previousPointsOnTable,
            newPointsOnTable: previousPointsOnTable - (redBallAdjustment * 8),
            setFreeBall: isFreeBallSelected,   // <--- Ważne: tu musi być przecinek
            previousBreak: breakBeforeFoul     // <--- To jest ta nowa linijka
        });

        opponentScoreElement.value = previousOpponentScore + foulPoints;

        if (redBallAdjustment > 0) {
            updateRedBalls(redBallAdjustment);
            updatePointsOnTableForReds(redBallAdjustment);
        }

        if (lastPottedRed) {
            updatePointsOnTable(7);
            lastPottedRed = false;
        }

        redBallsPottedThisTurn = 0;
        lastPottedRed = false;

        // Ustawiamy flagę
        isFreeBall = isFreeBallSelected;

        // Zerujemy breaka (bo zmiana gracza)
        currentBreak = 0;
        updateBreakDisplay();

        setActivePlayer(nextPlayerId);

        const foulModalEl = document.getElementById('foulModal');
        const foulModal = bootstrap.Modal.getInstance(foulModalEl) || new bootstrap.Modal(foulModalEl);
        foulModal.hide();

    } else {
        alert("Please select foul points and the next player.");
    }
});

function updateRedBalls(points) {
    const redBallsElement = document.getElementById("red-ball-count");
    const redBallContainer = redBallsElement.closest('.rounded-circle');
    const redButton = document.querySelector('.btn-danger[aria-label="Red"]');

    if (redBallsElement) {
        const currentRedBalls = parseInt(redBallsElement.textContent, 10) || 0;
        const newRedBallsCount = Math.max(currentRedBalls - points, 0);
        redBallsElement.textContent = newRedBallsCount;

        if (newRedBallsCount === 0) {
            if (redBallContainer) redBallContainer.style.display = "none";
            if (redButton) redButton.style.display = "none";
        }
    }
}

function updatePointsOnTable(points) {
    const pointsOnTableElement = document.getElementById("points-on-table");
    if (pointsOnTableElement) {
        const currentPoints = parseInt(pointsOnTableElement.textContent, 10) || 0;
        const newPoints = Math.max(currentPoints - points, 0);
        pointsOnTableElement.textContent = newPoints;
    }
}

function updatePointsOnTableForReds(redBallCount) {
    const pointsOnTableElement = document.getElementById("points-on-table");
    if (pointsOnTableElement) {
        const currentPoints = parseInt(pointsOnTableElement.textContent, 10) || 0;
        const pointsToSubtract = redBallCount * 8;
        const newPointsAfterFoul = Math.max(currentPoints - pointsToSubtract, 0);
        pointsOnTableElement.textContent = newPointsAfterFoul;
    }
}

function resetRedBalls() {
    const redBallsElement = document.getElementById("red-ball-count");
    const redBallContainer = redBallsElement.closest('.rounded-circle');
    const redButton = document.querySelector('.btn-danger[aria-label="Red"]');

    if (redBallsElement) {
        redBallsElement.textContent = 15;
    }

    if (redBallContainer) {
        redBallContainer.style.display = "flex";
    }

    if (redButton) {
        redButton.style.display = "inline-block";
    }
}

function resetPointsOnTable() {
    const pointsOnTableElement = document.getElementById("points-on-table");
    if (pointsOnTableElement) {
        pointsOnTableElement.textContent = 147;
    }
}

function confirmFrameWinner(winnerId) {
    pendingWinnerId = winnerId;

    // BS5: Zamykamy pierwszy modal
    // Musimy znaleźć istniejącą instancję (lub stworzyć nową, żeby móc wywołać hide)
    const endModalEl = document.getElementById('endFrameModal');
    const endModal = bootstrap.Modal.getInstance(endModalEl) || new bootstrap.Modal(endModalEl);
    endModal.hide();

    const playerNameSpan = document.getElementById('confirmation-player-name');
    if (playerNameSpan) {
        playerNameSpan.textContent = `Player ${winnerId}`;
    }

    // BS5: Otwieramy drugi modal
    const confirmModal = new bootstrap.Modal(document.getElementById('confirmWinnerModal'));
    confirmModal.show();
}

function finalizeFrameEnd() {
    // BS5: Zamykamy modal potwierdzenia
    const confirmModalEl = document.getElementById('confirmWinnerModal');
    const confirmModal = bootstrap.Modal.getInstance(confirmModalEl) || new bootstrap.Modal(confirmModalEl);
    confirmModal.hide();

    if (pendingWinnerId === null) return;

    const winnerPosition = pendingWinnerId;
    const p1ScoreInput = document.querySelector(`.player-score[data-player="1"]`);
    const p2ScoreInput = document.querySelector(`.player-score[data-player="2"]`);
    const p1Score = parseInt(p1ScoreInput ? p1ScoreInput.value : 0, 10);
    const p2Score = parseInt(p2ScoreInput ? p2ScoreInput.value : 0, 10);
    const duration = (typeof elapsedSeconds !== 'undefined') ? elapsedSeconds : 0;

    if (currentBreak >= 10 && activePlayer !== null) {
        if (activePlayer === 1) p1BreaksHistory.push(currentBreak);
        else if (activePlayer === 2) p2BreaksHistory.push(currentBreak);
    }

    fetch('/save_frame_result/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            match_id: matchId,
            winner_id: (winnerPosition == 1) ? player1Id : player2Id,
            p1_score: p1Score,
            p2_score: p2Score,
            duration: duration,
            p1_fouls: p1Fouls, p2_fouls: p2Fouls,
            p1_foul_pts: p1FoulPoints, p2_foul_pts: p2FoulPoints,
            p1_shots: p1Shots, p1_misses: p1Misses, p1_pots: p1Pots,
            p2_shots: p2Shots, p2_misses: p2Misses, p2_pots: p2Pots,
            p1_safeties: p1Safeties, p2_safeties: p2Safeties,
            p1_safe_success_count: p1SuccessfulSafeties, p2_safe_success_count: p2SuccessfulSafeties,
            p1_breaks: p1BreaksHistory, p2_breaks: p2BreaksHistory
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            console.log("Frame saved successfully!");
            updateVisualsAndReset(winnerPosition);
            if (data.match_over) {
                setTimeout(() => {
                    alert(`MATCH OVER! Winner: ${data.match_winner} 🏆`);
                    isUnsafeToLeave = false;
                    window.location.href = `/match/${matchId}/`;
                }, 500);
            }
        } else {
            alert("Error saving frame: " + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert("Server communication error.");
    });

    pendingWinnerId = null;
}

// Funkcja pomocnicza do czyszczenia stołu (stary kod przeniesiony tutaj)
function updateVisualsAndReset(winnerPosition) {
    undoStack = [];
    redoStack = [];

    const winnerFrameInput = document.getElementById(`player${winnerPosition}-frames`);
    if (winnerFrameInput) {
        let currentFrames = parseInt(winnerFrameInput.value, 10) || 0;
        winnerFrameInput.value = currentFrames + 1;
    }

    resetGame();
    elapsedSeconds = 0;
    const timerDisplay = document.getElementById("match-timer");
    if (timerDisplay) {
        timerDisplay.textContent = (typeof formatTime === 'function') ? formatTime(elapsedSeconds) : "00:00:00";
    }
}

// --- FUNKCJE POMOCNICZE DO UNDO/REDO STATYSTYK ---

function getStatsSnapshot() {
    return {
        // Podstawowe liczniki
        p1Fouls: p1Fouls, p2Fouls: p2Fouls,
        p1FoulPoints: p1FoulPoints, p2FoulPoints: p2FoulPoints,
        p1Shots: p1Shots, p2Shots: p2Shots,
        p1Misses: p1Misses, p2Misses: p2Misses,
        p1Pots: p1Pots, p2Pots: p2Pots,

        // Safety
        p1Safeties: p1Safeties, p2Safeties: p2Safeties,
        p1SuccessfulSafeties: p1SuccessfulSafeties, p2SuccessfulSafeties: p2SuccessfulSafeties,
        pendingSafetyCheck: pendingSafetyCheck,
        safetyPlayerId: safetyPlayerId,

        // Tablice breaków (ważne: robimy kopię przez [...])
        p1BreaksHistory: [...p1BreaksHistory],
        p2BreaksHistory: [...p2BreaksHistory]
    };
}

function restoreStatsSnapshot(snapshot) {
    if (!snapshot) return;

    p1Fouls = snapshot.p1Fouls; p2Fouls = snapshot.p2Fouls;
    p1FoulPoints = snapshot.p1FoulPoints; p2FoulPoints = snapshot.p2FoulPoints;
    p1Shots = snapshot.p1Shots; p2Shots = snapshot.p2Shots;
    p1Misses = snapshot.p1Misses; p2Misses = snapshot.p2Misses;
    p1Pots = snapshot.p1Pots; p2Pots = snapshot.p2Pots;

    p1Safeties = snapshot.p1Safeties; p2Safeties = snapshot.p2Safeties;
    p1SuccessfulSafeties = snapshot.p1SuccessfulSafeties; p2SuccessfulSafeties = snapshot.p2SuccessfulSafeties;
    pendingSafetyCheck = snapshot.pendingSafetyCheck;
    safetyPlayerId = snapshot.safetyPlayerId;

    // Przywracamy tablice
    p1BreaksHistory = snapshot.p1BreaksHistory;
    p2BreaksHistory = snapshot.p2BreaksHistory;
}

document.querySelectorAll('.set-active-player').forEach(button => {
    button.addEventListener('click', () => {
        const playerId = parseInt(button.dataset.player, 10);
        setActivePlayer(playerId);
    });
});

document.getElementById('undoButton').addEventListener('click', () => {
    undo();
});

document.getElementById('redoButton').addEventListener('click', () => {
    redo();
});

/* =========================================
   SIDEBAR HISTORY LOGIC (Dla Bootstrap 4)
   ========================================= */
document.addEventListener('DOMContentLoaded', () => {
    const historyBtn = document.getElementById('history-btn');
    const closeSidebarBtn = document.getElementById('closeSidebarBtn');
    const sidebar = document.getElementById('historySidebar');
    const backdrop = document.getElementById('sidebarBackdrop');

    // Funkcja przełączająca widoczność
    function toggleSidebar() {
        if (sidebar && backdrop) {
            sidebar.classList.toggle('active');
            backdrop.classList.toggle('active');
        }
    }

    // Otwieranie (kliknięcie w przycisk History w panelu)
    if (historyBtn) {
        historyBtn.addEventListener('click', (e) => {
            e.preventDefault();
            toggleSidebar();
        });
    }

    // Zamykanie (kliknięcie w przycisk Zamknij w panelu)
    if (closeSidebarBtn) {
        closeSidebarBtn.addEventListener('click', (e) => {
            e.preventDefault();
            toggleSidebar();
        });
    }

    // Zamykanie (kliknięcie w ciemne tło poza panelem)
    if (backdrop) {
        backdrop.addEventListener('click', (e) => {
            e.preventDefault();
            toggleSidebar();
        });
    }
});

// --- WARNING BEFORE LEAVING ---
window.addEventListener('beforeunload', function (e) {
    if (isUnsafeToLeave) {
        e.preventDefault();
        e.returnValue = '';
    }
});

resetBreak();
