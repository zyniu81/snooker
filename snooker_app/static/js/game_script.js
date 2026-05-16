// --- BILL STATISTICS (Detailed) ---
// Default counter set
const initialBallCounts = {
    red: 0, yellow: 0, green: 0, brown: 0, blue: 0, pink: 0, black: 0
};

// We copy this set for players 1 and 2
// (We use { ... } to create a copy, not a reference)
let p1BallCounts = { ...initialBallCounts };
let p2BallCounts = { ...initialBallCounts };

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
let pendingWinnerId = null; // Temporary variable to store the selected winner
// --- STATISTICS VARIABLES ---
let p1Fouls = 0;        // Number of fouls for Player 1
let p2Fouls = 0;        // Number of fouls for Player 2
let p1FoulPoints = 0;   // Points given by Player 1 (via fouls)
let p2FoulPoints = 0;   // Points given by Player 2 (via fouls)

let p1Shots = 0;   // Total shots attempted
let p1Misses = 0;  // Number of misses
let p1Pots = 0;    // Number of balls potted

let p2Shots = 0;
let p2Misses = 0;
let p2Pots = 0;

let p1Safeties = 0;           // Total safety attempts
let p1SuccessfulSafeties = 0; // Successful safeties only (when opponent didn't pot)

let p2Safeties = 0;
let p2SuccessfulSafeties = 0;

// MEMORY (State)
let pendingSafetyCheck = false; // Are we waiting for a safety check?
let safetyPlayerId = null;      // Who played the safety (1 or 2)?

// HISTORIA BREAKÓW (Tablice)
let p1BreaksHistory = [];
let p2BreaksHistory = [];

// --- AST TRACKING ---
let turnStartTime = Date.now();
let currentTurnShots = 0; // Counts shots ONLY for the current visit to the table

let isUnsafeToLeave = true;
let isStatsVisible = false;


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

        //--- WE SAVE STATISTICS ---
        statsSnapshot: getStatsSnapshot()
    };

    console.log(actionWithState);
    undoStack.push(actionWithState);
    redoStack = [];

    updateActionLogUI();

    // --- UPDATE MAX POSSIBLE BREAK ---
    updateMaxPossibleBreak();
}

function undo() {
    if (undoStack.length === 0) return;

    const lastAction = undoStack.pop();

    // --- Preparing data for REDO ---
    lastAction.redoStatsSnapshot = getStatsSnapshot();

    console.log("Undoing action:", lastAction);
    redoStack.push(lastAction);

    // --- Restoring Statistics ---
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
    updateBallStatsUI();
    updateFrameStatus();
    // --- UPDATE MAX POSSIBLE BREAK ---
    updateMaxPossibleBreak();
}

function redo() {
    if (redoStack.length === 0) return;

    const lastUndone = redoStack.pop();
    console.log("Redoing action:", lastUndone);
    undoStack.push(lastUndone);

    // --- Restoring statistics for REDO ---
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
    updateBallStatsUI();
    updateFrameStatus();
    // --- UPDATE MAX POSSIBLE BREAK ---
    updateMaxPossibleBreak();
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

            // Set the circle style (0.9em size will adjust to the font)
            // margin-right: 5px creates a small space around the name
            const ballStyle = 'width: 0.9em; height: 0.9em; display: inline-block; vertical-align: middle; border: 1px solid rgba(0,0,0,0.2); margin-right: 5px;';

            // Helper function to create the HTML circle (only locally here)
            const dot = (color) => `<span class="rounded-circle" style="background-color: ${color}; ${ballStyle}"></span>`;

            // Assigning balls
            if (points === 1) ballName = dot('#dc3545') + " Red";      // Red
            else if (points === 2) ballName = dot('#ffc107') + " Yellow"; // Yellow
            else if (points === 3) ballName = dot('#198754') + " Green";  // Green
            else if (points === 4) ballName = dot('#795548') + " Brown";  // Brown
            else if (points === 5) ballName = dot('#0d6efd') + " Blue";   // Blue
            else if (points === 6) ballName = dot('#ff69b4') + " Pink";   // Pink
            else if (points === 7) ballName = dot('#212529') + " Black";  // Black

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

    listElement.innerHTML = ''; // We are clearing the list

    // Take a copy of undoStack
    // slice(-10) takes the last 10, reverse() reverses the order (newest on top)
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

            if (typeof broadcastGameState === 'function') {
                broadcastGameState();
            }
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

    // BS5: Opening a modal without jQuery
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

    // Reset bill counters
    p1BallCounts = { ...initialBallCounts };
    p2BallCounts = { ...initialBallCounts };

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
    updateBallStatsUI();
    updateFrameStatus();
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

    updateFrameStatus();
}

function updateScore(points, ballType) {
    if (activePlayer === null) {
        alert("Please select an active player first!");
        return;
    }

    let currentCounts = (activePlayer === 1) ? p1BallCounts : p2BallCounts;

    // --- CHECKING THE PREVIOUS SAFETY ---
    resolvePendingSafety(true);
    // --------------------------------------

    // --- HIT STATISTICS ---
    if (activePlayer === 1) {
        p1Shots++;
        p1Pots++;
    } else {
        p2Shots++;
        p2Pots++;
    }

    // --- 1. FREE BALL LOGIC (Moved to TOP) ---
    let actualPoints = points;
    let effectiveBallType = ballType;
    let wasFreeBallShot = false;

    if (isFreeBall && ballType === 'color') {
        actualPoints = 1;
        effectiveBallType = 'red';
        wasFreeBallShot = true;
    }

    // --- 3. UI & SCORE UPDATE ---
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

    // --- 4. HISTORY & TABLE LOGIC ---
    let pointsToRemoveFromTable = 0;
    if (effectiveBallType === 'red' && !wasFreeBallShot) {
        pointsToRemoveFromTable = 8;
    }

    const safeLastShotWasFreeBall = (typeof lastShotWasFreeBall !== 'undefined') ? lastShotWasFreeBall : false;

    // IMPORTANT: We make a history entry NOW, before we increment the ball counter!
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

    // Update UI Value
    playerScoreInput.value = newScore;

    // --- 2. COUNTING SPECIFIC BALLS (MOVED HERE) ---
    // Now we increment the counters. Undo will restore the state before this point.
    if (wasFreeBallShot) {
        currentCounts.red++;
    } else {
        if (points === 1) currentCounts.red++;
        else if (points === 2) currentCounts.yellow++;
        else if (points === 3) currentCounts.green++;
        else if (points === 4) currentCounts.brown++;
        else if (points === 5) currentCounts.blue++;
        else if (points === 6) currentCounts.pink++;
        else if (points === 7) currentCounts.black++;
    }

    // --- 5. RED BALL REMOVAL LOGIC ---
    if (effectiveBallType === 'red') {
        for (let i = 0; i < actualPoints; i++) {
            redBallsPottedThisTurn++;

            if (!wasFreeBallShot) {
                updateRedBalls(1);
                updatePointsOnTable(1);
            }

            if (redBallsPottedThisTurn > 1 && !wasFreeBallShot) {
                updatePointsOnTable(7);
            }
        }
        lastPottedRed = true;
        lastShotWasFreeBall = wasFreeBallShot;

    } else if (ballType === 'color') {
        if (lastPottedRed) {
            if (!safeLastShotWasFreeBall) {
                updatePointsOnTable(7);
            }
            lastShotWasFreeBall = false;
        } else {
            updatePointsOnTable(points);
        }
        lastPottedRed = false;
        redBallsPottedThisTurn = 0;
    }

    // --- 6. HIDING BALLS ---
    const currentPointsOnTable = parseInt(document.getElementById("points-on-table").textContent, 10);
    hideColorBallBasedOnPoints(currentPointsOnTable);

    if (currentPointsOnTable <= 27) {
        showColorBalls();
        hideColorBallBasedOnPoints(currentPointsOnTable);
    }

    // --- 7. RESET FREE BALL ---
    if (isFreeBall) {
        isFreeBall = false;
    }

    updateBallStatsUI();
    updateFrameStatus();
}

function resolvePendingSafety(opponentPottedBall) {
    if (pendingSafetyCheck && safetyPlayerId !== null) {

        // Logic: If the opponent did NOT pot the ball (opponentPottedBall == false),
        // then the layup was a SUCCESS.
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

        // We reset the memory
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

    // --- CHECKING THE PREVIOUS SAFETY ---
    // We return false because no ball was potted (meaning the safety was successful)
    resolvePendingSafety(false);
    // --------------------------------------

    // Counting miss
    if (activePlayer === 1) {
        p1Shots++;  // He fired a shot
        p1Misses++; // But he missed.
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

    // 1. If previous player played a safety, and I play a safety too,
    // their safety was SUCCESSFUL (because they didn't let me pot).
    resolvePendingSafety(false);

    // 2. Update general statistics
    if (activePlayer === 1) {
        p1Shots++;
        p1Safeties++;
    } else {
        p2Shots++;
        p2Safeties++;
    }

    // 3. SET FLAG FOR THE FUTURE
    // Now my safety will be evaluated in the next turn
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

    // Remember WHO is leaving the table (we save their stats)
    const playerLeaving = activePlayer;

    // Send to DB only if they actually played (time > 1s or shot taken)
    if (timeSpentSeconds > 1 || currentTurnShots > 0) {

        // Get frame ID from HTML (ensure it exists in HTML, as discussed earlier)
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
    turnStartTime = Date.now(); // Reset timer for the new player
    currentTurnShots = 0;       // Reset shot counter for the new player


    // --- 3. EXISTING LOGIC (BREAKS HISTORY) ---
    // If break was significant (>= 10), save it to player history
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
    // BS5: Opening the foul modal
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

        // --- CHECKING THE PREVIOUS WAY ---
        // An opponent's foul is a success on the way (forcing an error)
        resolvePendingSafety(false);
        // --------------------------------------

        // --- START NEW CODE ---
        // Update Foul Statistics
        if (activePlayer === 1) {
            p1Fouls++;
            p1FoulPoints += foulPoints;
            p1Shots++;
            p1Misses++;
        } else {
            p2Fouls++;
            p2FoulPoints += foulPoints;
            p2Shots++;
            p2Misses++;
        }
        // --- END NEW CODE ---

        const opponentId = activePlayer === 1 ? 2 : 1;
        const opponentScoreElement = document.querySelector(`.player-score[data-player="${opponentId}"]`);
        const previousOpponentScore = parseInt(opponentScoreElement.value || '0', 10);
        const previousRedBalls = parseInt(document.getElementById("red-ball-count").textContent, 10);
        const previousPointsOnTable = parseInt(document.getElementById("points-on-table").textContent, 10);

        // We get the checkbox status
        const isFreeBallSelected = document.getElementById('freeBallCheckbox').checked;

        // We save the current break BEFORE we reset it
        const breakBeforeFoul = currentBreak;

        // If a player builds a break >= 10 and then fouls, the break still counts towards the stats!
        if (currentBreak >= 10) {
            if (activePlayer === 1) {
                p1BreaksHistory.push(currentBreak);
            } else {
                p2BreaksHistory.push(currentBreak);
            }
        }

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
            setFreeBall: isFreeBallSelected,   // <--- Important: there must be a comma here
            previousBreak: breakBeforeFoul     // <--- This is the new line
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

        // We set the flag
        isFreeBall = isFreeBallSelected;

        // We reset the break (because of the player change)
        currentBreak = 0;
        updateBreakDisplay();

        setActivePlayer(nextPlayerId);

        updateFrameStatus();

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

    // BS5: Closing the first modal
    // We need to find an existing instance (or create a new one to be able to invoke hide)
    const endModalEl = document.getElementById('endFrameModal');
    const endModal = bootstrap.Modal.getInstance(endModalEl) || new bootstrap.Modal(endModalEl);
    endModal.hide();

    const playerNameSpan = document.getElementById('confirmation-player-name');
    if (playerNameSpan) {
        playerNameSpan.textContent = `Player ${winnerId}`;
    }

    // BS5: Opening the second modal
    const confirmModal = new bootstrap.Modal(document.getElementById('confirmWinnerModal'));
    confirmModal.show();
}

function finalizeFrameEnd() {
    // BS5: Closing the confirmation modal
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
            p1_breaks: p1BreaksHistory, p2_breaks: p2BreaksHistory,

            // --- TUTAJ DODAJEMY NASZE NOWE LICZNIKI ---
            ball_counts: {
                player1: p1BallCounts,
                player2: p2BallCounts
            }
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            console.log("Frame saved successfully!");
            isUnsafeToLeave = false;
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

// Helper function to clear the table (old code moved here)
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

// --- HELPER FUNCTIONS FOR UNDO/REDO STATISTICS ---

function getStatsSnapshot() {
    return {
        // Basic counters
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

        // Break arrays (important: we make a copy through [...])
        p1BreaksHistory: [...p1BreaksHistory],
        p2BreaksHistory: [...p2BreaksHistory],

        // --- NEW: We save the state of the billiard counters ---
        // IMPORTANT: We make a copy of the {...} objects to avoid saving references!
        p1BallCounts: { ...p1BallCounts },
        p2BallCounts: { ...p2BallCounts },
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

    // Restoring the tables
    p1BreaksHistory = snapshot.p1BreaksHistory;
    p2BreaksHistory = snapshot.p2BreaksHistory;

    // --- NEW: We're bringing back ball counters ---
    p1BallCounts = snapshot.p1BallCounts || { ...initialBallCounts };
    p2BallCounts = snapshot.p2BallCounts || { ...initialBallCounts };
}

// Function that generates HTML with balls
function updateBallStatsUI() {
    function generateHTML(counts) {
        let html = '';
        // Display order: Red, Yellow, Green...
        const order = ['red', 'yellow', 'green', 'brown', 'blue', 'pink', 'black'];

        order.forEach(color => {
            const count = counts[color];
            if (count > 0) {
                html += `<div class="snooker-ball-icon ball-${color}">${count}</div>`;
            }
        });
        return html;
    }

    const p1Container = document.getElementById('p1-ball-stats');
    const p2Container = document.getElementById('p2-ball-stats');

    if (p1Container) p1Container.innerHTML = generateHTML(p1BallCounts);
    if (p2Container) p2Container.innerHTML = generateHTML(p2BallCounts);
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

    // Visibility toggle function
    function toggleSidebar() {
        if (sidebar && backdrop) {
            sidebar.classList.toggle('active');
            backdrop.classList.toggle('active');
        }
    }

    // Opening (clicking on the History button in the panel)
    if (historyBtn) {
        historyBtn.addEventListener('click', (e) => {
            e.preventDefault();
            toggleSidebar();
        });
    }

    // Closing (clicking the Close button in the panel)
    if (closeSidebarBtn) {
        closeSidebarBtn.addEventListener('click', (e) => {
            e.preventDefault();
            toggleSidebar();
        });
    }

    // Closing (clicking on the dark background outside the panel)
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

/* =========================================
   SNOOKER CALCULATOR (Logic: Active Player & Color Simulation)
   ========================================= */

// 1. Toggle Button Logic
document.addEventListener('DOMContentLoaded', () => {
    const toggleBtn = document.getElementById('btn-toggle-stats');
    const btnText = document.getElementById('stats-btn-text');

    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            isStatsVisible = !isStatsVisible;

            document.querySelectorAll('.match-status-info').forEach(el => {
                el.style.display = isStatsVisible ? 'block' : 'none';
            });

            if (isStatsVisible) {
                toggleBtn.classList.remove('btn-outline-info');
                toggleBtn.classList.add('btn-info');
                toggleBtn.classList.add('text-white');
                if (btnText) btnText.textContent = "Hide Stats";
                updateFrameStatus();
            } else {
                toggleBtn.classList.add('btn-outline-info');
                toggleBtn.classList.remove('btn-info');
                toggleBtn.classList.remove('text-white');
                if (btnText) btnText.textContent = "Show Stats";
            }
        });
    }
});

// 2. Main Calculation Logic (DEBUG VERSION)
function updateFrameStatus() {
    // LOG: Are we entering the function at all?
    console.log("--- [DEBUG] updateFrameStatus triggered ---");

    if (!isStatsVisible) {
        console.log("--- [DEBUG] Calculator hidden -> STOP");
        return;
    }

    const p1ScoreInput = document.querySelector(`.player-score[data-player="1"]`);
    const p2ScoreInput = document.querySelector(`.player-score[data-player="2"]`);
    const remainingEl = document.getElementById("points-on-table");

    // LOG: Who is active according to DOM?
    let activePlayerId = null;
    const activeBtn = document.querySelector('.set-active-player.active');
    if (activeBtn) {
        activePlayerId = parseInt(activeBtn.getAttribute('data-player'), 10);
        console.log(`--- [DEBUG] Active Player (from button): P${activePlayerId}`);
    } else {
        console.warn("--- [DEBUG] No active player (no button has .active class)!");
    }

    if (!p1ScoreInput || !p2ScoreInput || !remainingEl) return;

    const s1 = parseInt(p1ScoreInput.value, 10) || 0;
    const s2 = parseInt(p2ScoreInput.value, 10) || 0;
    const remaining = parseInt(remainingEl.textContent, 10) || 0;

    // Determine Leader and Chaser
    let leaderScore = s1;
    let chaserScore = s2;
    let leaderId = 1;

    if (s2 > s1) {
        leaderScore = s2;
        chaserScore = s1;
        leaderId = 2;
    }

    const diff = leaderScore - chaserScore;
    console.log(`--- [DEBUG] Score: ${s1}-${s2}, On table: ${remaining}, Leader: P${leaderId}, Lead: ${diff}`);

    // Get Status Containers
    const p1Status = document.getElementById("status-p1");
    const p2Status = document.getElementById("status-p2");

    // LOG: Clear old entries
    if (p1Status) p1Status.innerHTML = "";
    if (p2Status) p2Status.innerHTML = "";

    // --- LOGIC START ---

    // SCENARIO 1: SNOOKERS REQUIRED
    if (diff > remaining) {
        const snookersNeeded = Math.ceil((diff - remaining) / 4);
        console.log(`--- [DEBUG] Scenario: Snookers (${snookersNeeded})`);

        const leaderDiv = (leaderId === 1) ? p1Status : p2Status;
        if (leaderDiv && activePlayerId === leaderId) {
             leaderDiv.innerHTML = `<span class="text-success">✅ Frame Secured</span>`;
        }

        const chaserDiv = (leaderId === 1) ? p2Status : p1Status;
        if (chaserDiv) {
            chaserDiv.innerHTML = `<span style="color: #d63384;">⚠️ Snookers needed: ${snookersNeeded}</span>`;
        }
    }
    // SCENARIO 2: OPEN GAME (Open game - no snookers needed)
    else {
        // --- LOGIC FIX: Calculating for the ACTIVE player ---

        // 1. Determine who is at the table
        if (activePlayerId === null) return; // If no one is active, calculate nothing

        const activeScore = (activePlayerId === 1) ? s1 : s2;
        const opponentScore = (activePlayerId === 1) ? s2 : s1;

        // Difference from ACTIVE player's perspective (can be negative if trailing!)
        // E.g. I have 0, Opponent 58 -> myDiff = -58
        const myDiff = activeScore - opponentScore;

        let pointsToWin = 0;

        // SUB-SCENARIO 2A: Reds on table (> 27 pts)
        if (remaining > 27) {
            // Universal formula: (Remaining - MyLead) / 2 + 1
            // If myDiff is negative (chasing), minus and minus gives plus -> i.e. (Remaining + Deficit) / 2
            pointsToWin = Math.floor((remaining - myDiff) / 2) + 1;
        }

        // SUB-SCENARIO 2B: Colors only (<= 27 pts) -> Simulation for ACTIVE player
        else {
            const balls = [2, 3, 4, 5, 6, 7];
            let startIndex = -1;
            if (remaining === 27) startIndex = 0;
            else if (remaining === 25) startIndex = 1;
            else if (remaining === 22) startIndex = 2;
            else if (remaining === 18) startIndex = 3;
            else if (remaining === 13) startIndex = 4;
            else if (remaining === 7)  startIndex = 5;

            if (startIndex !== -1) {
                let simMyScore = activeScore;
                let simRemaining = remaining;
                let accumulatedPoints = 0;

                for (let i = startIndex; i < balls.length; i++) {
                    let ballValue = balls[i];
                    simMyScore += ballValue;
                    simRemaining -= ballValue;
                    accumulatedPoints += ballValue;

                    // Check if this pot secures the win
                    // MyScore > Opponent + Remaining
                    if (simMyScore > (opponentScore + simRemaining)) {
                        break;
                    }
                }
                pointsToWin = accumulatedPoints;
            } else {
                pointsToWin = Math.floor((remaining - myDiff) / 2) + 1;
            }
        }

        if (pointsToWin < 0) pointsToWin = 0;

        console.log(`--- [DEBUG] Active: P${activePlayerId}, Must score: ${pointsToWin}`);

        // --- DISPLAY ---
        // Display ONLY in the active player's container
        const activeDiv = (activePlayerId === 1) ? p1Status : p2Status;

        if (activeDiv && pointsToWin > 0) {
            activeDiv.innerHTML = `<span class="text-primary">To win: ${pointsToWin} pts</span>`;
        }

        // Draw - display for both (optional, but at draw diff=0 so logic above works for active)
        if (myDiff === 0 && activeDiv) {
             let pts = (remaining > 27) ? (Math.floor(remaining / 2) + 1) : pointsToWin;
             activeDiv.innerHTML = `<span class="text-secondary">To win: ${pts} pts</span>`;
        }
    }
}

/* =========================================
   SCOREBOARD BROADCASTING (TELEBIM)
   ========================================= */

const scoreChannel = new BroadcastChannel('snooker_live_score');

function broadcastGameState() {
    // 1. Gather Data from DOM
    const p1Name = document.querySelector("h4").textContent.replace(" 🔴", "").trim();
    // Assuming P2 name is the second h4
    const h4s = document.querySelectorAll("h4");
    const p2Name = h4s.length > 1 ? h4s[1].textContent.replace(" 🔴", "").trim() : "Player 2";

    const p1Score = document.querySelector('.player-score[data-player="1"]').value || 0;
    const p2Score = document.querySelector('.player-score[data-player="2"]').value || 0;

    const p1Frames = document.getElementById('player1-frames').value || 0;
    const p2Frames = document.getElementById('player2-frames').value || 0;

    // Removing parentheses from total frames: "( 5 )" -> "5"
    let totalFramesText = document.getElementById('total-frames').value || "0";
    totalFramesText = totalFramesText.replace(/[()]/g, '').trim();

    const remaining = document.getElementById("points-on-table").textContent || 0;
    const timerText = document.getElementById("match-timer").textContent || "00:00:00";

    // Get Active Player ID
    let activeId = null;
    const activeBtn = document.querySelector('.set-active-player.active');
    if (activeBtn) {
        activeId = parseInt(activeBtn.getAttribute('data-player'), 10);
    }

    // Get Stats HTML (Points to win / Snookers)
    // We grab innerHTML to preserve colors/styles
    const p1Stats = document.getElementById("status-p1") ? document.getElementById("status-p1").innerHTML : "";
    const p2Stats = document.getElementById("status-p2") ? document.getElementById("status-p2").innerHTML : "";

    // 2. Build Payload Object
    const payload = {
        activePlayer: activeId,
        currentBreak: typeof currentBreak !== 'undefined' ? currentBreak : 0,
        pointsOnTable: remaining,
        timer: timerText,
        totalFrames: totalFramesText,
        isStatsVisible: typeof isStatsVisible !== 'undefined' ? isStatsVisible : false,

        p1: {
            name: p1Name,
            score: p1Score,
            frames: p1Frames,
            statsHTML: p1Stats
        },
        p2: {
            name: p2Name,
            score: p2Score,
            frames: p2Frames,
            statsHTML: p2Stats
        }
    };

    // 3. Send Signal
    scoreChannel.postMessage(payload);
    // console.log("--- [BROADCAST] Sent data to scoreboard ---");
}

// 4. Hook into existing functions
// Add broadcastGameState() to all places where UI updates
// (Just add it to the end of these functions)

// Helper to inject into existing functions without rewriting them
function hookFunction(funcName) {
    if (typeof window[funcName] === 'function') {
        const original = window[funcName];
        window[funcName] = function(...args) {
            const result = original.apply(this, args);
            // Run broadcast slightly after to ensure DOM is updated
            setTimeout(broadcastGameState, 50);
            return result;
        };
    }
}

// Automatically hook into key functions
document.addEventListener('DOMContentLoaded', () => {
    hookFunction('updateScore');
    hookFunction('switchActivePlayer');
    hookFunction('undo');
    hookFunction('redo');
    hookFunction('resetGame');
    hookFunction('setActivePlayer');
    hookFunction('updateFrameStatus'); // Important: when calc updates, scoreboard updates
    updateMaxPossibleBreak();

    // For Timer: Since it updates every second via setInterval,
    // we need to add it to your startTimer loop manually or accept 1s delay.
    // Better approach: Add broadcastGameState() inside your setInterval in startTimer
});

// ==========================================
// MAX POSSIBLE BREAK CALCULATOR
// ==========================================
function updateMaxPossibleBreak() {
    // We use setTimeout to ensure all variables and the DOM
    // are fully updated BEFORE we calculate the new max break.
    setTimeout(() => {
        const redCountEl = document.getElementById("red-ball-count");
        const pointsOnTableEl = document.getElementById("points-on-table");
        const maxBreakEl = document.getElementById("max-possible-break");

        if (!redCountEl || !pointsOnTableEl || !maxBreakEl) return;

        const redsLeft = parseInt(redCountEl.textContent, 10) || 0;
        const pointsOnTable = parseInt(pointsOnTableEl.textContent, 10) || 0;

        let potentialFromTable = 0;

        // 1. Base Calculation from table
        if (redsLeft > 0) {
            potentialFromTable = (redsLeft * 8) + 27;
        } else {
            potentialFromTable = pointsOnTable;
        }

        // 2. Get active player's ongoing break
        let activeBreak = 0;
        if (typeof currentBreak !== 'undefined') {
            activeBreak = currentBreak;
        }

        let extraPotential = 0;

        // 3. SCENARIO A: Player potted a red/freeball and is currently on a color
        if (typeof lastPottedRed !== 'undefined' && lastPottedRed === true) {
            extraPotential = 7;
        }
        // 4. SCENARIO B: Free Ball awarded, but shot NOT taken yet
        else if (typeof isFreeBall !== 'undefined' && isFreeBall === true && activeBreak === 0) {
            extraPotential = 8;
        }

        // 5. Calculate total max break
        const maxBreak = activeBreak + potentialFromTable + extraPotential;

        // 6. Update the HTML
        maxBreakEl.textContent = maxBreak;
    }, 50); // 50ms micro-delay for perfect DOM synchronization
}